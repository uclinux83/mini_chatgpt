from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import OpenAI
import time
import requests
import base64
import random
import os

SLACK_SOCKET_TOKEN = "Your socket token, starting with xapp-"
SLACK_BOT_USER_TOKEN = "Your bot token, starting with xoxb"
OPENAI_KEY = "Your OpenAI API key"

GPT_MODEL = "gpt-4-1106-preview"
WAITING_MESSAGE = "Please wait..."
FILES_FOLDER = "files"

TTS_MODEL = "tts-1"
TTS_VOICE = "nova"
IMAGE_MODEL = "dall-e-3"
VISION_MODEL = "gpt-4-vision-preview"
VISION_MAX_TOKEN = 300
STT_MODEL = "whisper-1"


app = App(token = SLACK_BOT_USER_TOKEN)
ai_client = OpenAI(api_key = OPENAI_KEY)

@app.message()
def im_message(client, message):
    if message["channel_type"] == "im":
        if message["text"].split(" ")[0] in ["tts", "dall-e", "vision", "stt"]:
            reply = client.chat_postMessage(channel = message["channel"], text = WAITING_MESSAGE)
            if message["text"].startswith("tts"):
                input_text = message["text"].replace("tts", "", 1)
                try:
                    generated_file = generate_tts(input_text)
                    client.files_upload_v2(channel = message["channel"], file = generated_file, title = "Text To Speech")
                    response = f'[SUCCESS] Your text has been converted to speech'
                except:              
                    response = f'[ERROR] Problem converting from text to speech'
            elif message["text"].startswith("dall-e"):
                input_text = message["text"].replace("dall-e", "", 1)
                try:
                    image_url = generate_image(input_text)
                    response = f'[SUCCESS] URL of your generated image: {image_url}'
                except:
                    response = f'[ERROR] Problem generating image using DALL-E'
            elif message["text"].startswith("vision"):
                if "files" in message:
                    input_question = message["text"].replace("vision", "", 1)
                    try:
                        file_path = save_uploaded_file(message["files"][0])
                        response = generate_vision(file_path, input_question)
                    except:
                        response = f'[ERROR] Problem calling Vision API'
                else:
                    response = f'[ERROR] No attached image found in your message'
            elif message["text"].startswith("stt"):
                if "files" in message:
                    try:
                        file_path = save_uploaded_file(message["files"][0])
                        response = generate_stt(file_path)
                    except:
                        response = f'[ERROR] Problem converting from speech to text'
                else:
                    response = f'[ERROR] No attached audio found in your message'
            client.chat_update(channel = message["channel"], ts = reply["ts"], text = response)
        else:
            reply = client.chat_postMessage(channel = message["channel"], thread_ts = message["ts"], text = WAITING_MESSAGE)
            response = get_gpt_response(client, message)
            client.chat_update(channel = message["channel"], ts = reply["ts"], text = response)

#============================================#
    
def get_gpt_response(client, message):
    conversation_history = get_conversation_history(client, message)
    prompt_structure = []
    for msg in conversation_history:
        prompt_structure.append(msg) 
    try:
        response = ai_client.chat.completions.create(
            model = GPT_MODEL,
            messages = prompt_structure
        )
        answer = response.choices[0].message.content
        return answer
    except:
        return f"[ERROR] Problem calling OpenAI API"

def get_conversation_history(client, message):
    result = []
    if "thread_ts" in message:
        conversation = client.conversations_replies(channel = message["channel"], ts = message["thread_ts"])
        if "messages" in conversation:
            for msg in conversation["messages"]:
                if "client_msg_id" in msg:
                    result.append({"role": "user", "content": msg["text"]})
                if "bot_id" in msg:
                    if msg["text"] != WAITING_MESSAGE:
                        result.append({"role": "assistant", "content": msg["text"]})
    else:
        result.append({"role": "user", "content": message["text"]})
    return result

def generate_tts(input_text):
    speech_file_path = f'{FILES_FOLDER}/{generate_random_file_name()}.mp3'
    response = ai_client.audio.speech.create(model = TTS_MODEL, voice = TTS_VOICE, input = input_text)
    response.stream_to_file(speech_file_path)
    return speech_file_path

def generate_image(input_text):
    response = ai_client.images.generate(model = IMAGE_MODEL, prompt = input_text, size = "1024x1024", quality = "standard", n=1)
    return response.data[0].url

def generate_vision(image_path, question):
    base64_image = encode_image(image_path)
    response = ai_client.chat.completions.create(
        model = VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {
                        "type": "image_url",
                        "image_url": {
                           "url": f"data:image/jpeg;base64,{base64_image}"
                        },
                    },
                ],
            }
        ],
        max_tokens = VISION_MAX_TOKEN,
    )
    return response.choices[0].message.content

def generate_stt(file_path):
    audio_file= open(file_path, "rb")
    response = ai_client.audio.transcriptions.create(model = STT_MODEL, file = audio_file, response_format="text")
    return response

def save_uploaded_file(file):
    url = file["url_private"]
    file_path = f'{FILES_FOLDER}/{generate_random_file_name()}.{file["filetype"]}'
    headers = {"Authorization": "Bearer " + SLACK_BOT_USER_TOKEN}
    response = requests.get(url, headers = headers)
    with open(file_path, "wb") as f:
        f.write(response.content)
    return file_path

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
    
def generate_random_file_name():
    return f'{int(time.time_ns())}_{random.randint(0,100)}'

#============================================#

# Create folder for temporary files if not exist
if not os.path.exists(FILES_FOLDER):
    os.makedirs(FILES_FOLDER)
# Start the bot
if __name__ == "__main__":
    SocketModeHandler(app, SLACK_SOCKET_TOKEN).start()

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import OpenAI
import time
import requests
import base64
import random
import os
import json

SLACK_SOCKET_TOKEN = "Your Slack Socket token, starting with xapp-..."
SLACK_BOT_USER_TOKEN = "Your Slack bot user token, starting with xoxb-"
OPENAI_KEY = "Your OpenAI API key"

GPT_MODEL = "gpt-4-1106-preview"
WAITING_MESSAGE = "Please wait..."
FILES_FOLDER = "files"

TTS_MODEL = "tts-1"
TTS_VOICE = "nova"
IMAGE_MODEL = "dall-e-2"
VISION_MODEL = "gpt-4-vision-preview"
VISION_MAX_TOKEN = 300
STT_MODEL = "whisper-1"


app = App(token = SLACK_BOT_USER_TOKEN)
ai_client = OpenAI(api_key = OPENAI_KEY)

tools = [
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate image basing on description",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of the image, e.g. a house under an apple tree",
                    }
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_tts",
            "description": "Generate or convert from text to speech",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_text": {
                        "type": "string",
                        "description": "Text to be converted to speech",
                    }
                },
                "required": ["input_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_stt",
            "description": "Transcript or convert from speech to text"
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_vision",
            "description": "Answer question basing on the input image or photo",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Question regarding to the input image or photo",
                    }
                },
                "required": ["question"],
            },
        },
    }
]

@app.message()
def im_message(client, message):
    if message["channel_type"] == "im":
        reply = client.chat_postMessage(channel = message["channel"], thread_ts = message["ts"], text = WAITING_MESSAGE)
        result = get_gpt_response(client, message)
        if result.content:
            response = result.content
        elif result.tool_calls:
            function_name = result.tool_calls[0].function.name
            arguments = json.loads(result.tool_calls[0].function.arguments)
            if function_name == "generate_image":
                description = arguments["description"]
                try:
                    image_url = generate_image(description)
                    image_content = requests.get(image_url)
                    image_filepath = f'{FILES_FOLDER}/{generate_random_file_name()}.jpg'
                    with open(image_filepath, "wb") as f:
                        f.write(image_content.content)
                    client.files_upload_v2(channel = message["channel"], thread_ts = message["ts"], file = image_filepath, title = description)
                    response = f'[SUCCESS] Image has been generated successfully'
                except Exception as e:
                    print(e)
                    response = f'[ERROR] Problem generating image using DALL-E'
            elif function_name == "generate_tts":
                input_text = arguments["input_text"]
                try:
                    generated_file = generate_tts(input_text)
                    client.files_upload_v2(channel = message["channel"], thread_ts = message["ts"], file = generated_file, title = "Text To Speech")
                    response = f'[SUCCESS] Your text has been converted to speech'
                except:              
                    response = f'[ERROR] Problem converting from text to speech'
            elif function_name == "generate_stt":
                if "files" in message:
                    try:
                        file_path = save_uploaded_file(message["files"][0])
                        response = f'[SUCCESS] {generate_stt(file_path)}'
                    except:
                        response = f'[ERROR] Problem converting from speech to text'
                else:
                    response = f'[ERROR] No attached audio found in your message'
            elif function_name == "generate_vision":
                if "files" in message:
                    question = arguments["question"]
                    try:
                        file_path = save_uploaded_file(message["files"][0])
                        response = generate_vision(file_path, question)
                    except:
                        response = f'[ERROR] Problem calling Vision API'
                else:
                    response = f'[ERROR] No attached image found in your message'
            else:
                response = f"[ERROR] Invalid function"
        else:
            response = f"[ERROR] Invalid response from OpenAI"
        client.chat_update(channel = message["channel"], ts = reply["ts"], text = response)

#============================================#
    
def get_gpt_response(client, message):
    conversation_history = get_conversation_history(client, message)
    prompt_structure = [{"role": "system", "content": "Use tool calls if the user mention about input image, picture or photo"}]
    for msg in conversation_history:
        prompt_structure.append(msg) 
    try:
        response = ai_client.chat.completions.create(
            model = GPT_MODEL,
            messages = prompt_structure,
            tools = tools,
            tool_choice = "auto"
        )
        return response.choices[0].message
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

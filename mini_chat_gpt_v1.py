from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import openai

SLACK_SOCKET_TOKEN = "Your Slack Socket token, starting with xapp-..."
SLACK_BOT_USER_TOKEN = "Your Slack bot user token, starting with xoxb-"
OPENAI_KEY = "Your OpenAI API key"
GPT_MODEL = "gpt-3.5-turbo" #Choose the GPT model that you want to use
WAITING_MESSAGE = "Please wait..."

app = App(token = SLACK_BOT_USER_TOKEN)
openai.api_key = OPENAI_KEY

@app.message()
def im_message(client, message):
    if message["channel_type"] == "im":
        reply = client.chat_postMessage(channel = message["channel"], thread_ts = message["ts"], text = WAITING_MESSAGE)
        response = get_gpt_response(client, message)
        client.chat_update(channel = message["channel"], ts = reply["ts"], text = response)
    
def get_gpt_response(client, message):
    conversation_history = get_conversation_history(client, message)
    prompt_structure = []
    for msg in conversation_history:
        prompt_structure.append(msg) 
    try:
        response = openai.ChatCompletion.create(
            model = GPT_MODEL,
            messages = prompt_structure
        )
        if "choices" in response:
            answer = response["choices"][0]["message"]["content"]
            return answer
        else:
            return f"[ERROR] Response is empty"
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
    
# Start the bot
if __name__ == "__main__":
    SocketModeHandler(app, SLACK_SOCKET_TOKEN).start()

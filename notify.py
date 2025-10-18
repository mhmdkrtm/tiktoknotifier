import os
import requests

TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_message(message: str):
    if not TG_TOKEN or not CHAT_ID:
        print(f"💬 {message}")
        return

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"⚠️ Failed to send Telegram message: {e}")

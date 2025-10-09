import os
import asyncio
import requests
import time
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
from wrapper import record_tiktok_live

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
USERS_FILE = "users.txt"
CHECK_INTERVAL = 60
SUCCESS_COOLDOWN = 300

last_success_time = {}

def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload, timeout=10)
        if r.status_code == 200:
            print("✅ Sent Telegram message.")
    except Exception as e:
        print("❌ Telegram send failed:", e)

async def watch_user(username: str):
    live_announced = False
    while True:
        last_time = last_success_time.get(username, 0)
        if time.time() - last_time < SUCCESS_COOLDOWN:
            await asyncio.sleep(SUCCESS_COOLDOWN - (time.time() - last_time))
            continue
        try:
            client = TikTokLiveClient(unique_id=username)

            @client.on(ConnectEvent)
            async def on_connect(event):
                nonlocal live_announced
                print(f"[+] @{username} is LIVE (Room ID: {client.room_id})")
                if not live_announced:
                    send_telegram(f"🔴 <b>@{username} is now LIVE!</b>\n<a href='https://www.tiktok.com/@{username}/live'>Watch Now</a>")
                    live_announced = True
                    asyncio.create_task(record_tiktok_live(username))

            @client.on(DisconnectEvent)
            async def on_disconnect(event):
                nonlocal live_announced
                print(f"[-] @{username} disconnected.")
                if live_announced:
                    send_telegram(f"⚪ @{username} has ended the live.")
                live_announced = False
                await client.disconnect()

            await client.start()
            last_success_time[username] = time.time()

        except Exception as e:
            print(f"[!] @{username} error: {e}. Retrying in {CHECK_INTERVAL}s...")
            live_announced = False
            await asyncio.sleep(CHECK_INTERVAL)

async def main():
    if not os.path.exists(USERS_FILE):
        print(f"File '{USERS_FILE}' not found!")
        return
    with open(USERS_FILE, "r") as f:
        users = [line.strip().replace('@', '') for line in f if line.strip() and not line.startswith('#')]
    if not users:
        print("No usernames found in users.txt")
        return

    print(f"🔥 Monitoring {len(users)} users: {', '.join(users)}")
    tasks = [asyncio.create_task(watch_user(u)) for u in users]
    await asyncio.gather(*tasks)

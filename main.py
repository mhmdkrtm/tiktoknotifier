import asyncio
import os
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "your_telegram_bot_token"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or "your_chat_id"
USERS_FILE = "users.txt"
CHECK_INTERVAL = 60  # seconds between retry attempts
# ----------------------

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"


def send_telegram(msg: str):
    """Send message to Telegram."""
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        r = requests.post(TELEGRAM_API, json=payload, timeout=10)
        if r.status_code != 200:
            print("Telegram error:", r.text)
        else:
            print("✅ Sent Telegram message.")
    except Exception as e:
        print("❌ Telegram send failed:", e)


async def watch_user(username: str):
    """Keep trying to connect to a user's live stream."""
    client = TikTokLiveClient(unique_id=username)
    live_announced = False

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        nonlocal live_announced
        if not live_announced:
            msg = f"🔴 @{username} is now LIVE!\nhttps://www.tiktok.com/@{username}/live"
            send_telegram(msg)
            live_announced = True
        print(f"[+] Connected to @{username}")

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent):
        nonlocal live_announced
        if live_announced:
            send_telegram(f"⚪ @{username} has ended the live.")
        live_announced = False
        print(f"[-] Disconnected from @{username}")

    while True:
    try:
        if not client.is_connected():
            await client.start()
        else:
            await asyncio.sleep(CHECK_INTERVAL)
    except Exception as e:
        if "UserOfflineError" in str(e):
            print(f"[ℹ️] @{username} is offline, rechecking in {CHECK_INTERVAL}s...")
        elif "one connection per client" in str(e).lower():
            print(f"[ℹ️] @{username} already connected, skipping duplicate connect.")
        else:
            print(f"[!] @{username} unexpected error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def main():
    """Read usernames and start monitoring tasks for each."""
    if not os.path.exists(USERS_FILE):
        print(f"File '{USERS_FILE}' not found!")
        return

    with open(USERS_FILE, "r") as f:
        users = [line.strip() for line in f if line.strip()]

    if not users:
        print("No usernames found in users.txt")
        return

    print(f"🔥 TikTok Live → Telegram Notifier started")
    print(f"🚀 Monitoring {len(users)} TikTok users...")

    tasks = [asyncio.create_task(watch_user(u)) for u in users]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())

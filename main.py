import asyncio
import os
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
from TikTokLive.errors import LiveNotFound

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


async def monitor_user(username: str):
    """Monitor one TikTok user for live status."""
    client = TikTokLiveClient(unique_id=username)
    live_announced = False

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        nonlocal live_announced
        print(f"[+] @{username} is LIVE (Room ID: {client.room_id})")
        if not live_announced:
            msg = f"🔴 @{username} is now LIVE!\nhttps://www.tiktok.com/@{username}/live"
            send_telegram(msg)
            live_announced = True

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent):
        nonlocal live_announced
        if live_announced:
            msg = f"⚪ @{username} has ended the live."
            send_telegram(msg)
        print(f"[-] @{username} disconnected or ended live.")
        live_announced = False

    while True:
        try:
            await client.run()
        except LiveNotFound:
            print(f"[!] @{username} not live. Retry in {CHECK_INTERVAL}s.")
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"[!] Error for @{username}: {e}")
            await asyncio.sleep(CHECK_INTERVAL)


async def main():
    """Read usernames and start monitoring all of them."""
    if not os.path.exists(USERS_FILE):
        print(f"File '{USERS_FILE}' not found!")
        return

    with open(USERS_FILE, "r") as f:
        usernames = [line.strip() for line in f if line.strip()]

    if not usernames:
        print("No usernames found in users.txt")
        return

    print(f"🚀 Monitoring {len(usernames)} TikTok users...")
    for u in usernames:
        asyncio.create_task(monitor_user(u))

    # Keep alive forever
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    print("🔥 TikTok Live → Telegram Notifier started")
    asyncio.run(main())
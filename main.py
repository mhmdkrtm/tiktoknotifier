import asyncio
import os
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
print("🔍 DEBUG: TELEGRAM_TOKEN =", os.environ.get("TELEGRAM_TOKEN"))
print("🔍 DEBUG: TELEGRAM_CHAT_ID =", os.environ.get("TELEGRAM_CHAT_ID"))

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or "1280121045"
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
    """Monitor TikTok user live status."""
    client = TikTokLiveClient(unique_id=username)
    live_announced = False

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        nonlocal live_announced
        print(f"[+] @{username} is LIVE!")
        if not live_announced:
            msg = f"🔴 @{username} is now LIVE!\nhttps://www.tiktok.com/@{username}/live"
            send_telegram(msg)
            live_announced = True

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent):
        nonlocal live_announced
        if live_announced:
            send_telegram(f"⚪ @{username} has ended the live.")
        print(f"[-] @{username} disconnected.")
        live_announced = False

    # Retry loop
    while True:
        try:
            await client.start()
        except Exception as e:
            err_str = str(e)
            if "UserOfflineError" in err_str:
                print(f"[ℹ️] @{username} is offline, rechecking in {CHECK_INTERVAL}s...")
            elif "one connection per client" in err_str.lower():
                print(f"[ℹ️] @{username} already connected, skipping duplicate connect.")
            else:
                print(f"[!] @{username} unexpected error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)


async def main():
    """Start monitoring all users."""
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

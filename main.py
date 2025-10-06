import asyncio
import os
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent

# =====================================================
# 🔒 CONFIGURATION
# Replace the placeholders below *only in your private copy*.
# =====================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or "1280121045"
USERS_FILE = "users.txt"
CHECK_INTERVAL = 60     # seconds between retries
GRACE_PERIOD = 30       # seconds to confirm stream really ended
# =====================================================

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"


def send_telegram(msg: str):
    """Send a message to Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram token or chat ID not set.")
        return
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        r = requests.post(TELEGRAM_API, json=payload, timeout=10)
        if r.status_code == 200:
            print("✅ Sent Telegram message.")
        else:
            print("Telegram error:", r.text)
    except Exception as e:
        print("❌ Telegram send failed:", e)


async def watch_user(username: str):
    """Monitor a TikTok user with a disconnect-grace period."""
    client = TikTokLiveClient(unique_id=username)
    live_announced = False
    disconnect_task = None

    async def confirm_end():
        """Wait before confirming the live really ended."""
        await asyncio.sleep(GRACE_PERIOD)
        if not getattr(client, "connected", False):
            send_telegram(f"⚪ @{username} has ended the live.")
            print(f"[-] @{username} confirmed offline after {GRACE_PERIOD}s.")
            return True
        return False

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        nonlocal live_announced, disconnect_task
        if disconnect_task:
            disconnect_task.cancel()
            disconnect_task = None
        if not live_announced:
            msg = f"🔴 @{username} is now LIVE!\nhttps://www.tiktok.com/@{username}/live"
            send_telegram(msg)
            live_announced = True
        print(f"[+] Connected to @{username}")

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent):
        nonlocal live_announced, disconnect_task
        print(f"[ℹ️] @{username} disconnected — checking if truly offline...")
        if disconnect_task:
            disconnect_task.cancel()
        disconnect_task = asyncio.create_task(confirm_end())
        live_announced = False

    while True:
        try:
            await client.start()
        except Exception as e:
            err = str(e)
            if "UserOfflineError" in err:
                print(f"[ℹ️] @{username} offline, rechecking in {CHECK_INTERVAL}s...")
            elif "one connection per client" in err.lower():
                print(f"[ℹ️] @{username} already connected, skipping duplicate connect.")
            else:
                print(f"[!] @{username} unexpected error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)


async def main():
    """Read usernames and start monitoring all of them."""
    if not os.path.exists(USERS_FILE):
        print(f"File '{USERS_FILE}' not found!")
        return

    with open(USERS_FILE, "r") as f:
        users = [line.strip() for line in f if line.strip()]

    if not users:
        print("No usernames found in users.txt")
        return

    print("🔥 TikTok Live → Telegram Notifier started")
    print(f"🚀 Monitoring {len(users)} TikTok users...")

    tasks = [asyncio.create_task(watch_user(u)) for u in users]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())

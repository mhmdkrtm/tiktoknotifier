import asyncio
import os
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent

# ========= CONFIG =========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")  # keep these in Railway vars
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
USERS_FILE = "users.txt"

GRACE_PERIOD = 45  # seconds to wait after a disconnect before we "arm" next-live notification
RETRY_DELAY = 60   # seconds between retries when user is offline / errors
# =========================

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
        return
    try:
        r = requests.post(TELEGRAM_API, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        if r.status_code == 200:
            print("✅ Telegram sent")
        else:
            print("Telegram error:", r.text)
    except Exception as e:
        print("❌ Telegram send failed:", e)

async def watch_user(username: str):
    """
    Notify ONCE when the user goes live.
    Do NOT notify on end.
    Don't send periodic messages.
    Handle brief disconnects without re-notifying (grace period).
    """
    client = TikTokLiveClient(unique_id=username)

    # If True, we've already notified for the current live session.
    live_announced = False
    # A task that, after a grace period, "arms" us to notify on the next real live.
    rearm_task = None

    async def rearm_after_grace():
        """After a grace period with no reconnect, allow next live to notify again."""
        nonlocal live_announced, rearm_task
        await asyncio.sleep(GRACE_PERIOD)
        # if no reconnect happened during grace, re-arm
        live_announced = False
        rearm_task = None
        print(f"[✓] @{username} re-armed (will notify on next real live)")

    @client.on(ConnectEvent)
    async def on_connect(_evt: ConnectEvent):
        nonlocal live_announced, rearm_task
        # If we had a pending rearm (from a brief disconnect), cancel it — still same live.
        if rearm_task and not rearm_task.done():
            rearm_task.cancel()
            rearm_task = None

        # Only notify if we haven't announced this live session yet
        if not live_announced:
            send_telegram(f"🔴 @{username} is now LIVE!\nhttps://www.tiktok.com/@{username}/live")
            live_announced = True
        print(f"[+] @{username} connected (live active)")

    @client.on(DisconnectEvent)
    async def on_disconnect(_evt: DisconnectEvent):
        nonlocal rearm_task
        print(f"[ℹ️] @{username} disconnected — starting grace timer ({GRACE_PERIOD}s)")
        # Start (or restart) grace timer; if they don't reconnect in time, we re-arm.
        if rearm_task and not rearm_task.done():
            rearm_task.cancel()
        rearm_task = asyncio.create_task(rearm_after_grace())

    while True:
        try:
            await client.start()
        except Exception as e:
            err = str(e)
            if "UserOfflineError" in err:
                print(f"[ℹ️] @{username} offline, retrying in {RETRY_DELAY}s...")
            elif "one connection per client" in err.lower():
                # Harmless; avoid busy loop
                print(f"[ℹ️] @{username} already connected, backing off {RETRY_DELAY}s...")
            else:
                print(f"[!] @{username} unexpected error: {e}")
            await asyncio.sleep(RETRY_DELAY)

async def main():
    if not os.path.exists(USERS_FILE):
        print(f"File '{USERS_FILE}' not found!")
        return

    with open(USERS_FILE, "r") as f:
        users = [u.strip() for u in f if u.strip()]

    if not users:
        print("No usernames in users.txt")
        return

    print("🔥 TikTok Live → Telegram Notifier started")
    print(f"🚀 Monitoring {len(users)} TikTok users...")
    tasks = [asyncio.create_task(watch_user(u)) for u in users]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent

# --- CONFIGURATION ---
# NOTE: Using os.environ.get for deployment secrets (best practice)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or "1280121045"
USERS_FILE = "users.txt"
CHECK_INTERVAL = 60  # seconds between retry attempts

# --- Checks ---
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ FATAL: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID is missing from environment variables or config.")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# ----------------------

def send_telegram(msg: str):
    """Send message to Telegram using blocking requests (for simplicity)."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing. Skipping notification.")
        return
        
    try:
        # Use simple requests.post (Note: this is blocking, but acceptable for simple notification)
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        r = requests.post(TELEGRAM_API, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"Telegram error: {r.status_code} - {r.text}")
        else:
            print("✅ Sent Telegram message.")
    except Exception as e:
        print("❌ Telegram send failed:", e)

# --- Core Monitoring Logic ---

async def watch_user(username: str):
    """Keep trying to connect to a user's live stream."""
    
    # live_announced acts as the 'only notify once' flag for the current session
    live_announced = False
    
    # Main loop to handle disconnections and retries
    while True:
        try:
            client = TikTokLiveClient(unique_id=username)
            
            @client.on(ConnectEvent)
            async def on_connect(event: ConnectEvent):
                nonlocal live_announced
                print(f"[+] @{username} is LIVE (Room ID: {client.room_id})")
                
                # Only notify if this is a NEW session
                if not live_announced:
                    msg = f"🔴 <b>@{username} is now LIVE!</b>\n<a href='https://www.tiktok.com/@{username}/live'>Watch Now</a>"
                    send_telegram(msg)
                    live_announced = True
                
            @client.on(DisconnectEvent)
            async def on_disconnect(event: DisconnectEvent):
                nonlocal live_announced
                print(f"[-] @{username} disconnected or ended live.")
                
                # Only notify if we actually announced the stream start
                if live_announced:
                    msg = f"⚪ @{username} has ended the live."
                    send_telegram(msg)
                    
                live_announced = False # Reset flag for next stream
                
                # Force client exit to allow the outer loop to catch the error and retry cleanly
                await client.disconnect() 

            # Start the client. This call is blocking until disconnection or error.
            await client.start()
            
        except Exception as e:
            # Handle user offline, connection errors, or client library bugs
            print(f"[!] @{username} error: {e}. Retrying...")
            live_announced = False # Ensure we try to notify again on next connection
            await asyncio.sleep(CHECK_INTERVAL)

async def main():
    """Read usernames and start monitoring tasks for each."""
    if not os.path.exists(USERS_FILE):
        print(f"File '{USERS_FILE}' not found!")
        return
        
    with open(USERS_FILE, "r") as f:
        # Read unique usernames, ignoring empty lines and comments
        users = [line.strip().replace('@', '') for line in f if line.strip() and not line.startswith('#')]
    
    if not users:
        print("No usernames found in users.txt")
        return
        
    print(f"🔥 TikTok Live → Telegram Notifier started")
    print(f"🚀 Monitoring {len(users)} TikTok users: {', '.join(users)}")
    
    # Create and run concurrent tasks for all users
    tasks = [asyncio.create_task(watch_user(u)) for u in users]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nService interrupted and shutting down.")

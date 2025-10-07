import asyncio
import os
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent

# ====================================================================
# 1. CONFIGURATION AND CREDENTIALS ⚠️
# ====================================================================

# --- Telegram Credentials ---
# NOTE: Using os.environ.get for deployment secrets (best practice)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or "1280121045"
USERS_FILE = "users.txt"
CHECK_INTERVAL = 300  # Increased to 300s (5 min) to respect rate limits

# --- TikTok Login Credentials (FOR AUTHENTICATION) ---
# Set these as environment variables on Railway for security, OR insert directly here.
TIKTOK_USERNAME = os.environ.get("TIKTOK_USERNAME") or "mhero0030@gmail.com"
TIKTOK_PASSWORD = os.environ.get("TIKTOK_PASSWORD") or "mhmd2002"

# --- API Setup ---
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ FATAL: Telegram credentials missing.")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# ----------------------

def send_telegram(msg: str):
    """Send message to Telegram using synchronous requests."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing. Skipping notification.")
        return
        
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        r = requests.post(TELEGRAM_API, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"Telegram error: {r.status_code} - {r.text}")
        else:
            print("✅ Sent Telegram message.")
    except Exception as e:
        print("❌ Telegram send failed:", e)

# ----------------------

async def watch_user(username: str):
    """Monitor one TikTok user for live status, using account login."""
    
    # live_announced acts as the 'only notify once' flag for the current session
    live_announced = False
    
    # Main loop to handle disconnections and retries
    while True:
        try:
            # --- AUTHENTICATION FIX: Initialize client with credentials ---
            client = TikTokLiveClient(
                unique_id=username,
                # Pass credentials directly to the client
                session_id=None, # session_id is used for advanced login, but typically not needed here
                web_session_parameters={
                    "username": TIKTOK_USERNAME,
                    "password": TIKTOK_PASSWORD
                }
            )
            # -----------------------------------------------------------
            
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
            # This handles rate limit errors, disconnects, user offline, etc.
            # The rate limit error should be significantly reduced now.
            print(f"[!] @{username} error: {e}. Retrying in {CHECK_INTERVAL}s...")
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
        
    # Final check for credentials
    if TIKTOK_USERNAME == "YOUR_TIKTOK_USERNAME" or TIKTOK_PASSWORD == "YOUR_TIKTOK_PASSWORD":
        print("❌ WARNING: Please replace TikTok login placeholders in the code/environment.")
    
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

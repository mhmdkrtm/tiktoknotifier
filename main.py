import asyncio
import time
import os
import subprocess
import signal
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, RPCError

# ====================================================================
# 1. DIRECT VARIABLE INSERTION (Customize these values for testing) ⚠️
# ====================================================================

# --- Telegram Secrets ---
TG_API_ID = 20196111               # ⚠️ YOUR TELEGRAM API ID (from my.telegram.org)
TG_API_HASH = "05b184f5623850b5666c32e14e7a888b"     # ⚠️ YOUR TELEGRAM API HASH
TG_BOT_TOKEN = "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"        # ⚠️ YOUR TELEGRAM BOT TOKEN
MY_USER_ID = 1280121045            # ⚠️ YOUR PERSONAL CHAT ID (e.g., your saved messages ID or private chat ID)

# --- General Config ---
SEGMENT_DURATION_SECONDS = 30   # 🎯 SET TO 30 SECONDS FOR TESTING 🎯
CHECK_OFFLINE = 30              # Seconds to wait when user is offline
NOTIFY_COOLDOWN = 600           # Cooldown for live notifications (10 min)
USERS_FILE = 'users.txt'        # File containing usernames

# --- Recorder Reconnect Logic ---
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_WAIT_SECONDS = 15 

# --- Storage Paths ---
VIDEO_PATH_TEMPLATE = './temp/{username}_segment.mp4'

# --- Trackers (Global State) ---
last_notification_time = {}
is_recording_active = {} 
telegram_client = None # Global client for notification messaging


# ====================================================================
# 2. CORE FUNCTIONS: Telegram Client & Notifier
# ====================================================================

async def initialize_telegram_client():
    """Initializes the global Telethon client."""
    global telegram_client
    if telegram_client is None:
        print("[ℹ️] Initializing Telegram Client...")
        client = TelegramClient('session_name', TG_API_ID, TG_API_HASH)
        try:
            await client.start(bot_token=TG_BOT_TOKEN)
            telegram_client = client
            print("[✅] Telegram Client connected successfully.")
        except SessionPasswordNeededError:
            print("[❌] ERROR: 2FA is enabled. Telethon requires a user account setup for 2FA, or ensure you are connecting as a bot only.")
            raise
        except RPCError as e:
            print(f"[❌] Telegram RPC Error during connection: {e}")
            raise

async def send_bot_msg(message):
    """FIX: Sends message using the async Telethon client."""
    global telegram_client
    if telegram_client is None:
        try:
            await initialize_telegram_client()
        except:
            print("[❌] Failed to initialize Telegram client for notification.")
            return

    try:
        # 'me' or MY_USER_ID can be used to send to Saved Messages
        await telegram_client.send_message(MY_USER_ID, message)
        print(f"[✅] Telegram Notification sent.")
    except Exception as e:
        print(f"[❌] Failed to send Telegram message to {MY_USER_ID}: {e}")

# ====================================================================
# 3. CORE FUNCTIONS: Recording and Uploading
# ====================================================================

def record_with_ytdlp(username):
    """
    Synchronous function that manages segmented recording using yt-dlp.
    Uses the user's verified working yt-dlp options.
    """
    video_path = VIDEO_PATH_TEMPLATE.format(username=username)
    os.makedirs(os.path.dirname(video_path), exist_ok=True)
    tiktok_url = f"https://www.tiktok.com/@{username}/live"
    segment_count = 0
    consecutive_failures = 0
    
    if os.path.exists(video_path):
        os.remove(video_path)

    while is_recording_active.get(username, False) and consecutive_failures < MAX_RECONNECT_ATTEMPTS:
        segment_count += 1
        print(f"--- @{username}: Starting Segment {segment_count} ---")
        
        # --- FIXED COMMAND USING YOUR WORKING OPTIONS ---
        command = [
            'yt-dlp',
            '--wait-for-video', '60',
            '-f', 'bestvideo[height<=720]+bestaudio/best',
            '--output', video_path, 
            tiktok_url
        ]
        
        try:
            # Note: We use PIPE for stderr to capture errors, but DEVNULL for stdout
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            
            # Monitor and terminate the process based on SEGMENT_DURATION_SECONDS
            start_time = time.time()
            while time.time() - start_time < SEGMENT_DURATION_SECONDS:
                if not is_recording_active.get(username, False) or process.poll() is not None:
                    break
                time.sleep(1)
            
            # --- Robust Termination ---
            if process.poll() is None:
                print("Segment recording timed out. Terminating process...")
                process.send_signal(signal.SIGINT)
                
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            
            # Capture any remaining stderr and check for errors
            stdout, stderr = process.communicate()
            if stderr:
                 print(f"[YT-DLP DEBUG/ERROR] @{username}: {stderr.decode().strip()}")

            # --- Check Result ---
            if os.path.exists(video_path) and os.path.getsize(video_path) > 1024 * 10:
                print(f"[✅] Segment recording succeeded. File size: {os.path.getsize(video_path) / (1024*1024):.2f}MB")
                consecutive_failures = 0
            else:
                # --- Failure Logic: Retry ---
                print(f"[⚠️] Recording failed or file too small for @{username}. Retrying...")
                consecutive_failures += 1
                if consecutive_failures < MAX_RECONNECT_ATTEMPTS:
                    print(f"Waiting {RECONNECT_WAIT_SECONDS}s before re-initiation (Attempt {consecutive_failures+1}/{MAX_RECONNECT_ATTEMPTS})...")
                    time.sleep(RECONNECT_WAIT_SECONDS)
                    continue
                else:
                    print(f"[❌] Max reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) reached. Stopping recording for @{username}.")
                    is_recording_active[username] = False
            
        except FileNotFoundError:
            print("[❌] FATAL ERROR: 'yt-dlp' or 'ffmpeg' command not found. Cannot continue.")
            is_recording_active[username] = False
            break
        except Exception as e:
            print(f"[!] @{username} General recording error: {e}. Retrying.")
            consecutive_failures += 1
            if consecutive_failures >= MAX_RECONNECT_ATTEMPTS:
                 is_recording_active[username] = False
            
    print(f"@{username} Recording loop stopped. (Failures: {consecutive_failures})")


async def upload_segments(username):
    """
    Asynchronous task that monitors the disk for completed segments, 
    uploads them to Telegram, and deletes them.
    """
    video_path = VIDEO_PATH_TEMPLATE.format(username=username)
    global telegram_client

    if telegram_client is None:
        await initialize_telegram_client()

    try:
        while is_recording_active.get(username, False):
            await asyncio.sleep(5)
            
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                print(f"[⬆️] @{username}: Segment ready, starting upload...")
                
                try:
                    await telegram_client.send_file(
                        MY_USER_ID, 
                        video_path, 
                        caption=f"🎥 TikTok LIVE: @{username} Segment {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
                    )
                    print("[✅] Upload successful.")

                except Exception as e:
                    print(f"[❌] Telegram upload failed for @{username}: {e}")
                
                # CRITICAL: DELETE FILE
                try:
                    os.remove(video_path)
                    print(f"[🗑️] Successfully deleted {video_path}.")
                except Exception as e:
                    print(f"[⚠️] Failed to delete file on Railway: {e}")

        print(f"@{username} Uploader loop stopped.")

    except Exception as e:
        print(f"[❌] Uploader task error for @{username}: {e}")

# ====================================================================
# 4. TIKTOK LISTENER AND MAIN LOOP
# ====================================================================

async def watch_user(username):
    """Monitor TikTok user → notify → record → upload."""
    client = TikTokLiveClient(unique_id=username)
    recording_task = None
    uploader_task = None

    def stop_tasks():
        """Helper to safely stop all tasks."""
        nonlocal recording_task, uploader_task
        print(f"[ℹ️] Setting stop flag for @{username}.")
        is_recording_active[username] = False 
        
        if uploader_task and not uploader_task.done():
            uploader_task.cancel()
            
        recording_task = None
        uploader_task = None
        video_path = VIDEO_PATH_TEMPLATE.format(username=username)
        if os.path.exists(video_path):
             os.remove(video_path)

    @client.on(ConnectEvent)
    async def on_connect(_):
        nonlocal recording_task, uploader_task
        print(f"[+] @{username} is LIVE!")
        
        now = time.time()
        last_time = last_notification_time.get(username, 0)
        if now - last_time > NOTIFY_COOLDOWN:
            # FIX: Now calls the new async send_bot_msg function
            await send_bot_msg(f"🔴 @{username} is LIVE! Recording started (30s segments).")
            last_notification_time[username] = now
        else:
            print(f"[ℹ️] Skipping duplicate LIVE message (cooldown active).")

        is_recording_active[username] = True
        
        if not recording_task:
            loop = asyncio.get_event_loop()
            recording_task = loop.run_in_executor(None, record_with_ytdlp, username)
            
        if not uploader_task:
            uploader_task = asyncio.create_task(upload_segments(username))

    @client.on(DisconnectEvent)
    async def on_disconnect(_):
        print(f"[ℹ️] @{username} disconnected — stopping tasks.")
        await send_bot_msg(f"⏹️ @{username} is now OFFLINE. Recording stopped.")
        stop_tasks()
        
    while True:
        try:
            await client.start()
        except AttributeError as e:
            if "ping_loop" in str(e):
                print(f"[ℹ️] Swallowed ping_loop bug for @{username}")
                await asyncio.sleep(CHECK_OFFLINE)
                continue
            else:
                print(f"[!] @{username} AttributeError: {e}")
                stop_tasks()
                await asyncio.sleep(CHECK_OFFLINE)
        except Exception as e:
            err = str(e).lower()
            if "rate_limit" in err:
                print(f"[!] @{username} hit rate limit — waiting 5 min.")
                stop_tasks()
                await asyncio.sleep(300)
            elif "userofflineerror" in err:
                print(f"[ℹ️] @{username} offline — retry in {CHECK_OFFLINE}s.")
                stop_tasks()
                await asyncio.sleep(CHECK_OFFLINE)
            elif "one connection per client" in err:
                print(f"[ℹ️] @{username} already connected — skipping duplicate.")
                await asyncio.sleep(CHECK_OFFLINE)
            else:
                print(f"[!] @{username} error:", e)
                stop_tasks()
                await asyncio.sleep(CHECK_OFFLINE)

async def main():
    if not all([TG_API_ID, TG_API_HASH, TG_BOT_TOKEN, MY_USER_ID]):
        print("❌ FATAL: One or more Telegram credentials are missing. Please fill in the variables in Section 1.")
        return
        
    if not os.path.exists(USERS_FILE):
        print("❌ users.txt not found. Please create a file with one username per line.")
        return
        
    os.makedirs('./temp', exist_ok=True)
    
    with open(USERS_FILE) as f:
        users = [u.strip() for u in f if u.strip() and not u.startswith('#')]
    
    if not users:
        print("❌ users.txt is empty. Add TikTok usernames.")
        return

    # Initialize the single, global Telegram client before starting loops
    await initialize_telegram_client()
    
    print(f"🔥 Monitoring {len(users)} TikTok users…")
    
    await asyncio.gather(*(watch_user(u) for u in users))

if __name__ == "__main__":
    def handle_sigterm(*args):
        print("\nSIGTERM received, shutting down...")
        
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    except Exception as e:
        print(f"Unhandled fatal error: {e}")

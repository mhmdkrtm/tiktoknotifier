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
# 1. DIRECT VARIABLE INSERTION (Customize these values) ⚠️
# ====================================================================

# --- Telegram Secrets ---
# NOTE: Replace the placeholder values below with your actual credentials.
TG_API_ID = 20196111               # ⚠️ YOUR TELEGRAM API ID
TG_API_HASH = "05b184f5623850b5666c32e14e7a888b"     # ⚠️ YOUR TELEGRAM API HASH
TG_BOT_TOKEN = "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"        # ⚠️ YOUR TELEGRAM BOT TOKEN
MY_USER_ID = 1280121045            # ⚠️ YOUR PERSONAL CHAT ID (Must have started the bot)

# --- General Config ---
SEGMENT_DURATION_SECONDS = 30   # 🎯 SET TO 30 SECONDS FOR TESTING 🎯
CHECK_OFFLINE = 30              # Seconds to wait when user is offline
NOTIFY_COOLDOWN = 600           # Cooldown for live notifications (10 min)
USERS_FILE = 'users.txt'        # File containing usernames

# --- Recorder Reconnect Logic ---
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_WAIT_SECONDS = 15
DISCONNECT_GRACE_PERIOD = 30    # 30 seconds to record after streamer leaves

# --- Storage Paths ---
VIDEO_PATH_TEMPLATE = './temp/{username}_segment.mp4'

# --- Trackers (Global State) ---
last_notification_time = {}
is_recording_active = {} 
last_disconnect_time = {}       # NEW: Tracks when disconnect event occurred
telegram_client = None


# ====================================================================
# 2. CORE FUNCTIONS: Telegram Client & Notifier
# ====================================================================

async def initialize_telegram_client():
    """Initializes the single, global Telethon client."""
    global telegram_client
    if telegram_client is None:
        print("[ℹ️] Initializing Telegram Client...")
        client = TelegramClient('session_name', TG_API_ID, TG_API_HASH)
        try:
            await client.start(bot_token=TG_BOT_TOKEN)
            telegram_client = client
            print("[✅] Telegram Client connected successfully.")
        except SessionPasswordNeededError:
            print("[❌] ERROR: 2FA is enabled. Telethon requires user setup.")
            raise
        except RPCError as e:
            print(f"[❌] FATAL RPC Error during connection: {e}")
            raise

async def send_bot_msg(message):
    """Sends message using the async Telethon client for notifications."""
    global telegram_client
    # If the client is not yet initialized (e.g., failed startup), try once
    if telegram_client is None:
        try:
            await initialize_telegram_client()
        except:
            print("[❌] Failed to initialize Telegram client for notification. Check credentials.")
            return

    try:
        # Sends message to the defined MY_USER_ID
        await telegram_client.send_message(MY_USER_ID, message)
        print(f"[✅] Telegram Notification sent.")
    except Exception as e:
        print(f"[❌] Failed to send Telegram message to {MY_USER_ID}: {e}")

# ====================================================================
# 3. CORE FUNCTIONS: Recording and Uploading
# ====================================================================

def record_with_ytdlp(username):
    """
    Synchronous function that manages segmented recording, 
    now handling the 30s grace period and retry logic.
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
        
        # --- FIXED COMMAND using your working yt-dlp options ---
        command = [
            'yt-dlp',
            '--wait-for-video', '60',
            '-f', 'bestvideo[height<=720]+bestaudio/best',
            '--output', video_path, 
            tiktok_url
        ]
        
        try:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            
            start_time = time.time()
            
            # --- NEW MONITORING LOOP LOGIC ---
            while True:
                time.sleep(1)
                current_time = time.time()
                
                # Condition 1: Check if the segment is over the max duration
                if current_time - start_time >= SEGMENT_DURATION_SECONDS:
                    break
                    
                # Condition 2: Check for external disconnect event (grace period)
                if username in last_disconnect_time:
                    if current_time - last_disconnect_time[username] >= DISCONNECT_GRACE_PERIOD:
                        print(f"[INFO] Disconnect grace period ({DISCONNECT_GRACE_PERIOD}s) elapsed. Forcing segment stop.")
                        break
                        
                # Condition 3: Check if yt-dlp quit unexpectedly
                if process.poll() is not None:
                    print(f"[WARNING] yt-dlp quit early (Code: {process.returncode}). Breaking loop.")
                    break
                    
                # Condition 4: Stop if the overall flag is turned off externally (e.g., app shutdown)
                if not is_recording_active.get(username, False):
                    break
            
            # --- Robust Termination ---
            if process.poll() is None:
                print("Terminating process...")
                process.send_signal(signal.SIGINT)
                
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            
            # Capture any remaining stderr and check for errors
            stdout, stderr = process.communicate()
            if stderr:
                 print(f"[YT-DLP DEBUG/ERROR] @{username}: {stderr.decode().strip()}")

            # --- Check Result and Decide Next Action ---
            if os.path.exists(video_path) and os.path.getsize(video_path) > 1024 * 10:
                print(f"[✅] Segment recording succeeded. File size: {os.path.getsize(video_path) / (1024*1024):.2f}MB")
                consecutive_failures = 0
                
                # If finished during grace period, force exit
                if username in last_disconnect_time:
                    is_recording_active[username] = False 
                    del last_disconnect_time[username] 
            else:
                # --- Failure Logic: Retry or Exit ---
                if username in last_disconnect_time:
                    print(f"[INFO] File too small during grace period. Assuming stream is fully dead.")
                    is_recording_active[username] = False
                    del last_disconnect_time[username]
                else:
                    print(f"[⚠️] Recording failed or file too small. Retrying...")
                    consecutive_failures += 1
                    if consecutive_failures < MAX_RECONNECT_ATTEMPTS:
                        time.sleep(RECONNECT_WAIT_SECONDS)
                        continue
                    else:
                        print(f"[❌] Max reconnection attempts reached. Stopping recording for @{username}.")
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
            
    print(f"@{username} Recording loop stopped.")


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
        nonlocal recording_task, uploader_task
        print(f"[⚠️] @{username} disconnected. Allowing {DISCONNECT_GRACE_PERIOD}s grace period for segment to finish.")
        
        # Record disconnect time, DO NOT set is_recording_active=False yet.
        last_disconnect_time[username] = time.time()
        
        # Notify user that the stream is offline but we are waiting for the final segment
        await send_bot_msg(f"⏸️ @{username} is now OFFLINE. Finishing current segment (Grace Period: {DISCONNECT_GRACE_PERIOD}s)...")
        
        # The stop_tasks will be called by the recorder when the grace period or max attempts are reached.
        
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
    # Final check for required variables
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
    try:
        await initialize_telegram_client()
    except Exception:
        print("Exiting due to critical Telegram connection failure.")
        return
        
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

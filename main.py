import asyncio
import time
import os
import subprocess
import signal
from tiktok_live.client import TikTokLiveClient
from tiktok_live.events import ConnectEvent, DisconnectEvent
from telethon import TelegramClient

# ====================================================================
# 1. DIRECT VARIABLE INSERTION (Customize these values) ⚠️
# ====================================================================

# --- Telegram Secrets (Insert Your Credentials Directly) ---
TG_API_ID = 20196111               # ⚠️ YOUR TELEGRAM API ID (from my.telegram.org)
TG_API_HASH = "05b184f5623850b5666c32e14e7a888b"     # ⚠️ YOUR TELEGRAM API HASH
TG_BOT_TOKEN = "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"        # ⚠️ YOUR TELEGRAM BOT TOKEN
MY_USER_ID = 1280121045            # ⚠️ YOUR PERSONAL CHAT ID (to send to Saved Messages)

# --- General Config ---
SEGMENT_DURATION_SECONDS = 10  # 10 minutes (600 seconds)
CHECK_OFFLINE = 30              # Seconds to wait when user is offline
NOTIFY_COOLDOWN = 600           # Cooldown for live notifications (10 min)
USERS_FILE = 'users.txt'        # File containing usernames

# --- Storage Paths ---
# Path for the temporary video segment on Railway's ephemeral disk
VIDEO_PATH_TEMPLATE = './temp/{username}_segment.mp4'

# --- Trackers (Global State) ---
last_notification_time = {}
is_recording_active = {} 

# Dummy function for sending simple messages (replace with your actual implementation)
def send_bot_msg(message):
    # In a fully deployed bot, you might use Telethon here too, 
    # but for simplicity, we'll keep the print for the notification message.
    print(f"[TG] {message}")


# ====================================================================
# 2. CORE FUNCTIONS: Recording and Uploading (No changes needed here)
# ====================================================================

def record_with_ytdlp(username):
    """
    Synchronous function called by an executor. 
    It loops to record 10-minute segments until the 'is_recording_active' flag is False.
    """
    video_path = VIDEO_PATH_TEMPLATE.format(username=username)
    os.makedirs(os.path.dirname(video_path), exist_ok=True)
    tiktok_url = f"https://www.tiktok.com/@{username}/live"
    segment_count = 0
    
    if os.path.exists(video_path):
        os.remove(video_path)

    while is_recording_active.get(username, False):
        segment_count += 1
        print(f"--- @{username}: Starting Segment {segment_count} ---")
        
        command = [
            'yt-dlp',
            '--no-playlist', 
            '--live-from-start',
            '-f', 'best',
            '--output', video_path, 
            tiktok_url
        ]
        
        try:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            start_time = time.time()
            while time.time() - start_time < SEGMENT_DURATION_SECONDS:
                if not is_recording_active.get(username, False) or process.poll() is not None:
                    break
                time.sleep(1)
            
            if process.poll() is None:
                print(f"Segment recording timed out. Terminating process...")
                process.terminate()
                time.sleep(2) 
                if process.poll() is None:
                    process.kill()
            
            if os.path.exists(video_path) and os.path.getsize(video_path) > 1024 * 10:
                print(f"Segment recording for @{username} stopped. File size: {os.path.getsize(video_path) / (1024*1024):.2f}MB")
            else:
                print(f"Recording failed or file too small for @{username}. Live may have ended.")
                is_recording_active[username] = False
            
        except FileNotFoundError:
            print("[❌] ERROR: 'yt-dlp' or 'ffmpeg' command not found. Ensure they are installed on Railway!")
is_recording_active[username] = False
            break
        except Exception as e:
            print(f"[!] @{username} Error during recording segment: {e}")
            is_recording_active[username] = False
            
    print(f"@{username} Recording loop stopped.")


async def upload_segments(username):
    """
    Asynchronous task that monitors the disk for completed segments, 
    uploads them to Telegram, and deletes them.
    """
    video_path = VIDEO_PATH_TEMPLATE.format(username=username)

    # Telethon client uses the global constants defined above
    client = TelegramClient('session_name', TG_API_ID, TG_API_HASH)

    try:
        await client.start(bot_token=TG_BOT_TOKEN) 
        
        while is_recording_active.get(username, False):
            await asyncio.sleep(5)
            
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                print(f"[⬆️] @{username}: Segment ready, starting upload...")
                
                try:
                    await client.send_file(
                        MY_USER_ID, 
                        video_path, 
                        caption=f"TikTok Live: @{username} Segment {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
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
    finally:
        await client.disconnect()

# ====================================================================
# 3. TIKTOK LISTENER AND MAIN LOOP (No functional changes needed)
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
            send_bot_msg(f"🔴 @{username} is LIVE! Recording started.")
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

    print(f"🔥 Monitoring {len(users)} TikTok users…")
    
    await asyncio.gather(*(watch_user(u) for u in users))

if name == "main":
    def handle_sigterm(*args):
        print("\nSIGTERM received, shutting down...")
        
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user.")
    except Exception as e:
        print(f"Unhandled fatal error: {e}")

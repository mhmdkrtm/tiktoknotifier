import os
import asyncio
import subprocess
from pathlib import Path
from notify import send_message
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
from TikTokLive.client.errors import UserOfflineError, AgeRestrictedError

# ================= SETTINGS =================
ACCOUNTS_FILE = Path("accounts.txt")
TMP_DIR = Path("/app/downloads")
RCLONE_REMOTE = "gdrive:tiktok"
WAIT_FOR_LIVE = 300  # 5 minutes

SESSION_ID = os.getenv("SESSION_ID")
TT_TARGET_IDC = os.getenv("TT_TARGET_IDC")
TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
# ============================================

if not ACCOUNTS_FILE.exists():
    print(f"⚠️ {ACCOUNTS_FILE} not found. Exiting.")
    usernames = []
else:
    with open(ACCOUNTS_FILE, "r") as f:
        usernames = [line.strip() for line in f if line.strip()]

TMP_DIR.mkdir(parents=True, exist_ok=True)

# ===== Helper functions =====
def run_cmd(cmd, capture_output=False):
    print(f"▶️ Running: {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=capture_output, text=True)

def upload_to_drive(filepath):
    result = run_cmd(f"rclone move '{filepath}' {RCLONE_REMOTE} -v")
    return result.returncode == 0

def get_video_length(file_path):
    try:
        cmd = f'yt-dlp --print "%(duration_string)s" "{file_path}"'
        result = run_cmd(cmd, capture_output=True)
        duration = result.stdout.strip()
        return duration if duration else "unknown"
    except:
        return "unknown"

# ===== Monitor & record per account =====
async def monitor_account(username):
    client = TikTokLiveClient(unique_id=username)
    
    # Set session for age-restricted lives
    if SESSION_ID and TT_TARGET_IDC:
        client.web.set_session(SESSION_ID, TT_TARGET_IDC)
    
    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        print(f"Connected to @{username} (Room ID: {client.room_id})")
        send_message(f"🔔 @{username} is LIVE! Recording starting...")

        timestamp = asyncio.get_event_loop().time()
        filename = TMP_DIR / f"{username}_{int(timestamp)}.mp4"

        # Try yt-dlp first
        success = run_cmd(
            f'yt-dlp -o "{filename}" https://www.tiktok.com/@{username}/live',
        ).returncode == 0

        # If yt-dlp fails, fallback to ffmpeg
        if not success:
            send_message(f"⚠️ yt-dlp failed for @{username}, trying ffmpeg...")
            success = run_cmd(
                f'ffmpeg -y -i https://www.tiktok.com/@{username}/live -c copy "{filename}"'
            ).returncode == 0

        if success:
            duration = get_video_length(filename)
            send_message(f"✅ Recording finished: {filename.name}\n⏱ Length: {duration}")

            if upload_to_drive(filename):
                send_message(f"☁️ Uploaded {filename.name} to Google Drive successfully.")
                try:
                    filename.unlink()
                    print(f"🗑 Deleted local file {filename.name}")
                except Exception as e:
                    print(f"⚠️ Failed to delete {filename.name}: {e}")
            else:
                send_message(f"⚠️ Upload failed for {filename.name}.")
        else:
            send_message(f"❌ Recording failed for @{username}.")

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent):
        print(f"Disconnected from @{username} live.")
    
    try:
        await client.start()  # non-blocking
    except UserOfflineError:
        print(f"⚠️ @{username} is offline. Skipping.")
    except AgeRestrictedError:
        print(f"⚠️ @{username} is age-restricted. Recording attempt requires SESSION_ID & TT_TARGET_IDC.")
    except Exception as e:
        print(f"❌ Error with @{username}: {e}")

# ===== Main =====
async def main():
    tasks = [monitor_account(u) for u in usernames]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

import os
import time
import subprocess
import threading
import asyncio
from datetime import datetime
from pathlib import Path
from notify import send_message
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, LiveEndEvent
from TikTokLive.client.errors import UserOfflineError, AgeRestrictedError

# ================= SETTINGS =================
ACCOUNTS_FILE = Path("/app/accounts.txt")
CHECK_INTERVAL = 600  # 10 minutes
TMP_DIR = Path("/app/downloads")
RCLONE_REMOTE = "gdrive:tiktok"
WAIT_FOR_LIVE = 300  # 5 minutes
SESSION_ID = os.getenv("SESSION_ID")  # Railway env variable
# ============================================

TMP_DIR.mkdir(parents=True, exist_ok=True)

# ===== Read accounts =====
if not ACCOUNTS_FILE.exists():
    print(f"⚠️ {ACCOUNTS_FILE} not found. Exiting.")
    usernames = []
else:
    with open(ACCOUNTS_FILE, "r") as f:
        usernames = [line.strip() for line in f.readlines() if line.strip()]

if not usernames:
    print("⚠️ No accounts to monitor. Exiting.")
    exit(1)

# ===== Write RCLONE_CONFIG to file =====
rclone_conf_path = Path("/root/.config/rclone/rclone.conf")
rclone_conf_path.parent.mkdir(parents=True, exist_ok=True)
rclone_conf_content = os.getenv("RCLONE_CONFIG")
if not rclone_conf_content:
    print("⚠️ RCLONE_CONFIG env variable is empty. Exiting.")
    exit(1)

with open(rclone_conf_path, "w") as f:
    f.write(rclone_conf_content)
print("✅ rclone.conf written successfully")

# ===== Helper functions =====
def run_cmd(cmd, capture_output=False):
    print(f"▶️ Running: {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=capture_output, text=True)

def get_video_length(file_path):
    try:
        cmd = f'yt-dlp --print "%(duration_string)s" "{file_path}"'
        result = run_cmd(cmd, capture_output=True)
        duration = result.stdout.strip()
        return duration if duration else "unknown"
    except:
        return "unknown"

def upload_to_drive(filepath):
    result = run_cmd(f"rclone move '{filepath}' {RCLONE_REMOTE} -v")
    return result.returncode == 0

async def monitor_account(username):
    client = TikTokLiveClient(unique_id=username)
    # Pass sessionid to access age-restricted lives
    if SESSION_ID:
        client.web.set_session(SESSION_ID)

    while True:
        try:
            is_live = await client.is_live()
        except UserOfflineError:
            print(f"❌ @{username} is offline. Skipping.")
            await asyncio.sleep(CHECK_INTERVAL)
            continue
        except AgeRestrictedError:
            print(f"⚠️ @{username} is age-restricted. Using session ID if provided.")
            if not SESSION_ID:
                await asyncio.sleep(CHECK_INTERVAL)
                continue
            try:
                is_live = await client.is_live()
            except Exception as e:
                print(f"⚠️ Failed to fetch age-restricted live: {e}")
                await asyncio.sleep(CHECK_INTERVAL)
                continue

        if is_live:
            send_message(f"🎥 @{username} is LIVE! Recording started...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = TMP_DIR / f"{username}_{timestamp}.mp4"

            # ===== Try yt-dlp first =====
            success = run_cmd(
                f'yt-dlp --wait-for-video {WAIT_FOR_LIVE} -o "{filename}" https://www.tiktok.com/@{username}/live'
            ).returncode == 0

            # ===== If yt-dlp fails, try ffmpeg =====
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
                send_message(f"❌ Both yt-dlp and ffmpeg failed for @{username}.")
        else:
            print(f"⏸ @{username} is offline. Retrying in {CHECK_INTERVAL // 60} min.")

        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    tasks = [monitor_account(u) for u in usernames]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

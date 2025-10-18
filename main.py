import os
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime
from notify import send_message
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent

# ================= SETTINGS =================
ACCOUNTS_FILE = Path("accounts.txt")
TMP_DIR = Path("/app/downloads")
RCLONE_REMOTE = "gdrive:tiktok"
WAIT_FOR_LIVE = 300  # seconds to wait for yt-dlp
CHECK_INTERVAL = 600  # 10 minutes
# ============================================

TMP_DIR.mkdir(parents=True, exist_ok=True)

# ===== Read accounts =====
if not ACCOUNTS_FILE.exists():
    print(f"⚠️ {ACCOUNTS_FILE} not found. Exiting.")
    usernames = []
else:
    usernames = [line.strip() for line in ACCOUNTS_FILE.read_text().splitlines() if line.strip()]

if not usernames:
    print("ℹ️ No accounts found in accounts.txt. Exiting.")
    exit(1)

# ===== Rclone config =====
rclone_conf_content = os.getenv("RCLONE_CONFIG")
if not rclone_conf_content:
    print("⚠️ RCLONE_CONFIG env variable is empty. Exiting.")
    exit(1)

rclone_conf_path = Path("/root/.config/rclone/rclone.conf")
rclone_conf_path.parent.mkdir(parents=True, exist_ok=True)
with open(rclone_conf_path, "w") as f:
    f.write(rclone_conf_content)
print("✅ rclone.conf written successfully")

# ===== Helper functions =====
def run_cmd(cmd, capture_output=False):
    print(f"▶️ Running: {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=capture_output, text=True)

def get_video_length(file_path):
    try:
        result = run_cmd(f'yt-dlp --print "%(duration_string)s" "{file_path}"', capture_output=True)
        duration = result.stdout.strip()
        return duration if duration else "unknown"
    except:
        return "unknown"

def upload_to_drive(filepath):
    result = run_cmd(f"rclone move '{filepath}' {RCLONE_REMOTE} -v")
    return result.returncode == 0

async def record_live(username: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = TMP_DIR / f"{username}_{timestamp}.mp4"
    
    # ===== Try yt-dlp first =====
    success = run_cmd(
        f'yt-dlp --wait-for-video {WAIT_FOR_LIVE} -o "{filename}" https://www.tiktok.com/@{username}/live'
    ).returncode == 0

    # ===== Fallback to ffmpeg =====
    if not success:
        send_message(f"⚠️ yt-dlp failed for {username}, trying ffmpeg...")
        success = run_cmd(
            f'ffmpeg -y -i https://www.tiktok.com/@{username}/live -c copy "{filename}"'
        ).returncode == 0

    if success:
        send_message(f"🎥 LIVE detected for {username}! Recording started: {filename.name}")
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
        send_message(f"❌ Both yt-dlp and ffmpeg failed for {username}.")

# ===== Monitor function =====
async def monitor_account(username: str):
    client = TikTokLiveClient(unique_id=username)
    is_live = False

    async def check_live():
        nonlocal is_live
        try:
            if await client.is_live():
                if not is_live:
                    is_live = True
                    send_message(f"🟢 {username} is LIVE!")
                    await record_live(username)
            else:
                is_live = False
        except Exception as e:
            print(f"⚠️ Error checking live for {username}: {e}")

    while True:
        await check_live()
        await asyncio.sleep(CHECK_INTERVAL)

# ===== Main =====
async def main():
    tasks = [monitor_account(user) for user in usernames]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

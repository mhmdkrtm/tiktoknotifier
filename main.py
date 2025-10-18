import os
import asyncio
import subprocess
from pathlib import Path
from TikTokLive import TikTokLiveClient
import datetime
import requests

# ================= SETTINGS =================
TMP_DIR = Path("/app/downloads")
RCLONE_REMOTE = "gdrive:tiktok"
WAIT_FOR_LIVE = 300  # seconds to wait for yt-dlp recording
ACCOUNTS_FILE = "accounts.txt"
# ============================================

TMP_DIR.mkdir(parents=True, exist_ok=True)

# ===== Environment variables =====
TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
RCLONE_CONFIG_CONTENT = os.getenv("RCLONE_CONFIG")
if not (TG_TOKEN and CHAT_ID and RCLONE_CONFIG_CONTENT):
    print("⚠️ TG_TOKEN, CHAT_ID, or RCLONE_CONFIG not set. Exiting.")
    exit(1)

# ===== Write rclone config =====
rclone_conf_path = Path("/root/.config/rclone/rclone.conf")
rclone_conf_path.parent.mkdir(parents=True, exist_ok=True)
with open(rclone_conf_path, "w") as f:
    f.write(RCLONE_CONFIG_CONTENT)
print("✅ rclone.conf written successfully")

# ===== Helper functions =====
def send_message(message: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except Exception as e:
        print(f"⚠️ Failed to send Telegram message: {e}")

def run_cmd(cmd):
    print(f"▶️ Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode == 0

def get_video_length(file_path):
    try:
        result = subprocess.run(
            f'yt-dlp --print "%(duration_string)s" "{file_path}"',
            shell=True,
            capture_output=True,
            text=True
        )
        duration = result.stdout.strip()
        return duration if duration else "unknown"
    except:
        return "unknown"

def upload_to_drive(filepath):
    return run_cmd(f"rclone move '{filepath}' {RCLONE_REMOTE} -v")

def read_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        print(f"{ACCOUNTS_FILE} not found!")
        return []
    with open(ACCOUNTS_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

# ===== Recording function =====
def record_live(account):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = TMP_DIR / f"{account}_{timestamp}.mp4"

    # Try yt-dlp first
    success = run_cmd(f'yt-dlp --wait-for-video {WAIT_FOR_LIVE} -o "{filename}" https://www.tiktok.com/@{account}/live')

    # Fallback to ffmpeg
    if not success:
        send_message(f"⚠️ yt-dlp failed for {account}, trying ffmpeg...")
        success = run_cmd(f'ffmpeg -y -i https://www.tiktok.com/@{account}/live -c copy "{filename}"')

    if success:
        send_message(f"🎥 LIVE detected for {account}! Recording started: {filename.name}")
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
        send_message(f"❌ Both yt-dlp and ffmpeg failed for {account}.")

# ===== TikTok Live listener =====
async def start_listener(account):
    client = TikTokLiveClient(unique_id=account)

    @client.on("live_start")
    async def on_live_start(event):
        send_message(f"🔔 {account} just went LIVE! Recording...")
        # Run recording in a separate thread to not block async loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, record_live, account)

    await client.run()

# ===== Main =====
async def main():
    accounts = read_accounts()
    if not accounts:
        print("No accounts to monitor. Exiting.")
        return

    tasks = [start_listener(account) for account in accounts]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

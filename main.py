import os
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, LiveEndEvent
from notify import send_message

# ================= SETTINGS =================
ACCOUNTS_FILE = Path("accounts.txt")
TMP_DIR = Path("/app/downloads")
RCLONE_REMOTE = "gdrive:tiktok"
WAIT_FOR_LIVE = 300  # seconds
YTDLP_IMPERSONATE = "chrome-116"  # check with yt-dlp --list-impersonate-targets
# ============================================

TMP_DIR.mkdir(parents=True, exist_ok=True)

# Read accounts.txt
if not ACCOUNTS_FILE.exists():
    print(f"⚠️ {ACCOUNTS_FILE} not found. Exiting.")
    exit(1)

with open(ACCOUNTS_FILE, "r") as f:
    usernames = [line.strip() for line in f if line.strip()]

if not usernames:
    print("⚠️ No usernames found in accounts.txt. Exiting.")
    exit(1)

# Write rclone config from env variable
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

def upload_to_drive(filepath):
    result = run_cmd(f"rclone move '{filepath}' {RCLONE_REMOTE} -v")
    return result.returncode == 0

async def record_live(username: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = TMP_DIR / f"{username}_{timestamp}.mp4"

    # Try yt-dlp first with impersonation
    result = run_cmd(
        f'yt-dlp --wait-for-video {WAIT_FOR_LIVE} --impersonate "{YTDLP_IMPERSONATE}" -o "{filename}" https://www.tiktok.com/@{username}/live'
    )

    # If yt-dlp fails, fallback to ffmpeg
    if result.returncode != 0:
        print(f"⚠️ yt-dlp failed for {username}, trying ffmpeg...")
        result = run_cmd(
            f'ffmpeg -y -i https://www.tiktok.com/@{username}/live -c copy "{filename}"'
        )

    if result.returncode == 0:
        send_message(f"🎥 Recording finished: {filename.name}")
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

# ===== TikTokLive listeners =====
async def start_listener(username: str):
    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        print(f"✅ Connected to @{event.unique_id} (Room ID: {client.room_id})")
        # Check if live
        try:
            if await client.is_live():
                send_message(f"🔴 @{username} is LIVE!")
                await record_live(username)
        except Exception as e:
            print(f"⚠️ Error checking live status for {username}: {e}")

    @client.on(LiveEndEvent)
    async def on_live_end(event: LiveEndEvent):
        print(f"⚪ @{username} live ended.")

    await client.start()  # non-blocking

# ===== Main =====
async def main():
    tasks = [start_listener(u) for u in usernames]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

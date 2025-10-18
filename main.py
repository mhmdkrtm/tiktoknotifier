import os
import asyncio
import subprocess
from pathlib import Path
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
from TikTokLive.client.errors import UserNotFoundError
from notify import send_message

# ========== CONFIG ==========
ACCOUNTS_FILE = Path("accounts.txt")  # file with TikTok usernames
TMP_DIR = Path("/app/downloads")      # temporary storage
RCLONE_REMOTE = "gdrive:tiktok"       # rclone remote
WAIT_FOR_LIVE = 5 * 60                # seconds to wait for live recording
CHECK_INTERVAL = 600                   # seconds between checks
# ============================

# Ensure TMP_DIR exists
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Write rclone config
rclone_conf_path = Path("/root/.config/rclone/rclone.conf")
rclone_conf_path.parent.mkdir(parents=True, exist_ok=True)
rclone_conf_content = os.getenv("RCLONE_CONFIG")
if not rclone_conf_content:
    print("⚠️ RCLONE_CONFIG env variable is empty. Exiting.")
    exit(1)
with open(rclone_conf_path, "w") as f:
    f.write(rclone_conf_content)
print("✅ rclone.conf written successfully")


def run_cmd(cmd: str, capture_output=False):
    """Run shell command"""
    print(f"▶️ Running: {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=capture_output, text=True)


def upload_to_drive(filepath: Path):
    """Move file to Google Drive using rclone"""
    result = run_cmd(f"rclone move '{filepath}' {RCLONE_REMOTE} -v")
    return result.returncode == 0


async def monitor_account(username: str):
    """Monitor a single TikTok account"""
    client = TikTokLiveClient(unique_id=username)

    # Try connecting to the account to see if it exists
    try:
        is_live = await client.is_live()
    except UserNotFoundError:
        print(f"⚠️ {username} cannot go live or does not exist. Skipping.")
        return

    if not is_live:
        print(f"ℹ️ {username} is currently offline.")
        return

    send_message(f"🎥 {username} is LIVE! Starting recording...")
    timestamp = asyncio.get_event_loop().time()
    filename = TMP_DIR / f"{username}_{int(timestamp)}.mp4"

    # Try yt-dlp first
    result = run_cmd(
        f'yt-dlp -o "{filename}" https://www.tiktok.com/@{username}/live', capture_output=True
    )
    success = result.returncode == 0

    # If yt-dlp fails, fallback to ffmpeg
    if not success:
        send_message(f"⚠️ yt-dlp failed for {username}, trying ffmpeg...")
        result = run_cmd(
            f'ffmpeg -y -i https://www.tiktok.com/@{username}/live -c copy "{filename}"', capture_output=True
        )
        success = result.returncode == 0

    if success:
        send_message(f"✅ Recording finished: {filename.name}")
        if upload_to_drive(filename):
            send_message(f"☁️ Uploaded {filename.name} to Google Drive successfully.")
            try:
                filename.unlink()
                print(f"🗑 Deleted local file {filename.name}")
            except Exception as e:
                print(f"⚠️ Failed to delete {filename.name}: {e}")
        else:
            send_message(f"❌ Upload failed for {filename.name}.")
    else:
        send_message(f"❌ Recording failed for {username}.")


async def main():
    """Main loop to check all accounts periodically"""
    if not ACCOUNTS_FILE.exists():
        print(f"⚠️ {ACCOUNTS_FILE} not found. Exiting.")
        return

    usernames = [line.strip() for line in ACCOUNTS_FILE.read_text().splitlines() if line.strip()]

    while True:
        tasks = [monitor_account(username) for username in usernames]
        await asyncio.gather(*tasks)
        print(f"⏱ Sleeping for {CHECK_INTERVAL} seconds before next check...")
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())

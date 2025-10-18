import os
import asyncio
import subprocess
from pathlib import Path
from notify import send_message
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, LiveEndEvent

# ================= SETTINGS =================
ACCOUNTS_FILE = Path("accounts.txt")
TMP_DIR = Path("/app/downloads")
RCLONE_REMOTE = "gdrive:tiktok"
WAIT_FOR_LIVE = 300  # seconds
# ============================================

TMP_DIR.mkdir(parents=True, exist_ok=True)

# ===== Read accounts =====
if not ACCOUNTS_FILE.exists():
    print(f"⚠️ {ACCOUNTS_FILE} not found. Exiting.")
    usernames = []
else:
    with open(ACCOUNTS_FILE, "r") as f:
        usernames = [line.strip() for line in f if line.strip()]

if not usernames:
    print("⚠️ No usernames found in accounts.txt. Exiting.")
    exit(1)

# ===== Write rclone config =====
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

async def record_live(username: str):
    timestamp = asyncio.get_running_loop().time()
    filename = TMP_DIR / f"{username}_{int(timestamp)}.mp4"

    # Try yt-dlp first
    result = run_cmd(
        f'yt-dlp --wait-for-video {WAIT_FOR_LIVE} -o "{filename}" https://www.tiktok.com/@{username}/live'
    )

    if result.returncode != 0:
        send_message(f"⚠️ yt-dlp failed for {username}, trying ffmpeg...")
        result = run_cmd(
            f'ffmpeg -y -i https://www.tiktok.com/@{username}/live -c copy "{filename}"'
        )

    if result.returncode == 0:
        send_message(f"🎥 Recording finished for {username}: {filename.name}")
        # Upload
        upload_result = run_cmd(f"rclone move '{filename}' {RCLONE_REMOTE} -v")
        if upload_result.returncode == 0:
            send_message(f"☁️ Uploaded {filename.name} to Google Drive successfully.")
            try:
                filename.unlink()
                print(f"🗑 Deleted local file {filename.name}")
            except Exception as e:
                print(f"⚠️ Failed to delete {filename.name}: {e}")
        else:
            send_message(f"⚠️ Upload failed for {filename.name}.")
    else:
        send_message(f"❌ Recording failed for {username}.")


# ===== Listener per account =====
async def start_listener(username: str):
    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        print(f"✅ Connected to @{event.unique_id} (Room ID: {client.room_id})")
        try:
            if await client.is_live():
                send_message(f"🔴 @{username} is LIVE!")
                await record_live(username)
        except Exception as e:
            print(f"⚠️ Error checking live status for {username}: {e}")

    @client.on(LiveEndEvent)
    async def on_live_end(event: LiveEndEvent):
        print(f"⚪ @{username} live ended.")

    # Run client in background
    loop = asyncio.get_running_loop()
    loop.create_task(client.connect(fetch_room_info=True))

# ===== Main =====
async def main():
    tasks = [start_listener(u) for u in usernames]
    await asyncio.gather(*tasks)

    # Keep the script alive
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())

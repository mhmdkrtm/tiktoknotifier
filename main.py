import os
import asyncio
import subprocess
from pathlib import Path
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, LiveEndEvent
from TikTokLive.client.errors import UserOfflineError, AgeRestrictedError
from notify import send_message

# ================= SETTINGS =================
ACCOUNTS_FILE = Path("accounts.txt")
TMP_DIR = Path("/app/downloads")
RCLONE_REMOTE = os.getenv("RCLONE_REMOTE", "gdrive:tiktok")
WAIT_FOR_LIVE = 300  # seconds to wait for yt-dlp
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
    print("⚠️ No accounts found in accounts.txt. Exiting.")
    exit(1)

# ===== Helper functions =====
def run_cmd(cmd, capture_output=False):
    print(f"▶️ Running: {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=capture_output, text=True)

def upload_to_drive(filepath):
    result = run_cmd(f"rclone move '{filepath}' {RCLONE_REMOTE} -v")
    return result.returncode == 0

async def record_live(username: str, room_url: str):
    timestamp = Path(username + "_" + asyncio.get_event_loop().time().__str__())
    filename = TMP_DIR / f"{username}_{int(asyncio.get_event_loop().time())}.mp4"

    # Try yt-dlp first
    cmd_yt = f'yt-dlp -o "{filename}" {room_url}'
    success = run_cmd(cmd_yt).returncode == 0

    # Fallback to ffmpeg
    if not success:
        send_message(f"⚠️ yt-dlp failed for {username}, trying ffmpeg...")
        cmd_ff = f'ffmpeg -y -i {room_url} -c copy "{filename}"'
        success = run_cmd(cmd_ff).returncode == 0

    if success:
        send_message(f"🎥 Recording started for @{username}: {filename.name}")

        # Upload
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
        send_message(f"❌ Failed to record live for @{username}.")

# ===== Listener per account =====
async def start_listener(username: str):
    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        try:
            is_live = await client.is_live()
            if is_live:
                send_message(f"🔴 @{username} is LIVE!")
                room_url = f"https://www.tiktok.com/@{username}/live"
                await record_live(username, room_url)
            else:
                print(f"⚪ @{username} connected but not live.")
        except Exception as e:
            print(f"⚠️ Error checking live for @{username}: {e}")

    @client.on(LiveEndEvent)
    async def on_live_end(event: LiveEndEvent):
        print(f"⚪ @{username} live ended.")

    # Run client with exception handling
    try:
        await client.start(fetch_room_info=True)
    except UserOfflineError:
        print(f"⚪ @{username} is offline.")
    except AgeRestrictedError:
        print(f"⚠️ @{username} is age-restricted. Skipping.")
    except Exception as e:
        print(f"❌ Unexpected error for @{username}: {e}")

# ===== Main =====
async def main():
    tasks = [start_listener(username) for username in usernames]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

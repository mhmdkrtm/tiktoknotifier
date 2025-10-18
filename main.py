import asyncio
import os
import subprocess
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, LiveEndEvent
from notify import send_message

DOWNLOAD_DIR = "/app/downloads"
RCLONE_REMOTE = "gdrive:/TikTokLives/"

# ===== RCLONE config =====
def write_rclone_config():
    rclone_config = os.getenv("RCLONE_CONFIG")
    if not rclone_config:
        print("⚠️ RCLONE_CONFIG not set")
        return
    config_path = "/root/.config/rclone/rclone.conf"
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        f.write(rclone_config)
    print("✅ rclone.conf written successfully")

# ===== Record live =====
def record_live(account):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    filename = f"{DOWNLOAD_DIR}/{account}.mp4"

    try:
        subprocess.run([
            "yt-dlp",
            "--format", "bestvideo+bestaudio",
            "--merge-output-format", "mp4",
            "--output", filename,
            f"https://www.tiktok.com/@{account}/live"
        ], check=True)
        print(f"✅ yt-dlp finished recording {account}")
    except subprocess.CalledProcessError:
        print(f"⚠️ yt-dlp failed for {account}, trying ffmpeg...")
        try:
            subprocess.run([
                "ffmpeg",
                "-i", f"https://www.tiktok.com/@{account}/live",
                "-c:v", "libx264",
                "-c:a", "aac",
                filename
            ], check=True)
            print(f"✅ ffmpeg finished recording {account}")
        except subprocess.CalledProcessError:
            print(f"❌ Both yt-dlp and ffmpeg failed for {account}")
            return

    upload_to_gdrive(filename, account)

# ===== Upload and cleanup =====
def upload_to_gdrive(file_path, account):
    try:
        subprocess.run([
            "rclone", "copy", file_path, RCLONE_REMOTE
        ], check=True)
        print(f"☁️ Uploaded {account} successfully")
        cleanup(file_path, account)
    except subprocess.CalledProcessError:
        print(f"❌ Failed to upload {account}")

def cleanup(file_path, account):
    try:
        os.remove(file_path)
        print(f"🗑 Deleted {account} locally")
        send_message(f"✅ {account} live recording and upload completed successfully")
    except Exception as e:
        print(f"⚠️ Failed to delete {account}: {e}")

# ===== Listener per account =====
async def start_listener(account):
    client = TikTokLiveClient(unique_id=account)

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        print(f"🔌 Connected to {account} live stream (Room ID: {client.room_id})")

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent):
        print(f"❌ Disconnected from {account}")

    @client.on(LiveEndEvent)
    async def on_live_end(event: LiveEndEvent):
        print(f"⏹ Live ended for {account}")

    # Check if live first
    if await client.is_live():
        send_message(f"🔔 {account} is LIVE! Recording now...")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, record_live, account)

    try:
        await client.start()  # async non-blocking
    except Exception as e:
        print(f"❌ Error connecting to {account}: {e}")

# ===== Main =====
async def main():
    write_rclone_config()
    accounts = ["account1", "account2"]  # Replace with your TikTok accounts
    tasks = [start_listener(account) for account in accounts]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

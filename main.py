import asyncio
import os
import subprocess
from TikTokLive import TikTokLiveClient
from TikTokLive.events import LiveStartEvent
from notify import send_message

# Ensure Rclone config is written
def write_rclone_config():
    rclone_config = os.getenv("RCLONE_CONFIG")
    if rclone_config:
        config_path = "/root/.config/rclone/rclone.conf"
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            f.write(rclone_config)
        print("✅ rclone.conf written successfully")
    else:
        print("⚠️ RCLONE_CONFIG not set in environment variables.")

# Record live stream using yt-dlp
def record_live(account):
    print(f"🎥 Starting recording for {account}...")
    try:
        subprocess.run(
            [
                "yt-dlp",
                "--format", "bestvideo+bestaudio",
                "--merge-output-format", "mp4",
                "--output", f"downloads/{account}.mp4",
                f"https://www.tiktok.com/@{account}/live"
            ],
            check=True
        )
        print(f"✅ Recording completed for {account}")
        upload_to_gdrive(account)
    except subprocess.CalledProcessError:
        print(f"❌ yt-dlp failed, attempting with ffmpeg for {account}...")
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", f"https://www.tiktok.com/@{account}/live",
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-strict", "experimental",
                    f"downloads/{account}.mp4"
                ],
                check=True
            )
            print(f"✅ Recording completed for {account} using ffmpeg")
            upload_to_gdrive(account)
        except subprocess.CalledProcessError:
            print(f"❌ ffmpeg failed to record {account}")

# Upload recorded video to Google Drive using rclone
def upload_to_gdrive(account):
    print(f"☁️ Uploading {account}.mp4 to Google Drive...")
    try:
        subprocess.run(
            ["rclone", "copy", f"downloads/{account}.mp4", "gdrive:/TikTokLives/"],
            check=True
        )
        print(f"✅ Upload completed for {account}")
        cleanup(account)
    except subprocess.CalledProcessError:
        print(f"❌ Upload failed for {account}")

# Clean up local files
def cleanup(account):
    print(f"🧹 Cleaning up local files for {account}...")
    try:
        os.remove(f"downloads/{account}.mp4")
        print(f"✅ Cleanup completed for {account}")
        send_message(f"✅ {account} live recording and upload completed successfully.")
    except Exception as e:
        print(f"❌ Cleanup failed for {account}: {e}")

# Start listening for live events
async def start_listener(account):
    client = TikTokLiveClient(unique_id=account)

    @client.on(LiveStartEvent)
    async def on_live_start(event):
        send_message(f"🔔 {account} just went LIVE! Recording...")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, record_live, account)

    try:
        await client.run()
    except Exception as e:
        print(f"❌ Failed to connect to {account}'s live stream: {e}")

# Main function to start the listeners
async def main():
    accounts = ["@account1", "@account2"]  # Replace with your target TikTok accounts
    write_rclone_config()
    tasks = [start_listener(account) for account in accounts]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())

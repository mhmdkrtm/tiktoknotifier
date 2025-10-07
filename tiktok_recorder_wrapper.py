import os
import asyncio
import subprocess
import time
from datetime import datetime
from telethon import TelegramClient

# Telegram setup
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", ""))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_FILE = "tg_session.session"
TMP_DIR = os.getenv("RAILWAY_TMP", "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

# Telethon client (to send videos)
tg_client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)

async def send_to_telegram(file_path):
    async with tg_client:
        await tg_client.send_file("me", file_path, caption=f"🎥 TikTok chunk: {os.path.basename(file_path)}")

async def record_chunks(username):
    """Run tiktok-live-recorder for 10-minute chunks"""
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(TMP_DIR, f"{username}_{timestamp}.mp4")

        print(f"🎬 Starting 10-minute recording for @{username} → {output_file}")
        process = subprocess.Popen(
            ["python3", "tiktok-live-recorder/main.py", "--u", username, "--o", output_file],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # Record for 10 minutes (600 seconds)
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            process.terminate()
            raise

        # Stop recorder
        process.terminate()
        time.sleep(2)

        print("TMP content after recording:", os.listdir(TMP_DIR))

        # Upload and clean up
        if os.path.exists(output_file):
            print(f"📤 Uploading {output_file} to Telegram…")
            await send_to_telegram(output_file)
            os.remove(output_file)
            print(f"🧹 Deleted {output_file}")

async def main():
    username = "example_user"  # Replace or pass dynamically
    await record_chunks(username)

if __name__ == "__main__":
    asyncio.run(main())

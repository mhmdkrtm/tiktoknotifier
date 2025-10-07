import os
import asyncio
import subprocess
import time
from datetime import datetime
from telethon import TelegramClient

# --- TELEGRAM SETUP ---
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", ""))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_FILE = "tg_session.session"

# Create tmp dir (for Railway ephemeral storage)
TMP_DIR = os.getenv("RAILWAY_TMP", "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

tg_client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)

async def send_to_telegram(file_path):
    """Send a file to Saved Messages."""
    async with tg_client:
        await tg_client.send_file("me", file_path, caption=f"🎥 TikTok chunk: {os.path.basename(file_path)}")

async def record_tiktok(username, duration_seconds=20):
    """Record TikTok Live in 20-second chunks and upload to Telegram."""
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(TMP_DIR, f"{username}_{timestamp}.mp4")

        print(f"🎬 Starting 20-second recording for @{username} → {output_file}")

        # Run the TikTok recorder from the submodule
        process = subprocess.Popen(
            ["python3", "tiktok-live-recorder/main.py", "--u", username, "--o", output_file],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        try:
            await asyncio.sleep(duration_seconds)
        except asyncio.CancelledError:
            process.terminate()
            raise

        # Stop recorder after duration
        process.terminate()
        time.sleep(2)

        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            print(f"📤 Uploading {output_file} to Telegram...")
            await send_to_telegram(output_file)
            os.remove(output_file)
            print(f"🧹 Deleted {output_file}")
        else:
            print(f"⚪ No file found for @{username}. Possibly user not live or args incorrect.")

        await asyncio.sleep(5)  # small pause before next chunk

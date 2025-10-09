import os
import asyncio
import subprocess
import time
import glob
from datetime import datetime
from telethon import TelegramClient

# --- TELEGRAM SETUP ---
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", ""))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_FILE = "tg_session.session"

# Create tmp dir (for Railway / local storage)
TMP_DIR = os.getenv("RAILWAY_TMP", "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

tg_client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)


# --- SEND TO TELEGRAM ---
async def send_to_telegram(file_path):
    """Send a file to Telegram Saved Messages."""
    async with tg_client:
        await tg_client.send_file(
            "me",
            file_path,
            caption=f"🎥 TikTok Live chunk: {os.path.basename(file_path)}",
        )


# --- MAIN RECORDING LOOP ---
async def record_tiktok(username, duration_seconds=20):
    """
    Record TikTok Live in chunks and upload each to Telegram.

    Steps:
      - Run the tiktok-live-recorder submodule for <duration_seconds>
      - Stop the recorder
      - Upload any new video files to Telegram
      - Clean up and repeat
    """

    while True:
        print(f"🎬 Checking @{username} live status and starting recording chunk...")

        # Start the TikTok recorder submodule
        process = subprocess.Popen(
            [
                "python3",
                "tiktok-live-recorder/main.py",
                "--url",
                f"https://www.tiktok.com/@{username}/live",
                "--output",
                TMP_DIR,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # Record for N seconds
            await asyncio.sleep(duration_seconds)
        except asyncio.CancelledError:
            process.terminate()
            raise

        # Stop recorder gracefully
        process.terminate()
        time.sleep(2)

        # Find the most recent file
        files = sorted(
            glob.glob(os.path.join(TMP_DIR, "*.flv"))
            + glob.glob(os.path.join(TMP_DIR, "*.mp4")),
            key=os.path.getmtime,
            reverse=True,
        )

        if files:
            latest_file = files[0]
            size = os.path.getsize(latest_file)
            if size > 0:
                print(f"📤 Uploading {latest_file} to Telegram ({size / 1024:.1f} KB)...")
                await send_to_telegram(latest_file)
                os.remove(latest_file)
                print(f"🧹 Deleted {latest_file}")
            else:
                print(f"⚪ File {latest_file} is empty, skipping.")
        else:
            print(f"⚪ No recorded files found for @{username}. Possibly user not live.")

        # Small pause before next recording cycle
        await asyncio.sleep(5)

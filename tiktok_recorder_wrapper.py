import os
import asyncio
import subprocess
import time
from datetime import datetime
from telethon import TelegramClient

# --- TELEGRAM SETUP ---
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_FILE = "tg_session.session"

# ✅ Use Zeabur’s safe tmp directory
TMP_DIR = "/tmp"
os.makedirs(TMP_DIR, exist_ok=True)

# --- TELETHON CLIENT ---
tg_client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)


async def send_to_telegram(file_path: str):
    """Send a recorded file to Telegram Saved Messages."""
    async with tg_client:
        await tg_client.send_file(
            "me",
            file_path,
            caption=f"🎥 TikTok Live chunk: {os.path.basename(file_path)}"
        )
    print(f"✅ Uploaded to Telegram → {os.path.basename(file_path)}")


async def record_tiktok(username: str, duration_seconds: int = 20):
    """
    Record TikTok Live in short chunks, upload to Telegram, then delete the file.
    Automatically retries until stopped.
    """
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(TMP_DIR, f"{username}_{timestamp}.flv")

        print(f"🎬 Starting {duration_seconds}-second recording for @{username}")
        print("Working directory:", os.getcwd())

        # ✅ Use absolute path for the submodule’s main.py
        recorder_path = os.path.join(os.getcwd(), "tiktok-live-recorder", "main.py")

        process = subprocess.Popen(
            ["python3", recorder_path, "--u", username, "--o", output_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        try:
            await asyncio.sleep(duration_seconds)
        except asyncio.CancelledError:
            print(f"🛑 Recording for @{username} was stopped manually.")
            process.terminate()
            raise

        # Gracefully stop the process
        process.terminate()
        time.sleep(2)

        # --- Check if file exists and upload ---
        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            if size > 0:
                print(f"📤 Uploading {output_file} ({size/1024:.1f} KB)...")
                try:
                    await send_to_telegram(output_file)
                except Exception as e:
                    print(f"❌ Upload failed: {e}")
                finally:
                    try:
                        os.remove(output_file)
                        print(f"🧹 Deleted {output_file}")
                    except Exception as e:
                        print(f"⚠️ Couldn’t delete {output_file}: {e}")
            else:
                print(f"⚪ Empty file created for @{username}, skipping upload.")
                os.remove(output_file)
        else:
            print(f"⚪ No file found for @{username}. User might not be live or path issue.")

        await asyncio.sleep(5)  # small pause before next chunk

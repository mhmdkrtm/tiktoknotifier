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

TMP_DIR = os.getenv("RAILWAY_TMP", "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

tg_client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)

async def send_to_telegram(file_path: str):
    """Uploads file to Telegram Saved Messages."""
    async with tg_client:
        await tg_client.send_file("me", file_path, caption=f"🎥 TikTok chunk: {os.path.basename(file_path)}")

async def record_tiktok(username: str, duration_seconds: int = 20):
    """
    Record TikTok Live using 3 fallbacks:
    1️⃣ yt-dlp
    2️⃣ ffmpeg
    3️⃣ Michele's tiktok-live-recorder submodule
    """
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(TMP_DIR, f"{username}_{timestamp}.flv")
        success = False

        print(f"🎬 Starting {duration_seconds}s recording for @{username}")

        # --- 1️⃣ Try yt-dlp ---
        ytdlp_cmd = [
            "yt-dlp",
            f"https://www.tiktok.com/@{username}/live",
            "-o", output_file,
            "--no-part",
            "--quiet",
            "--live-from-start"
        ]
        print(f"⚙️ Trying yt-dlp for @{username}...")
        ytdlp_proc = subprocess.Popen(ytdlp_cmd)
        await asyncio.sleep(duration_seconds)
        ytdlp_proc.terminate()
        await asyncio.sleep(2)

        if os.path.exists(output_file) and os.path.getsize(output_file) > 100_000:
            success = True
            print(f"✅ yt-dlp succeeded for @{username}")

        # --- 2️⃣ Fallback: ffmpeg ---
        if not success:
            print(f"⚪ yt-dlp failed. Trying ffmpeg capture...")
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-t", str(duration_seconds),
                "-i", f"https://www.tiktok.com/@{username}/live",
                "-c", "copy", output_file
            ]
            ffmpeg_proc = subprocess.Popen(ffmpeg_cmd)
            ffmpeg_proc.wait()

            if os.path.exists(output_file) and os.path.getsize(output_file) > 100_000:
                success = True
                print(f"✅ ffmpeg succeeded for @{username}")

        # --- 3️⃣ Final fallback: Michele’s tiktok-live-recorder submodule ---
        if not success:
            print(f"⚪ ffmpeg failed. Trying tiktok-live-recorder submodule...")
            recorder_cmd = [
                "python3", "tiktok-live-recorder/main.py",
                "--u", username,
                "--o", output_file
            ]
            recorder_proc = subprocess.Popen(recorder_cmd)
            await asyncio.sleep(duration_seconds)
            recorder_proc.terminate()
            await asyncio.sleep(2)

            if os.path.exists(output_file) and os.path.getsize(output_file) > 100_000:
                success = True
                print(f"✅ Submodule recorder succeeded for @{username}")

        # --- Upload and Cleanup ---
        if success:
            print(f"📤 Uploading {output_file} to Telegram...")
            await send_to_telegram(output_file)
            try:
                os.remove(output_file)
                print(f"🧹 Deleted {output_file}")
            except Exception as e:
                print(f"⚠️ Cleanup failed: {e}")
        else:
            print(f"❌ All recorders failed for @{username}. Maybe not live or invalid URL.")

        await asyncio.sleep(5)  # Cooldown before retry

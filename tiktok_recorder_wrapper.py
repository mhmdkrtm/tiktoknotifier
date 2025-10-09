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

TMP_DIR = os.getenv("RAILWAY_TMP", "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

tg_client = TelegramClient(SESSION_FILE, TELEGRAM_API_ID, TELEGRAM_API_HASH)

# --- Helper: Send file to Telegram ---
async def send_to_telegram(file_path):
    async with tg_client:
        await tg_client.send_file(
            "me",
            file_path,
            caption=f"🎥 TikTok Live chunk: {os.path.basename(file_path)}"
        )

# --- Helper: Run shell command safely ---
def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return result.stdout.strip()
        print(f"[!] Command failed: {' '.join(cmd)}\n{result.stderr}")
        return None
    except Exception as e:
        print(f"[!] Error running command: {e}")
        return None

# --- Core: Get TikTok live stream URL ---
def get_live_url(username):
    url = f"https://www.tiktok.com/@{username}/live"
    print(f"🔍 Checking live URL for @{username} ...")
    live_url = run_command(["yt-dlp", "-g", url])
    if live_url:
        print(f"✅ Got real live URL for @{username}")
        return live_url
    print(f"⚪ yt-dlp failed to get live URL for @{username}")
    return None

# --- Core: Try multiple recording methods ---
def try_record(live_url, output_file, duration):
    """Try yt-dlp, streamlink, then ffmpeg sequentially."""
    print(f"🎬 Recording {duration}s chunk → {output_file}")

    # 1️⃣ yt-dlp direct record
    try:
        cmd = ["yt-dlp", "-o", output_file, "--hls-use-mpegts", "--live-from-start", "-f", "best", live_url]
        print("▶️ Trying yt-dlp ...")
        subprocess.run(cmd, timeout=duration, check=False)
        if os.path.exists(output_file) and os.path.getsize(output_file) > 100000:
            return True
    except Exception as e:
        print(f"❌ yt-dlp error: {e}")

    # 2️⃣ streamlink fallback
    try:
        cmd = ["streamlink", "--hls-duration", str(duration), live_url, "best", "-o", output_file]
        print("▶️ Trying streamlink ...")
        subprocess.run(cmd, timeout=duration + 10, check=False)
        if os.path.exists(output_file) and os.path.getsize(output_file) > 100000:
            return True
    except Exception as e:
        print(f"❌ streamlink error: {e}")

    # 3️⃣ ffmpeg fallback
    try:
        cmd = [
            "ffmpeg", "-y", "-i", live_url, "-t", str(duration),
            "-c", "copy", "-f", "flv", output_file
        ]
        print("▶️ Trying ffmpeg ...")
        subprocess.run(cmd, timeout=duration + 10, check=False)
        if os.path.exists(output_file) and os.path.getsize(output_file) > 100000:
            return True
    except Exception as e:
        print(f"❌ ffmpeg error: {e}")

    print("⚠️ All recorders failed.")
    return False

# --- Main recording loop ---
async def record_tiktok(username, duration_seconds=20):
    """Record TikTok Live in chunks and upload to Telegram."""
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(TMP_DIR, f"{username}_{timestamp}.mp4")

        live_url = get_live_url(username)
        if not live_url:
            print(f"⚪ @{username} might not be live or TikTok blocked extraction.")
            await asyncio.sleep(15)
            continue

        success = try_record(live_url, output_file, duration_seconds)

        if success:
            print(f"📤 Uploading {output_file} to Telegram ...")
            try:
                await send_to_telegram(output_file)
                os.remove(output_file)
                print(f"🧹 Deleted {output_file}")
            except Exception as e:
                print(f"❌ Telegram upload failed: {e}")
        else:
            print(f"⚪ No valid recording for @{username}")

        await asyncio.sleep(5)

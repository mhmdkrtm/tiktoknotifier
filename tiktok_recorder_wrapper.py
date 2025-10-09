import os
import asyncio
import subprocess
from datetime import datetime
from telegram import Bot

# --- ENVIRONMENT VARIABLES ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TMP_DIR = os.getenv("RAILWAY_TMP", "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

bot = Bot(token=TELEGRAM_TOKEN)

# --- Helper: Send to Telegram ---
async def send_to_telegram(file_path):
    try:
        print(f"📤 Uploading {file_path} to Telegram ...")
        with open(file_path, "rb") as f:
            await asyncio.to_thread(
                bot.send_video,
                chat_id=TELEGRAM_CHAT_ID,
                video=f,
                caption=f"🎥 TikTok Live: {os.path.basename(file_path)}",
            )
        print("✅ Uploaded successfully.")
        os.remove(file_path)
    except Exception as e:
        print(f"❌ Telegram upload failed: {e}")

# --- Helper: Run subprocess ---
def run_cmd(cmd):
    try:
        print(f"⚙️ Running: {' '.join(cmd)}")
        process = subprocess.run(cmd, capture_output=True, text=True)
        if process.returncode != 0:
            print(f"⚠️ Command failed: {process.stderr.strip()}")
        return process.returncode == 0
    except Exception as e:
        print(f"❌ Error executing command: {e}")
        return False

# --- Main Recorder Function ---
async def record_tiktok_live(username):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_path = os.path.join(TMP_DIR, f"{username}_{timestamp}.mp4")

    print(f"🎬 Starting TikTok live recording for @{username}...")

    # --- Step 1: Try yt-dlp to get the live URL ---
    try:
        yt_cmd = [
            "yt-dlp",
            f"https://www.tiktok.com/@{username}/live",
            "--no-warnings",
            "--geo-bypass",
            "--get-url",
        ]
        stream_url = subprocess.check_output(yt_cmd, text=True).strip()
        if "tiktokcdn" not in stream_url:
            raise Exception("Invalid stream URL")
        print(f"✅ Stream URL: {stream_url}")
    except Exception as e:
        print(f"⚠️ Failed to fetch stream URL with yt-dlp: {e}")
        stream_url = None

    # --- Step 2: Try to record using yt-dlp ---
    success = False
    if stream_url:
        output_pattern = os.path.join(TMP_DIR, f"{username}_part_%03d.mp4")
        yt_record_cmd = [
            "yt-dlp",
            "--no-part",
            "--no-warnings",
            "--no-live-from-start",
            "-o",
            output_pattern,
            stream_url,
        ]
        success = run_cmd(yt_record_cmd)

    # --- Step 3: Streamlink fallback ---
    if not success:
        streamlink_cmd = [
            "streamlink",
            f"https://www.tiktok.com/@{username}/live",
            "best",
            "-o",
            base_path,
            "--hls-live-restart",
        ]
        success = run_cmd(streamlink_cmd)

    # --- Step 4: ffmpeg fallback ---
    if not success and stream_url:
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            stream_url,
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            "600",
            "-reset_timestamps",
            "1",
            os.path.join(TMP_DIR, f"{username}_part_%03d.mp4"),
        ]
        run_cmd(ffmpeg_cmd)

    # --- Step 5: Upload chunks ---
    for file in sorted(os.listdir(TMP_DIR)):
        if file.startswith(username) and file.endswith(".mp4"):
            await send_to_telegram(os.path.join(TMP_DIR, file))

    print(f"✅ Finished all tasks for @{username}.")

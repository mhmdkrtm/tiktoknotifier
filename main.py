import os
import time
import subprocess
from datetime import datetime
from pathlib import Path
from notify import send_message

# ========== SETTINGS ==========
TIKTOK_ACCOUNT = "x_o_533"
CHECK_INTERVAL = 600  # 10 minutes
TMP_DIR = Path("/app/downloads")
RCLONE_REMOTE = "gdrive:tiktok"
WAIT_FOR_LIVE = 300  # 5 minutes
# ==============================

TMP_DIR.mkdir(parents=True, exist_ok=True)

# Restore rclone config
rclone_conf_path = Path(os.getenv("RCLONE_CONFIG"))
if not rclone_conf_path.exists():
    print("⚠️ No RCLONE_CONFIG found. Exiting.")
    exit(1)

def run_cmd(cmd, capture_output=False):
    print(f"▶️ Running: {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=capture_output, text=True)

def get_video_length(file_path):
    try:
        cmd = f'yt-dlp --print "%(duration_string)s" "{file_path}"'
        result = run_cmd(cmd, capture_output=True)
        duration = result.stdout.strip()
        return duration if duration else "unknown"
    except:
        return "unknown"

def upload_to_drive(filepath):
    result = run_cmd(f"rclone move '{filepath}' {RCLONE_REMOTE} -v")
    return result.returncode == 0

while True:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n⏰ Checking at {now}")
    send_message(f"🔎 Checking TikTok LIVE for {TIKTOK_ACCOUNT} at {now}...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = TMP_DIR / f"{TIKTOK_ACCOUNT}_{timestamp}.mp4"

    # Try yt-dlp first
    success = run_cmd(f'yt-dlp --wait-for-video {WAIT_FOR_LIVE} -o "{filename}" https://www.tiktok.com/@{TIKTOK_ACCOUNT}/live').returncode == 0

    # If yt-dlp fails, try ffmpeg
    if not success:
        send_message("⚠️ yt-dlp failed, trying ffmpeg...")
        success = run_cmd(f'ffmpeg -y -i https://www.tiktok.com/@{TIKTOK_ACCOUNT}/live -c copy "{filename}"').returncode == 0

    if success:
        send_message(f"🎥 LIVE detected! Recording started: {filename.name}")
        # Wait until recording finishes
        duration = get_video_length(filename)
        send_message(f"✅ Recording finished: {filename.name}\n⏱ Length: {duration}")

        if upload_to_drive(filename):
            send_message(f"☁️ Uploaded {filename.name} to Google Drive successfully.")
        else:
            send_message(f"⚠️ Upload failed for {filename.name}.")
    else:
        send_message("❌ Both yt-dlp and ffmpeg failed. Retrying in 10 minutes.")

    time.sleep(CHECK_INTERVAL)

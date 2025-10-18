import os
import time
import subprocess
from datetime import datetime
from pathlib import Path

# ---- SETTINGS ----
TIKTOK_URL = "https://www.tiktok.com/@x_o_533/live"
TMP_DIR = Path("/app/downloads")  # for Railway
WAIT_FOR_VIDEO = 300  # 5 min
CHECK_INTERVAL = 600  # 10 min

# Restore rclone config from environment variable (Railway secret)
config_dir = Path("/root/.config/rclone")
config_dir.mkdir(parents=True, exist_ok=True)
rclone_conf_path = config_dir / "rclone.conf"

if os.getenv("RCLONE_CONFIG"):
    with open(rclone_conf_path, "w") as f:
        f.write(os.getenv("RCLONE_CONFIG"))
else:
    print("⚠️  No RCLONE_CONFIG env variable found.")
    exit(1)

TMP_DIR.mkdir(parents=True, exist_ok=True)

def run_cmd(cmd):
    print(f"▶️ Running: {cmd}")
    result = subprocess.run(cmd, shell=True)
    return result.returncode

def upload_to_gdrive():
    print("📤 Uploading to Google Drive...")
    run_cmd(f"rclone move {TMP_DIR} gdrive:tiktok --create-empty-src-dirs --ignore-existing -v")

while True:
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n⏰ Checking at {now}")
        cmd = f'yt-dlp --wait-for-video {WAIT_FOR_VIDEO} -o "{TMP_DIR}/%(uploader)s_%(upload_date)s.%(ext)s" {TIKTOK_URL}'
        result = run_cmd(cmd)
        if result == 0:
            upload_to_gdrive()
        else:
            print("❌ yt-dlp returned non-zero code (maybe no live yet).")
        time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        print("🛑 Exiting...")
        break
    except Exception as e:
        print(f"⚠️ Error: {e}")
        time.sleep(60)

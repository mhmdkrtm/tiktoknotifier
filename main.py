import os
import time
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from notify import send_message

# ================= SETTINGS =================
TIKTOK_ACCOUNTS = ["x_o_533", "prensesa.cane", "yra8746"]  # up to 3 accounts
CHECK_INTERVAL = 600  # 10 minutes
TMP_DIR = Path("/app/downloads")
RCLONE_REMOTE = "gdrive:tiktok"
WAIT_FOR_LIVE = 300  # 5 minutes
# ============================================

TMP_DIR.mkdir(parents=True, exist_ok=True)

# ===== Write RCLONE_CONFIG to file =====
rclone_conf_path = Path("/root/.config/rclone/rclone.conf")
rclone_conf_path.parent.mkdir(parents=True, exist_ok=True)
rclone_conf_content = os.getenv("RCLONE_CONFIG")
if not rclone_conf_content:
    print("⚠️ RCLONE_CONFIG env variable is empty. Exiting.")
    exit(1)

with open(rclone_conf_path, "w") as f:
    f.write(rclone_conf_content)
print("✅ rclone.conf written successfully")

# ===== Helper functions =====
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

# ===== Monitoring function per account =====
def monitor_account(account):
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n⏰ Checking {account} at {now}")
        send_message(f"🔎 Checking TikTok LIVE for {account} at {now}...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = TMP_DIR / f"{account}_{timestamp}.mp4"

        # Try yt-dlp first
        success = run_cmd(
            f'yt-dlp --wait-for-video {WAIT_FOR_LIVE} -o "{filename}" https://www.tiktok.com/@{account}/live'
        ).returncode == 0

        # If yt-dlp fails, try ffmpeg
        if not success:
            send_message(f"⚠️ yt-dlp failed for {account}, trying ffmpeg...")
            success = run_cmd(
                f'ffmpeg -y -i https://www.tiktok.com/@{account}/live -c copy "{filename}"'
            ).returncode == 0

        if success:
            send_message(f"🎥 LIVE detected for {account}! Recording started: {filename.name}")
            duration = get_video_length(filename)
            send_message(f"✅ Recording finished: {filename.name}\n⏱ Length: {duration}")

            if upload_to_drive(filename):
                send_message(f"☁️ Uploaded {filename.name} to Google Drive successfully.")
                # ===== Cleanup local file after upload =====
                try:
                    filename.unlink()
                    print(f"🗑 Deleted local file {filename.name}")
                except Exception as e:
                    print(f"⚠️ Failed to delete {filename.name}: {e}")
            else:
                send_message(f"⚠️ Upload failed for {filename.name}.")
        else:
            send_message(f"❌ Both yt-dlp and ffmpeg failed for {account}. Retrying in {CHECK_INTERVAL // 60} min.")

        time.sleep(CHECK_INTERVAL)

# ===== Start threads for each account =====
threads = []
for account in TIKTOK_ACCOUNTS:
    t = threading.Thread(target=monitor_account, args=(account,))
    t.daemon = True  # allows the program to exit even if threads are running
    t.start()
    threads.append(t)

# ===== Keep main thread alive =====
while True:
    time.sleep(60)

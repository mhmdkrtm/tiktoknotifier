import os
import subprocess
import time
from datetime import datetime

# Full absolute path to your tmp directory inside Railway
TMP_DIR = os.path.join(os.getcwd(), "tiktoknotifier", "tmp")

# Ensure folder exists
os.makedirs(TMP_DIR, exist_ok=True)

def record_tiktok(username, duration_minutes=10):
    """
    Record a TikTok live stream for a given username and duration.
    Splits recordings into chunks and stores temporarily in tmp folder.
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{username}_{timestamp}.mp4"
    filepath = os.path.join(TMP_DIR, filename)

    print(f"🎬 Starting {duration_minutes}-minute recording for @{username} → {filepath}")

    try:
        # Call DouyinLiveRecorder submodule correctly
        process = subprocess.Popen(
            [
                "python3",
                "tiktok-live-recorder/run.py",
                "--user", username,
                "--path", TMP_DIR,
                "--no-streamlink",
                "--retry", "2"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Run for duration_minutes then stop
        time.sleep(duration_minutes * 60)
        process.terminate()

        # Give recorder time to finalize the file
        time.sleep(3)

        # Check contents of TMP_DIR
        files = os.listdir(TMP_DIR)
        print(f"TMP content after recording: {files}")

        # Return the most recent file (if any)
        mp4_files = [f for f in files if username in f and f.endswith(('.mp4', '.flv'))]
        if not mp4_files:
            print(f"⚪ No file found for @{username}. Possibly user not live or ar

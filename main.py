import os, asyncio, time, subprocess
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
from telethon import TelegramClient

# ================= TELEGRAM CONFIG =================
API_ID   = int(os.environ.get("API_ID", 0))          # from my.telegram.org
API_HASH = os.environ.get("API_HASH", "")            # from my.telegram.org
SESSION  = "tg_session"                              # Telethon session name
# ===================================================

TMP_DIR        = "/tmp/tiktok_segments"   # ephemeral dir on Railway
SEGMENT_TIME   = 600                      # 10 minutes
CHECK_INTERVAL = 60                       # offline retry seconds
USERS_FILE     = "users.txt"

os.makedirs(TMP_DIR, exist_ok=True)
tg_client = TelegramClient(SESSION, API_ID, API_HASH)

# ───────────────────────────────────────────────────
async def upload_segments(username):
    """Upload new 10-minute segments to Saved Messages and delete them."""
    seen = set()
    while True:
        for f in sorted(os.listdir(TMP_DIR)):
            if f.endswith(".mp4") and f not in seen:
                seen.add(f)
                path = os.path.join(TMP_DIR, f)
                try:
                    async with tg_client:
                        await tg_client.send_file(
                            "me", path,
                            caption=f"🎬 @{username} — segment {time.strftime('%H:%M:%S')}"
                        )
                    print(f"☁️ Uploaded & deleted {f}")
                except Exception as e:
                    print("❌ Telegram upload failed:", e)
                finally:
                    try:
                        os.remove(path)
                    except Exception:
                        pass
        await asyncio.sleep(10)
# ───────────────────────────────────────────────────
def start_ffmpeg(username):
    """Use streamlink → ffmpeg to record 10-minute segments."""
    out_pattern = os.path.join(TMP_DIR, f"{username}_%03d.mp4")
    sl_cmd = [
        "streamlink",
        f"https://www.tiktok.com/@{username}/live",
        "best",
        "-O"
    ]
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", "pipe:0",
        "-c", "copy", "-f", "segment",
        "-segment_time", str(SEGMENT_TIME),
        out_pattern
    ]
    print(f"🎥 Starting 10-minute recorder for @{username}")
    sl = subprocess.Popen(sl_cmd, stdout=subprocess.PIPE)
    subprocess.Popen(ffmpeg_cmd, stdin=sl.stdout).wait()
    print(f"🛑 Recorder stopped for @{username}")
# ───────────────────────────────────────────────────
async def watch_user(username):
    """Monitor a TikTok user and start recording when live."""
    client = TikTokLiveClient(unique_id=username)
    recording_task = None
    uploader_task = None

    @client.on(ConnectEvent)
    async def on_connect(_):
        nonlocal recording_task, uploader_task
        print(f"[+] @{username} is LIVE!")
        if not recording_task:
            loop = asyncio.get_event_loop()
            recording_task = loop.run_in_executor(None, start_ffmpeg, username)
        if not uploader_task:
            uploader_task = asyncio.create_task(upload_segments(username))

    @client.on(DisconnectEvent)
    async def on_disconnect(_):
        print(f"[ℹ️] @{username} disconnected — waiting for next live.")

    while True:
        try:
            await client.start()
        except Exception as e:
            err = str(e)
            if "UserOfflineError" in err:
                print(f"[ℹ️] @{username} offline, retrying in {CHECK_INTERVAL}s...")
            else:
                print(f"[!] @{username} error:", e)
            await asyncio.sleep(CHECK_INTERVAL)
# ───────────────────────────────────────────────────
async def main():
    if not os.path.exists(USERS_FILE):
        print("❌ users.txt not found.")
        return
    with open(USERS_FILE) as f:
        users = [u.strip() for u in f if u.strip()]
    print(f"🔥 Monitoring {len(users)} TikTok users.")
    await asyncio.gather(*(watch_user(u) for u in users))
# ───────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())

import os, asyncio, time, subprocess, requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
from telethon import TelegramClient

# =====================================================
# 🔧 CONFIGURATION
# =====================================================
API_ID     = 20196111
API_HASH   = "05b184f5623850b5666c32e14e7a888b"
BOT_TOKEN  = "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"
CHAT_ID    = "1280121045"
SESSION    = "tg_session"

TMP_DIR         = "/tmp/tiktok_segments"
SEGMENT_TIME    = 30            # 30 s for testing (change to 600 for production)
CHECK_OFFLINE   = 60            # retry every 1 min when offline
NOTIFY_COOLDOWN = 600           # 10 min between notifications
USERS_FILE      = "users.txt"

os.makedirs(TMP_DIR, exist_ok=True)
tg_client = TelegramClient(SESSION, API_ID, API_HASH)

# =====================================================
# global cooldown tracker (shared across reconnects)
last_notification_time = {}

# =====================================================
def send_bot_msg(text: str):
    """Send Telegram bot text message."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    except Exception as e:
        print("⚠️ Bot send failed:", e)

# =====================================================
async def upload_segments(username):
    """Continuously upload new chunks to Saved Messages."""
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
                            caption=f"🎬 @{username} — {time.strftime('%H:%M:%S')}"
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

# =====================================================
def record_with_streamlink(username):
    """Main recorder using Streamlink + ffmpeg segmentation."""
    out_pattern = os.path.join(TMP_DIR, f"{username}_%03d.mp4")
    sl_cmd = [
        "streamlink", f"https://www.tiktok.com/@{username}/live", "best", "-O",
    ]
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-i", "pipe:0",
        "-c", "copy", "-f", "segment",
        "-segment_time", str(SEGMENT_TIME),
        out_pattern,
    ]
    print(f"🎥 Recording @{username} via Streamlink…")
    sl = subprocess.Popen(sl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ffmpeg = subprocess.Popen(ffmpeg_cmd, stdin=sl.stdout, stderr=subprocess.PIPE)
    stdout, stderr = sl.communicate()
    if b"No playable streams" in stderr or b"inaccessible" in stderr:
        raise RuntimeError("Streamlink failed to access stream.")
    ffmpeg.wait()

# =====================================================
def record_with_ytdlp(username):
    """Fallback recorder if Streamlink fails."""
    output = os.path.join(TMP_DIR, f"{username}_yt_%(timestamp)s.%(ext)s")
    cmd = [
        "yt-dlp",
        f"https://www.tiktok.com/@{username}/live",
        "-o", output,
        "--hls-use-mpegts",
        "--no-part",
        "--no-warnings",
        "--no-live-from-start",   # ✅ fixed flag
        "--max-filesize", "500M",
    ]
    print(f"🎥 Streamlink failed, using yt-dlp for @{username}…")
    subprocess.call(cmd)

# =====================================================
def start_recording(username):
    """Attempt Streamlink first, fallback to yt-dlp if needed."""
    try:
        record_with_streamlink(username)
    except Exception as e:
        print(f"⚠️ Streamlink failed for @{username}: {e}")
        try:
            record_with_ytdlp(username)
        except Exception as e2:
            print(f"❌ yt-dlp also failed for @{username}: {e2}")
            send_bot_msg(f"⚠️ Both recorders failed for @{username}")
    print(f"🛑 Recorder stopped for @{username}")

# =====================================================
async def watch_user(username):
    """Monitor user, manage recording, upload, and notifications."""
    client = TikTokLiveClient(unique_id=username)
    recording_task = None
    uploader_task = None

    @client.on(ConnectEvent)
    async def on_connect(_):
        nonlocal recording_task, uploader_task
        print(f"[+] @{username} is LIVE!")

        now = time.time()
        last_time = last_notification_time.get(username, 0)

        # 🔥 check cooldown across sessions
        if now - last_time > NOTIFY_COOLDOWN:
            send_bot_msg(f"🔴 @{username} is LIVE!")
            last_notification_time[username] = now
        else:
            print(f"[ℹ️] Skipping duplicate LIVE message (cooldown active).")

        if not recording_task:
            loop = asyncio.get_event_loop()
            recording_task = loop.run_in_executor(None, start_recording, username)
        if not uploader_task:
            uploader_task = asyncio.create_task(upload_segments(username))

    @client.on(DisconnectEvent)
    async def on_disconnect(_):
        print(f"[ℹ️] @{username} disconnected — waiting for next live.")

    while True:
        try:
            await client.start()
        except Exception as e:
            err = str(e).lower()
            if "rate_limit" in err:
                print(f"[!] @{username} hit rate limit — waiting 5 min.")
                await asyncio.sleep(300)
                continue
            elif "userofflineerror" in err:
                print(f"[ℹ️] @{username} offline — retry in {CHECK_OFFLINE}s.")
            elif "one connection per client" in err:
                print(f"[ℹ️] @{username} already connected — skipping duplicate.")
            else:
                print(f"[!] @{username} error:", e)
            await asyncio.sleep(CHECK_OFFLINE)

# =====================================================
async def main():
    if not os.path.exists(USERS_FILE):
        print("❌ users.txt not found.")
        return
    with open(USERS_FILE) as f:
        users = [u.strip() for u in f if u.strip()]
    print(f"🔥 Monitoring {len(users)} TikTok users…")
    await asyncio.gather(*(watch_user(u) for u in users))

# =====================================================
if __name__ == "__main__":
    asyncio.run(main())

import os, asyncio, time, subprocess, requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent
from telethon import TelegramClient

# =====================================================
# 🔧 MANUAL CONFIG (inserted directly)
# =====================================================
API_ID     = 20196111
API_HASH   = "05b184f5623850b5666c32e14e7a888b"
BOT_TOKEN  = "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"
CHAT_ID    = "1280121045"
SESSION    = "tg_session"

# =====================================================
TMP_DIR        = "/tmp/tiktok_segments"
SEGMENT_TIME   = 30           # 30 seconds for testing
CHECK_INTERVAL = 60           # offline check interval
USERS_FILE     = "users.txt"

os.makedirs(TMP_DIR, exist_ok=True)
tg_client = TelegramClient(SESSION, API_ID, API_HASH)

# =====================================================
def send_bot_msg(text: str):
    """Send a short message via bot to your Telegram chat."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text})
    except Exception as e:
        print("⚠️ Bot send failed:", e)

# =====================================================
async def upload_segments(username):
    """Continuously upload new 30-sec segments to Saved Messages."""
    seen = set()
    while True:
        for f in sorted(os.listdir(TMP_DIR)):
            if f.endswith(".mp4") and f not in seen:
                seen.add(f)
                path = os.path.join(TMP_DIR, f)
                try:
                    async with tg_client:
                        await tg_client.send_file(
                            "me",
                            path,
                            caption=f"🎬 @{username} — segment {time.strftime('%H:%M:%S')}",
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
def start_ffmpeg(username):
    """Record TikTok live into 30-sec chunks."""
    out_pattern = os.path.join(TMP_DIR, f"{username}_%03d.mp4")
    sl_cmd = [
        "streamlink",
        f"https://www.tiktok.com/@{username}/live",
        "best",
        "-O",
    ]
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        "pipe:0",
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        str(SEGMENT_TIME),
        out_pattern,
    ]
    print(f"🎥 Recording @{username} in 30-second chunks…")
    sl = subprocess.Popen(sl_cmd, stdout=subprocess.PIPE)
    subprocess.Popen(ffmpeg_cmd, stdin=sl.stdout).wait()
    print(f"🛑 Recorder stopped for @{username}")

# =====================================================
async def watch_user(username):
    """Detect live state and trigger recording/uploader with rate-limit handling."""
    client = TikTokLiveClient(unique_id=username)
    recording_task = None
    uploader_task = None
    notified_live = False  # so we only send one message per live session

    @client.on(ConnectEvent)
    async def on_connect(_):
        nonlocal recording_task, uploader_task, notified_live
        print(f"[+] @{username} is LIVE!")
        if not notified_live:
            send_bot_msg(f"🔴 @{username} is LIVE!")
            notified_live = True
        if not recording_task:
            loop = asyncio.get_event_loop()
            recording_task = loop.run_in_executor(None, start_ffmpeg, username)
        if not uploader_task:
            uploader_task = asyncio.create_task(upload_segments(username))

    @client.on(DisconnectEvent)
    async def on_disconnect(_):
        nonlocal notified_live
        print(f"[ℹ️] @{username} disconnected — waiting for next live.")
        notified_live = False  # reset for next session

    while True:
        try:
            await client.start()
        except Exception as e:
            err = str(e).lower()
            if "rate_limit" in err:
                print(f"[!] @{username} hit rate limit — waiting 5 minutes.")
                await asyncio.sleep(300)
                continue
            elif "userofflineerror" in err:
                print(f"[ℹ️] @{username} offline — retry in {CHECK_INTERVAL}s.")
            elif "one connection per client" in err:
                print(f"[ℹ️] @{username} already connected — skipping duplicate.")
            else:
                print(f"[!] @{username} unexpected error:", e)
            await asyncio.sleep(CHECK_INTERVAL)

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

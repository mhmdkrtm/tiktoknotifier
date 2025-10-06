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

# working directory
TMP_DIR         = "/tmp/tiktok_segments"     # auto-created at runtime
SEGMENT_TIME    = 30                         # seconds per chunk (testing)
CHECK_OFFLINE   = 60                         # seconds between offline checks
NOTIFY_COOLDOWN = 600                        # seconds between notifications (10 min)
USERS_FILE      = "users.txt"

# create folder if missing
os.makedirs(TMP_DIR, exist_ok=True)

# telegram client for uploads
tg_client = TelegramClient(SESSION, API_ID, API_HASH)
last_notification_time = {}  # per-user cooldown tracking

# =====================================================
def send_bot_msg(text: str):
    """Send Telegram bot text message."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10
        )
    except Exception as e:
        print("⚠️ Telegram send failed:", e)

# =====================================================
async def upload_segments(username):
    """Continuously upload new video chunks to Saved Messages."""
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
                    print("❌ Upload failed:", e)
                finally:
                    try:
                        os.remove(path)
                    except Exception:
                        pass
        await asyncio.sleep(10)

# =====================================================
def record_with_ytdlp(username):
    """Record TikTok live with yt-dlp only."""
    print(f"🎥 Recording @{username} via yt-dlp…")
    out_pattern = os.path.join(TMP_DIR, f"{username}_%(timestamp)s.%(ext)s")
    cmd = [
        "yt-dlp",
        f"https://www.tiktok.com/@{username}/live",
        "-o", out_pattern,
        "--hls-use-mpegts",
        "--no-part",
        "--no-warnings",
        "--no-live-from-start",
        "--max-filesize", "500M",
    ]
    try:
        subprocess.call(cmd)
    except Exception as e:
        print(f"❌ yt-dlp recording error for @{username}: {e}")
        send_bot_msg(f"⚠️ yt-dlp failed for @{username}")
    print(f"🛑 yt-dlp stopped for @{username}")

# =====================================================
async def watch_user(username):
    """Monitor TikTok user → notify once → record & upload."""
    client = TikTokLiveClient(unique_id=username)
    recording_task = None
    uploader_task = None

    @client.on(ConnectEvent)
    async def on_connect(_):
        nonlocal recording_task, uploader_task
        print(f"[+] @{username} is LIVE!")
        now = time.time()
        last_time = last_notification_time.get(username, 0)

        # send only once per cooldown window
        if now - last_time > NOTIFY_COOLDOWN:
            send_bot_msg(f"🔴 @{username} is LIVE!")
            last_notification_time[username] = now
        else:
            print(f"[ℹ️] Skipping duplicate LIVE message (cooldown active).")

        if not recording_task:
            loop = asyncio.get_event_loop()
            recording_task = loop.run_in_executor(None, record_with_ytdlp, username)
        if not uploader_task:
            uploader_task = asyncio.create_task(upload_segments(username))

    @client.on(DisconnectEvent)
    async def on_disconnect(_):
        print(f"[ℹ️] @{username} disconnected — waiting for next live.")

    # main loop with ping_loop bug suppression
    while True:
        try:
            await client.start()
        except AttributeError as e:
            if "ping_loop" in str(e):
                print(f"[ℹ️] Swallowed ping_loop bug for @{username}")
                await asyncio.sleep(CHECK_OFFLINE)
                continue
            else:
                print(f"[!] @{username} AttributeError: {e}")
                await asyncio.sleep(CHECK_OFFLINE)
        except Exception as e:
            err = str(e).lower()
            if "rate_limit" in err:
                print(f"[!] @{username} hit rate limit — waiting 5 min.")
                await asyncio.sleep(300)
            elif "userofflineerror" in err:
                print(f"[ℹ️] @{username} offline — retry in {CHECK_OFFLINE}s.")
                await asyncio.sleep(CHECK_OFFLINE)
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

import os
import subprocess
import glob
import time
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# === CONFIG ===
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4")
YOUR_TELEGRAM_ID = int(os.environ.get("YOUR_TELEGRAM_ID", "1280121045"))
RECORDER_PATH = os.path.join(os.path.dirname(__file__), "tiktok-live-recorder", "main.py")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "downloads")
CHUNK_DURATION = 30   # 10 minutes in seconds
MAX_TELEGRAM_MB = 50  # Telegram file size limit (in MB)

active_recordings = {}

# --- Helper to send and delete chunk ---
async def send_and_delete(context, username):
    """Send latest chunk to Telegram and delete it after upload."""
    recorded_files = sorted(
        glob.glob(os.path.join(OUTPUT_DIR, f"*{username}*.mp4")),
        key=os.path.getmtime,
        reverse=True,
    )

    if not recorded_files:
        return

    latest_file = recorded_files[0]
    file_size_mb = os.path.getsize(latest_file) / (1024 * 1024)

    if file_size_mb > MAX_TELEGRAM_MB:
        await context.bot.send_message(
            chat_id=YOUR_TELEGRAM_ID,
            text=f"⚠️ @{username} chunk is {file_size_mb:.1f} MB — too big for Telegram upload."
        )
        os.remove(latest_file)
        return

    await context.bot.send_message(YOUR_TELEGRAM_ID, f"📦 Uploading new 10-minute chunk for @{username} ...")
    await context.bot.send_video(
        chat_id=YOUR_TELEGRAM_ID,
        video=open(latest_file, "rb"),
        caption=f"🎬 10-minute chunk from @{username}'s live",
    )
    os.remove(latest_file)
    await context.bot.send_message(YOUR_TELEGRAM_ID, f"🗑️ Deleted chunk after upload ✅")


# --- Record loop ---
async def record_loop(username, context):
    """Continuously record in 10-minute chunks until stream ends."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await context.bot.send_message(YOUR_TELEGRAM_ID, f"🎥 Starting continuous recording for @{username}.")

    while username in active_recordings:
        try:
            process = subprocess.Popen(
                [
                    "python", RECORDER_PATH,
                    "--user", username,
                    "--output", OUTPUT_DIR,
                    "--duration", str(CHUNK_DURATION)
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            active_recordings[username] = process
            process.wait()  # Wait for this 10-min chunk to finish

            await send_and_delete(context, username)
            await asyncio.sleep(5)  # small delay before next chunk

        except Exception as e:
            await context.bot.send_message(YOUR_TELEGRAM_ID, f"❌ Error during chunk: {e}")
            break

    await context.bot.send_message(YOUR_TELEGRAM_ID, f"🛑 Recording stopped for @{username}.")


# --- Bot commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Use:\n"
        "/record <username> → Start continuous recording\n"
        "/stop <username> → Stop it\n"
        "/status → List current recordings"
    )

async def record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /record <username>")
        return

    username = context.args[0].replace("@", "")
    if username in active_recordings:
        await update.message.reply_text(f"⚠️ Already recording @{username}.")
        return

    active_recordings[username] = None
    await update.message.reply_text(f"🎬 Started recording @{username} in 10-minute chunks.")
    asyncio.create_task(record_loop(username, context))

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /stop <username>")
        return

    username = context.args[0].replace("@", "")
    if username not in active_recordings:
        await update.message.reply_text(f"⚠️ No active recording for @{username}.")
        return

    process = active_recordings.pop(username)
    if process:
        process.terminate()
    await update.message.reply_text(f"🛑 Stopped recording @{username}.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not active_recordings:
        await update.message.reply_text("🟢 No recordings running.")
        return

    msg = "\n".join([f"• @{u}" for u in active_recordings.keys()])
    await update.message.reply_text(f"🎥 Active Recordings:\n{msg}")

# --- Main ---
def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("record", record))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))

    print("🤖 Bot ready.")
    app.run_polling()

if __name__ == "__main__":
    main()

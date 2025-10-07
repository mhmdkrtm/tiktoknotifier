import os
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"
REPO_URL = "https://github.com/Michele0303/tiktok-live-recorder.git"
REPO_DIR = "tiktok-live-recorder"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! Use /record <username> to start recording a TikTok live.")

async def record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage:\n/record <tiktok_username>")
        return

    username = context.args[0].replace("@", "")
    await update.message.reply_text(f"🎥 Starting recording for @{username} ...")

    # Clone repo if not already cloned
    if not os.path.exists(REPO_DIR):
        await update.message.reply_text("📦 Cloning TikTok Recorder repo...")
        subprocess.run(["git", "clone", REPO_URL, REPO_DIR])

    # Run recorder
    cmd = [
        "python3",
        f"{REPO_DIR}/main.py",
        "--user", username,
    ]
    subprocess.Popen(cmd)
    await update.message.reply_text(f"✅ Recorder started for @{username}!")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("record", record))

    print("🤖 Bot is running...")
    app.run_polling()

import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from tiktok_recorder_wrapper import record_tiktok

# --- CONFIG ---
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN not set in environment variables")

# Track active recording tasks
active_tasks = {}

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Use /record <username> to start recording a TikTok live.\n"
        "Use /list to view active recordings."
    )

async def record_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /record <username>")
        return

    username = context.args[0].replace("@", "")

    if username in active_tasks:
        await update.message.reply_text(f"⚠️ Already recording @{username}")
        return

    await update.message.reply_text(f"🎥 Starting recording for @{username} ...")

    # Start async recording task (20s chunks)
    task = asyncio.create_task(record_tiktok(username))
    active_tasks[username] = task

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not active_tasks:
        await update.message.reply_text("📭 No active recordings.")
        return
    msg = "🎬 Active Recordings:\n" + "\n".join([f"• @{u}" for u in active_tasks])
    await update.message.reply_text(msg)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Usage: /stop <username>")
        return

    username = context.args[0].replace("@", "")
    task = active_tasks.get(username)
    if not task:
        await update.message.reply_text(f"⚪ No active recording for @{username}")
        return

    task.cancel()
    del active_tasks[username]
    await update.message.reply_text(f"🛑 Stopped recording @{username}")

# --- MAIN APP ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("record", record_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("stop", stop_command))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

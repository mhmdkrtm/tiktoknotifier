import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from tiktok_recorder_wrapper import record_chunks

# -------------------------------
# Telegram Bot Setup
# -------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ Missing TELEGRAM_TOKEN environment variable!")

# Dictionary to keep track of running recording tasks
active_tasks = {}


# -------------------------------
# Commands
# -------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command to show help"""
    await update.message.reply_text(
        "👋 Welcome to the TikTok Recorder Bot!\n\n"
        "Available commands:\n"
        "• /record <username> → Start recording live in 10-min chunks\n"
        "• /stop <username> → Stop recording that user\n"
        "• /list → Show currently recording users"
    )


async def record_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start recording a TikTok user's live"""
    if not context.args:
        await update.message.reply_text("Usage: /record <tiktok_username>")
        return

    username = context.args[0].replace("@", "")
    chat_id = update.effective_chat.id

    if username in active_tasks:
        await update.message.reply_text(f"⚠️ Already recording @{username}")
        return

    await update.message.reply_text(
        f"🎬 Starting to record @{username}'s live every 10 minutes..."
    )

    # Start recording in the background
    task = asyncio.create_task(record_chunks(username))
    active_tasks[username] = task

    # Inform user when finished or failed
    async def watch_task():
        try:
            await task
            await update.message.reply_text(f"✅ Recording for @{username} finished.")
        except asyncio.CancelledError:
            await update.message.reply_text(f"🛑 Recording for @{username} stopped.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error while recording @{username}: {e}")

    asyncio.create_task(watch_task())


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop recording a user"""
    if not context.args:
        await update.message.reply_text("Usage: /stop <tiktok_username>")
        return

    username = context.args[0].replace("@", "")

    if username not in active_tasks:
        await update.message.reply_text(f"⚠️ @{username} is not being recorded.")
        return

    # Cancel and clean up
    task = active_tasks.pop(username)
    task.cancel()
    await update.message.reply_text(f"🛑 Stopped recording @{username}.")


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List currently recording users"""
    if not active_tasks:
        await update.message.reply_text("No active recordings.")
    else:
        users = "\n".join([f"• @{u}" for u in active_tasks.keys()])
        await update.message.reply_text(f"🎥 Currently recording:\n{users}")


# -------------------------------
# Main Application
# -------------------------------
def main():
    print("🚀 Starting Telegram bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("record", record_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("list", list_command))

    app.run_polling()


if __name__ == "__main__":
    main()

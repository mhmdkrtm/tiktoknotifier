import os
import asyncio
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN") or "8348090543:AAG0cSjAFceozLxllCyCaWkRA9YPa55e_L4"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 أهلاً! اكتب /record <username> لتسجيل لايف من تيك توك.")

async def record(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ استخدم الأمر بالشكل التالي:\n/record username")
        return
    
    username = context.args[0].replace("@", "")
    await update.message.reply_text(f"🎥 بدأ التسجيل من حساب @{username} ...")

    # شغّل سكربت التسجيل (مثلاً tiktok-recorder.py)
    subprocess.Popen(["python3", "tiktok-recorder.py", username])

    await update.message.reply_text("✅ بدأ التسجيل (سيتم حفظ الفيديو تلقائيًا).")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("record", record))

    print("🤖 Telegram bot is running...")
    app.run_polling()

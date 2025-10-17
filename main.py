#!/usr/bin/env python3
"""
TikTok Live Monitor Bot
- Add/remove monitored TikTok usernames through Telegram
- Detect live streams in real time (TikTokLive)
- Fallback to periodic polling every 5 minutes if websocket fails
- Sends Telegram alerts + prints clear console logs
"""

import asyncio
import logging
import json
import re
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, LiveEndEvent, LiveStartEvent

# ---------------- CONFIG ----------------
API_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ADMIN_CHAT_ID = 123456789  # Replace with your Telegram ID
POLL_INTERVAL = 300  # 5 minutes
# ----------------------------------------

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
monitored_users = {}  # {username: {"live": bool, "method": "realtime"|"poll"}}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")


# ---------------- HELPER FUNCTIONS ----------------
async def check_live_status(username: str) -> bool:
    """Fallback check — Scrape TikTok HTML and parse live state."""
    url = f"https://www.tiktok.com/@{username}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            match = re.search(
                r'<script id="SIGI_STATE" type="application/json">(.*?)</script>', r.text
            )
            if not match:
                return False
            data = json.loads(match.group(1))
            user_info = data.get("UserModule", {}).get("users", {}).get(username)
            live_info = data.get("LiveRoom", {})
            if live_info or (user_info and user_info.get("isLive")):
                return True
            return False
    except Exception as e:
        logging.error(f"❌ Error checking {username}: {e}")
        return False


async def start_realtime_monitor(username: str):
    """Start TikTokLive websocket for real-time detection."""
    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent):
        monitored_users[username]["method"] = "realtime"
        logging.info(f"🟢 Real-time connected: @{username}")

    @client.on(LiveStartEvent)
    async def on_live_start(event: LiveStartEvent):
        monitored_users[username]["live"] = True
        logging.info(f"✅ @{username} is now LIVE!")
        await bot.send_message(ADMIN_CHAT_ID, f"🎥 @{username} has started a LIVE stream!")

    @client.on(LiveEndEvent)
    async def on_live_end(event: LiveEndEvent):
        monitored_users[username]["live"] = False
        logging.info(f"🔴 @{username} went offline.")
        await bot.send_message(ADMIN_CHAT_ID, f"⚪ @{username} ended the live stream.")

    try:
        await client.start()
    except Exception as e:
        logging.warning(f"⚠️ Real-time failed for @{username}: {e}")
        monitored_users[username]["method"] = "poll"
        # Start fallback polling instead
        while True:
            is_live = await check_live_status(username)
            if is_live and not monitored_users[username]["live"]:
                monitored_users[username]["live"] = True
                logging.info(f"✅ @{username} is LIVE (fallback)")
                await bot.send_message(ADMIN_CHAT_ID, f"🎬 @{username} went LIVE (fallback mode)")
            elif not is_live and monitored_users[username]["live"]:
                monitored_users[username]["live"] = False
                logging.info(f"🔴 @{username} went offline (fallback)")
                await bot.send_message(ADMIN_CHAT_ID, f"⚪ @{username} went offline (fallback mode)")
            await asyncio.sleep(POLL_INTERVAL)


# ---------------- TELEGRAM COMMANDS ----------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Welcome to TikTok Live Monitor!\nUse /add <username>, /remove <username>, /list, /status")


@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("❗ Usage: /add <tiktok_username>")

    username = args[1].replace("@", "").strip()
    if username in monitored_users:
        return await message.reply(f"⚠️ @{username} is already being monitored.")

    monitored_users[username] = {"live": False, "method": None}
    await message.reply(f"⏳ Checking @{username}...")

    try:
        asyncio.create_task(start_realtime_monitor(username))
        await asyncio.sleep(2)
        logging.info(f"👀 Started monitoring @{username}")
        await message.reply(f"✅ Monitoring started for @{username}")
    except Exception as e:
        logging.error(f"Error starting monitor for {username}: {e}")
        await message.reply(f"❌ Failed to monitor @{username}")


@dp.message(Command("remove"))
async def cmd_remove(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("❗ Usage: /remove <tiktok_username>")

    username = args[1].replace("@", "").strip()
    if username in monitored_users:
        del monitored_users[username]
        await message.reply(f"🗑️ Stopped monitoring @{username}")
    else:
        await message.reply(f"⚠️ @{username} is not being monitored.")


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    if not monitored_users:
        return await message.reply("📭 No monitored users yet.")
    msg = "\n".join([f"• @{u} ({'LIVE' if d['live'] else 'offline'})" for u, d in monitored_users.items()])
    await message.reply(f"📋 **Monitored Accounts:**\n{msg}", parse_mode="Markdown")


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if not monitored_users:
        return await message.reply("📭 No monitored users.")
    reply_lines = []
    for username, info in monitored_users.items():
        status = "🟢 LIVE" if info["live"] else "⚪ Offline"
        method = info["method"] or "checking..."
        reply_lines.append(f"@{username}: {status} ({method})")
    await message.reply("\n".join(reply_lines))


# ---------------- MAIN LOOP ----------------
async def main():
    logging.info("🤖 TikTok Live Monitor Bot Started.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

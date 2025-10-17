#!/usr/bin/env python3
"""
TikTok Live Monitor Bot
- Monitors TikTok users in real-time (TikTokLive)
- Fallback to periodic polling every 5 minutes
- Sends Telegram alerts
- Fully compatible with latest TikTokLive library
"""

import os
import asyncio
import logging
import json
import re
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, LiveEndEvent

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # Replace with your Telegram ID
POLL_INTERVAL = 300  # 5 minutes

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
monitored_users = {}  # {username: {"live": bool, "method": "realtime"|"poll"}}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")


# ---------------- HELPER FUNCTIONS ----------------
async def check_live_status(username: str) -> bool:
    """Fallback check — parse TikTok page JSON to determine live status."""
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
        logging.info(f"🟢 Connected (real-time) to @{username}")
        # Check immediately if live
        is_live = await check_live_status(username)
        monitored_users[username]["live"] = is_live
        if is_live:
            logging.info(f"✅ @{username} is currently LIVE!")
            if ADMIN_CHAT_ID:
                await bot.send_message(ADMIN_CHAT_ID, f"🎥 @{username} is LIVE!")
        else:
            logging.info(f"⚪ @{username} is currently offline.")
            if ADMIN_CHAT_ID:
                await bot.send_message(ADMIN_CHAT_ID, f"⚪ @{username} is offline.")

    @client.on(LiveEndEvent)
    async def on_live_end(event: LiveEndEvent):
        monitored_users[username]["live"] = False
        logging.info(f"🔴 @{username} went offline.")
        if ADMIN_CHAT_ID:
            await bot.send_message(ADMIN_CHAT_ID, f"⚪ @{username} ended the live stream.")

    @client.on(DisconnectEvent)
    async def on_disconnect(event: DisconnectEvent):
        logging.warning(f"⚠️ @{username} disconnected. Switching to polling.")
        monitored_users[username]["method"] = "poll"
        asyncio.create_task(polling_monitor(username))

    try:
        await client.start()
    except Exception as e:
        logging.warning(f"❌ Real-time failed for @{username}: {e}")
        monitored_users[username]["method"] = "poll"
        asyncio.create_task(polling_monitor(username))


# ---------------- POLLING FALLBACK ----------------
async def polling_monitor(username: str):
    """Check live status every POLL_INTERVAL seconds."""
    last_status = monitored_users[username].get("live", False)
    while username in monitored_users:
        try:
            is_live = await check_live_status(username)
            if is_live != last_status:
                last_status = is_live
                monitored_users[username]["live"] = is_live
                if is_live:
                    logging.info(f"✅ @{username} went LIVE (polling)")
                    if ADMIN_CHAT_ID:
                        await bot.send_message(ADMIN_CHAT_ID, f"🎥 @{username} went LIVE (polling)")
                else:
                    logging.info(f"🔴 @{username} went offline (polling)")
                    if ADMIN_CHAT_ID:
                        await bot.send_message(ADMIN_CHAT_ID, f"⚪ @{username} went offline (polling)")
        except Exception as e:
            logging.error(f"❌ Polling error for @{username}: {e}")
        await asyncio.sleep(POLL_INTERVAL)


# ---------------- TELEGRAM COMMANDS ----------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Welcome to TikTok Live Monitor!\n"
        "Use /add <username>, /remove <username>, /list, /status"
    )


@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("❗ Usage: /add <tiktok_username>")

    username = args[1].replace("@", "").strip()
    if username in monitored_users:
        return await message.reply(f"⚠️ @{username} is already monitored.")

    monitored_users[username] = {"live": False, "method": None}
    await message.reply(f"⏳ Checking @{username}...")
    asyncio.create_task(start_realtime_monitor(username))
    logging.info(f"👀 Started monitoring @{username}")
    await message.reply(f"✅ Monitoring started for @{username}")


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
        await message.reply(f"⚠️ @{username} is not monitored.")


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    if not monitored_users:
        return await message.reply("📭 No monitored users yet.")
    msg = "\n".join([f"• @{u} ({'LIVE' if d['live'] else 'offline'})" for u, d in monitored_users.items()])
    await message.reply(f"📋 Monitored Accounts:\n{msg}")


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


# ---------------- MAIN ----------------
async def main():
    logging.info("🤖 TikTok Live Monitor Bot Started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

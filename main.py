#!/usr/bin/env python3
"""
TikTok Live Monitor Bot (room_id method)
- Uses yt-dlp to get room_id
- Checks TikTok live API to detect actual live streams
- Telegram notifications for ONLINE/OFFLINE
"""

import os
import asyncio
import logging
import json
import subprocess
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", 0))  # Replace with your Telegram ID
POLL_INTERVAL = 300  # 5 minutes

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
monitored_users = {}  # {username: {"live": False, "room_id": None}}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")


# ---------------- HELPER FUNCTIONS ----------------
def get_room_id(username: str) -> str | None:
    """Use yt-dlp to get TikTok live room_id."""
    url = f"https://www.tiktok.com/@{username}"
    try:
        result = subprocess.run(
            ["yt-dlp", "-J", url],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(result.stdout)
        room_id = data.get("live_room", {}).get("room_id")
        return room_id
    except Exception as e:
        logging.error(f"❌ Failed to get room_id for @{username}: {e}")
        return None


async def is_user_live(room_id: str) -> bool:
    """Check TikTok live room API to see if user is live."""
    if not room_id:
        return False
    url = f"https://api2.musical.ly/aweme/v1/live/room/{room_id}/?aid=1988"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                # live_status 2 = live, 4 = offline
                return data.get("data", {}).get("status") == 2
            return False
    except Exception as e:
        logging.error(f"❌ Failed to check live status for room {room_id}: {e}")
        return False


async def polling_monitor(username: str):
    """Check live status every POLL_INTERVAL seconds."""
    user_data = monitored_users[username]
    last_status = user_data.get("live", False)
    room_id = user_data.get("room_id")

    while username in monitored_users:
        if not room_id:
            room_id = get_room_id(username)
            monitored_users[username]["room_id"] = room_id

        is_live = await is_user_live(room_id)
        if is_live != last_status:
            last_status = is_live
            monitored_users[username]["live"] = is_live
            if is_live:
                logging.info(f"✅ @{username} is LIVE")
                if ADMIN_CHAT_ID:
                    await bot.send_message(ADMIN_CHAT_ID, f"🎥 @{username} is LIVE!")
            else:
                logging.info(f"⚪ @{username} is OFFLINE")
                if ADMIN_CHAT_ID:
                    await bot.send_message(ADMIN_CHAT_ID, f"⚪ @{username} is OFFLINE")
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

    room_id = get_room_id(username)
    monitored_users[username] = {"live": False, "room_id": room_id}
    await message.reply(f"⏳ Starting monitoring @{username}...")
    asyncio.create_task(polling_monitor(username))
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
    msg = "\n".join([
        f"• @{u} ({'LIVE' if d['live'] else 'OFFLINE'})" 
        for u, d in monitored_users.items()
    ])
    await message.reply(f"📋 Monitored Accounts:\n{msg}")


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if not monitored_users:
        return await message.reply("📭 No monitored users.")
    reply_lines = []
    for username, info in monitored_users.items():
        status = "🟢 LIVE" if info["live"] else "⚪ OFFLINE"
        reply_lines.append(f"@{username}: {status}")
    await message.reply("\n".join(reply_lines))


# ---------------- MAIN ----------------
async def main():
    logging.info("🤖 TikTok Live Monitor Bot (room_id method) Started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

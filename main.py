#!/usr/bin/env python3
"""
TikTok Live Monitor Bot
- Add/remove monitored accounts via Telegram commands
- Detects live status via TikTokLive (real-time)
- Falls back to polling every 5 minutes if WebSocket fails
- Sends alerts to Telegram when a monitored user goes live or offline
"""

import os
import asyncio
import logging
from pathlib import Path
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from TikTokLive import TikTokLiveClient
from TikTokLive.types.events import ConnectEvent, DisconnectEvent, LiveEndEvent

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --- Env vars ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # optional if auto-registration used

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required! Set it in Railway environment variables.")

# --- Telegram setup ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Data structures ---
clients = {}  # username -> dict(client, status, mode)
CHECK_INTERVAL = 300  # 5 minutes


# --- Utility: check live status via TikTok web ---
async def check_live_status(username: str) -> bool:
    url = f"https://www.tiktok.com/@{username}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            return "LIVE" in r.text or '"isLive":true' in r.text
    except Exception as e:
        logging.error("Error checking %s: %s", username, e)
        return False


# --- Real-time TikTokLive monitoring ---
async def start_tiktok_live(username: str):
    """Try connecting via TikTokLive WebSocket. If fails, fallback to polling."""
    try:
        client = TikTokLiveClient(unique_id=username)

        @client.on("connect")
        async def on_connect(event: ConnectEvent):
            logging.info("Connected to %s (real-time mode)", username)
            clients[username]["status"] = "offline"
            clients[username]["mode"] = "realtime"

        @client.on("live_end")
        async def on_live_end(event: LiveEndEvent):
            logging.info("%s ended live.", username)
            clients[username]["status"] = "offline"
            if ADMIN_CHAT_ID:
                await bot.send_message(ADMIN_CHAT_ID, f"⚪ @{username} ended the live.")

        @client.on("disconnect")
        async def on_disconnect(event: DisconnectEvent):
            logging.warning("%s disconnected. Fallback to polling.", username)
            clients[username]["mode"] = "polling"
            asyncio.create_task(polling_monitor(username))

        clients[username]["client"] = client
        await client.start()
    except Exception as e:
        logging.warning("Failed real-time for %s: %s", username, e)
        clients[username]["mode"] = "polling"
        asyncio.create_task(polling_monitor(username))


# --- Polling fallback ---
async def polling_monitor(username: str):
    """Periodically check live status every 5 min."""
    last_status = clients[username].get("status", "offline")
    while username in clients:
        try:
            is_live = await check_live_status(username)
            current = "live" if is_live else "offline"
            if current != last_status:
                last_status = current
                clients[username]["status"] = current
                msg = f"🔴 @{username} just went LIVE!" if current == "live" else f"⚪ @{username} ended the live."
                logging.info(msg)
                if ADMIN_CHAT_ID:
                    await bot.send_message(ADMIN_CHAT_ID, msg)
        except Exception as e:
            logging.error("Polling error for %s: %s", username, e)
        await asyncio.sleep(CHECK_INTERVAL)


# --- Telegram Commands ---
@dp.message(Command("start"))
async def start_command(message: types.Message):
    global ADMIN_CHAT_ID
    ADMIN_CHAT_ID = str(message.chat.id)
    Path("admin.txt").write_text(ADMIN_CHAT_ID)
    await message.answer(
        "👋 Bot started!\n"
        "Your chat ID has been registered for alerts.\n"
        "Use /add <username> to monitor someone."
    )


@dp.message(Command("add"))
async def add_account(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /add <tiktok_username>")
        return
    username = args[1].lstrip("@")
    if username in clients:
        await message.answer(f"@{username} is already being monitored.")
        return
    clients[username] = {"status": "unknown", "mode": "connecting"}
    asyncio.create_task(start_tiktok_live(username))
    await message.answer(f"✅ Added @{username} to monitored list.")


@dp.message(Command("remove"))
async def remove_account(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /remove <tiktok_username>")
        return
    username = args[1].lstrip("@")
    if username in clients:
        client = clients[username].get("client")
        if client:
            await client.stop()
        del clients[username]
        await message.answer(f"❌ Removed @{username} from monitoring.")
    else:
        await message.answer(f"@{username} is not in the list.")


@dp.message(Command("list"))
async def list_accounts(message: types.Message):
    if not clients:
        await message.answer("No accounts are being monitored.")
        return
    text = "\n".join(
        f"@{u} — {d['status']} ({d['mode']})" for u, d in clients.items()
    )
    await message.answer("📋 Monitored accounts:\n" + text)


@dp.message(Command("status"))
async def status_command(message: types.Message):
    if not clients:
        await message.answer("No accounts are being monitored.")
        return
    lines = []
    for username, data in clients.items():
        status = data.get("status", "unknown")
        lines.append(f"@{username} — {'🟢 Live' if status == 'live' else '⚪ Offline'}")
    await message.answer("\n".join(lines))


# --- Startup ---
async def main():
    global ADMIN_CHAT_ID
    if Path("admin.txt").exists():
        ADMIN_CHAT_ID = Path("admin.txt").read_text().strip()
    logging.info("Bot started. Waiting for commands...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

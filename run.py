import asyncio
import os
from bot import run_bot
from main import watch_user, USERS_FILE

async def start_notifier():
    if not os.path.exists(USERS_FILE):
        print(f"File '{USERS_FILE}' not found!")
        return
    with open(USERS_FILE, "r") as f:
        users = [line.strip().replace("@", "") for line in f if line.strip() and not line.startswith("#")]
    if not users:
        print("No usernames found in users.txt")
        return
    print(f"🔥 Monitoring {len(users)} TikTok users: {', '.join(users)}")
    tasks = [asyncio.create_task(watch_user(u)) for u in users]
    await asyncio.gather(*tasks)

async def main():
    # Start bot first
    print("🤖 Starting Telegram bot...")
    bot_task = asyncio.create_task(run_bot())

    # Give bot a moment to initialize
    await asyncio.sleep(2)

    # Start notifier
    notifier_task = asyncio.create_task(start_notifier())

    await asyncio.gather(bot_task, notifier_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nService interrupted and shutting down.")

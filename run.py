import asyncio
from bot import run_bot
from main import main as notifier_main

async def run_all():
    bot_task = asyncio.create_task(run_bot())
    notifier_task = asyncio.create_task(notifier_main())
    await asyncio.gather(bot_task, notifier_task)

if __name__ == "__main__":
    asyncio.run(run_all())

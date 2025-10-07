import asyncio
import subprocess

async def run_all():
    bot = asyncio.create_task(asyncio.to_thread(subprocess.run, ["python3", "bot.py"]))
    notifier = asyncio.create_task(asyncio.to_thread(subprocess.run, ["python3", "main.py"]))
    await asyncio.gather(bot, notifier)

if __name__ == "__main__":
    asyncio.run(run_all())

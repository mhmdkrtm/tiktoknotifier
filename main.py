import os
import json
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, JobQueue
)
from TikTokLive import TikTokLiveClient
from TikTokLive.client.errors import FailedToConnect, AlreadyConnected
from TikTokLive.types.errors import UserNotFoundError

# --- Configuration and Environment Variables ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
try:
    AUTHORIZED_USER_ID = int(os.environ.get("AUTHORIZED_USER_ID"))
except (TypeError, ValueError):
    AUTHORIZED_USER_ID = None
    logging.error("AUTHORIZED_USER_ID is not set or is not a valid integer. Bot cannot function without it.")

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# File to store followed users data (used for persistence on Railway volume)
DATA_FILE = "followed_users.json"
POLLING_INTERVAL = 120 # Check every 120 seconds (2 minutes)

# --- Data Management Functions ---

def load_data():
    """Loads followed users and their stream status from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return {"users": {}}
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Corrupted or empty data file: {DATA_FILE}. Starting with empty data.")
            return {"users": {}}

def save_data(data):
    """Saves followed users and their stream status to the JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# Initialize data structure
data = load_data()

# --- Telegram Bot Utilities ---

async def auth_check(update: Update) -> bool:
    """Checks if the user is authorized to run commands."""
    if not AUTHORIZED_USER_ID or update.effective_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("⛔️ You are not authorized to use this bot.")
        return False
    return True

# --- Telegram Bot Commands ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and instructions."""
    if not await auth_check(update): return
    
    await update.message.reply_text(
        "👋 Welcome to the TikTok Notifier Bot! \n"
        "I will check for live streams every 2 minutes.\n\n"
        "**Available Commands:**\n"
        "/add <username> - Add a streamer (e.g., `/add user_name`).\n"
        "/remove <username> - Remove a streamer.\n"
        "/list - Show all monitored streamers."
    )

async def add_streamer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adds a streamer to the monitoring list."""
    if not await auth_check(update): return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/add <tiktok_username>` (e.g., `user_name`).")
        return

    username = context.args[0].lower().lstrip('@')
    
    if username in data["users"]:
        await update.message.reply_text(f"🔴 **{username}** is already being monitored.")
        return

    # Attempt an initial check to validate the username
    try:
        # Create a client with a short timeout to prevent blocking too long
        client = TikTokLiveClient(unique_id=username, **{"timeout_ms": 5000}) 
        room_info = await client.retrieve_room_info()
        
        # room_id exists if they are live
        is_online = bool(getattr(room_info, 'room_id', None))
        
        data["users"][username] = {
            "is_online": is_online
        }
        save_data(data)

        await update.message.reply_text(f"✅ Streamer **{username}** added. \nInitial status: {'🟢 **Online**' if is_online else '🔴 **Offline**'}.", parse_mode='Markdown')

    except UserNotFoundError:
        await update.message.reply_text(f"❌ TikTok user **'{username}'** not found.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error validating streamer {username}: {e}")
        # Add them anyway, but warn user, assuming the username might be correct
        data["users"][username] = {"is_online": False}
        save_data(data)
        await update.message.reply_text(f"⚠️ Added **{username}**, but initial validation failed/timed out. Will check later.", parse_mode='Markdown')


async def remove_streamer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes a streamer from the monitoring list."""
    if not await auth_check(update): return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/remove <tiktok_username>`")
        return

    username = context.args[0].lower().lstrip('@')

    if username in data["users"]:
        del data["users"][username]
        save_data(data)
        await update.message.reply_text(f"🗑️ Streamer **{username}** removed.")
    else:
        await update.message.reply_text(f"❌ Streamer **{username}** is not in the list.")


async def list_streamers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all monitored streamers and their last known status."""
    if not await auth_check(update): return

    if not data["users"]:
        await update.message.reply_text("📋 The monitoring list is currently empty. Use `/add <username>`.")
        return

    response = "📋 **Monitored TikTok Streamers:**\n\n"
    for username, info in data["users"].items():
        status = "🟢 ONLINE" if info.get("is_online") else "🔴 OFFLINE"
        response += f"- **{username}** ({status})\n"

    await update.message.reply_text(response, parse_mode='Markdown')

# --- Polling Job/Scheduler Function ---

async def check_tiktok_status(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled job to check all monitored streamers' status."""
    global data
    # Reload data from disk to ensure persistence across checks
    data = load_data() 

    if not data["users"]:
        logger.info("No users to check.")
        return

    bot = context.bot
    updated = False
    
    # Iterate over a list of keys to safely modify the dictionary during iteration
    for username in list(data["users"].keys()):
        info = data["users"].get(username)
        if not info: continue

        was_online = info.get("is_online", False)
        is_currently_online = False

        try:
            # We use retrieve_room_info to check for a room ID, which signals if a user is live.
            # Set a timeout (e.g., 10 seconds) for the HTTP request to prevent the job from hanging.
            client = TikTokLiveClient(unique_id=username, **{"timeout_ms": 10000}) 
            room_info = await client.retrieve_room_info()
            
            # Check for room_id attribute on the room_info object
            if getattr(room_info, 'room_id', None):
                is_currently_online = True

        except UserNotFoundError:
            logger.warning(f"User {username} not found during check. Removing.")
            del data["users"][username]
            updated = True
            continue
        except (FailedToConnect, AlreadyConnected) as e:
            # FailedToConnect typically means they are offline or a temporary issue.
            is_currently_online = False
        except Exception as e:
            logger.error(f"Unknown error checking status for {username}: {e}. Retaining last status.")
            # If a critical unknown error occurs, we assume the previous state remains.
            continue
            
        # 1. Stream went ONLINE (Transition: Offline -> Online)
        if is_currently_online and not was_online:
            message = (
                f"🚨 **{username} is NOW LIVE on TikTok!** 🚨\n\n"
                f"🔗 https://www.tiktok.com/@{username}/live"
            )
            await bot.send_message(chat_id=AUTHORIZED_USER_ID, text=message, parse_mode='Markdown')
            
            data["users"][username]["is_online"] = True
            updated = True

        # 2. Stream went OFFLINE (Transition: Online -> Offline)
        elif not is_currently_online and was_online:
            message = f"🚪 **{username}** has ended the live stream on TikTok."
            await bot.send_message(chat_id=AUTHORIZED_USER_ID, text=message, parse_mode='Markdown')

            data["users"][username]["is_online"] = False
            updated = True

    # Save the updated status only if changes occurred
    if updated:
        save_data(data)
        logger.info("Stream status updated and saved.")

# --- Main function to run the bot ---

def main() -> None:
    """Starts the bot."""
    if not TELEGRAM_BOT_TOKEN or AUTHORIZED_USER_ID is None:
        logger.error("Bot cannot start due to missing environment variables.")
        return

    # Set up Telegram Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    job_queue: JobQueue = application.job_queue

    # Add Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("add", add_streamer))
    application.add_handler(CommandHandler("remove", remove_streamer))
    application.add_handler(CommandHandler("list", list_streamers))

    # Add the scheduled job: check streams every POLLING_INTERVAL seconds
    job_queue.run_repeating(check_tiktok_status, interval=POLLING_INTERVAL, first=5)
    
    logger.info("Bot started. Polling job scheduled.")
    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Create the initial data file if it doesn't exist
    if not os.path.exists(DATA_FILE):
        save_data({"users": {}})
    main()

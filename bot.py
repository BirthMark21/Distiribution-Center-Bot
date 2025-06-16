# bot.py
import logging
import sys
import os
import asyncio

from telegram import Update # Added Update import for type hinting
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

import config
import gsheet_utils
import common_handlers

from handlers import create
from handlers import read
from handlers import update
from handlers import delete
from handlers import insights
from handlers.menu import main_menu_command_simple

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("gspread").setLevel(logging.INFO)
logging.getLogger("oauth2client").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

async def main() -> None:
    logger.info("Starting bot initialization...")

    if not config.BOT_TOKEN:
        logger.critical("CRITICAL: BOT_TOKEN is not found. Bot cannot start. Exiting.")
        return
    if not config.GSHEET_NAME:
        logger.error("ERROR: GOOGLE_SHEET_NAME not set. Google Sheet operations will likely fail.")
    if not config.WORKSHEET_NAME:
        logger.warning("WARNING: WORKSHEET_NAME not set. gsheet_utils will attempt to use the first available sheet.")

    logger.info("Attempting to connect to Google Sheets and initialize headers...")
    is_gsheet_ready, loaded_headers, worksheet_object = await gsheet_utils.connect_and_initialize_sheet()
    
    application_was_started = False # Flag to track if application.start() was successful

    try:
        if not is_gsheet_ready:
            logger.error(
                "Failed to connect to Google Sheets or worksheet not found during initial setup. "
                "Some functionalities will be impaired or unavailable. Bot will continue, but check GSheet config and permissions."
            )
        elif not loaded_headers:
            logger.error(
                "Google Sheet headers could not be loaded or are empty. "
                "This is critical for data operations. Please check the sheet structure or gsheet_utils.py. Bot will continue with caution."
            )
        else:
            ws_title = worksheet_object.title if worksheet_object else 'N/A (worksheet object is None!)'
            logger.info(f"Successfully connected to Google Sheet: '{config.GSHEET_NAME} - {ws_title}'.")
            logger.info(f"Bot initialized with GSheet Headers: {gsheet_utils.HEADERS}")

        application = (
            Application.builder()
            .token(config.BOT_TOKEN)
            .build()
        )
        logger.info("Telegram Application built.")

        logger.info("Registering conversation handlers...")
        application.add_handler(create.create_conv_handler)
        application.add_handler(read.read_conv_handler)
        application.add_handler(update.update_conv_handler)
        application.add_handler(delete.delete_conv_handler)
        application.add_handler(insights.insights_conv_handler)

        logger.info("Registering command handlers...")
        application.add_handler(CommandHandler("start", common_handlers.generic_start_command))
        application.add_handler(CommandHandler("help", common_handlers.generic_start_command))
        application.add_handler(CommandHandler("menu", main_menu_command_simple))

        logger.info("Registering global callback query handlers...")
        application.add_handler(
            CallbackQueryHandler(common_handlers.start_menu_callback, pattern=f"^{config.CB_OPEN_MENU_FROM_START}$")
        )
        
        if common_handlers.error_handler: # Check if error_handler is defined
            application.add_error_handler(common_handlers.error_handler)


        logger.info("Bot setup complete. Initializing and starting application...")
        await application.initialize() 
        await application.start()
        application_was_started = True # Mark as started
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
        ) 
        logger.info("Bot is now polling for updates. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(3600) 
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopping due to KeyboardInterrupt or SystemExit.")
    except Exception as e:
        logger.critical(f"Unhandled exception in main bot execution: {e}", exc_info=True)
    finally:
        logger.info("Attempting to stop the bot gracefully...")
        if application_was_started: # Only try to stop if it was started
            if application.updater and application.updater.running:
                logger.info("Stopping updater polling...")
                await application.updater.stop()
            
            try:
                if application._initialized: # Check internal flag
                     logger.info("Stopping application...")
                     await application.stop()
            except RuntimeError as e:
                if "This Application is not running!" in str(e):
                    logger.info("Application was not fully running, so stop command was skipped.")
                else:
                    logger.error(f"RuntimeError during application.stop(): {e}") # Log other runtime errors
            except Exception as e:
                logger.error(f"Exception during application.stop(): {e}", exc_info=True)

        if 'application' in locals() and hasattr(application, 'shutdown'): # ensure application exists
            logger.info("Shutting down application...")
            await application.shutdown() 
        logger.info("Bot has been stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            logger.warning("Main function seems to be called from an already running event loop.")
        else:
            raise
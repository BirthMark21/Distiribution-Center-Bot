import logging
import json
import traceback

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

# Import functions that will be called from the new handler
from handlers.menu import main_menu_command_simple
import keyboards
import config

logger = logging.getLogger(__name__)

# --- Standard Command Handlers ---

async def generic_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /start, /help, and the text 'start' by showing the main menu.
    """
    user = update.effective_user
    logger.info(f"User {user.first_name} (ID: {user.id}) triggered start/help, showing main menu.")
    await main_menu_command_simple(update, context)


async def start_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the 'Open Main Menu' button callback if it's used elsewhere.
    This is less common now that /start goes directly to the menu.
    """
    query = update.callback_query
    await query.answer()
    user = query.from_user
    logger.info(f"User {user.first_name} (ID: {user.id}) clicked 'Open Main Menu' button.")
    await main_menu_command_simple(update, context)


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Generic cancel handler that ends a conversation and shows navigation.
    """
    user = update.effective_user
    logger.info(f"User {user.first_name} (ID: {user.id}) canceled an operation.")
    
    text_to_send = "Operation canceled. What would you like to do next?"
    reply_markup = keyboards.build_post_action_keyboard() # Use the standard navigation keyboard

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text=text_to_send, reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(text=text_to_send, reply_markup=reply_markup)

    context.user_data.clear()
    return ConversationHandler.END


async def post_conversation_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles global navigation callbacks that might be clicked after a conversation
    has sent its final message. This acts as a fallback for all ConversationHandlers.
    """
    query = update.callback_query
    await query.answer()
    
    # We are leaving a conversation, so clear any leftover data.
    context.user_data.clear()
    
    # Check which navigation button was pressed.
    if query.data == f"{config.CB_MAIN_MENU_PREFIX}menu":
        logger.info(f"User {query.from_user.id} navigating to Main Menu from post-action keyboard.")
        await main_menu_command_simple(update, context)
        return ConversationHandler.END # End the previous conversation state.

    elif query.data == f"{config.CB_MAIN_MENU_PREFIX}new":
        logger.info(f"User {query.from_user.id} navigating to New Entry from post-action keyboard.")
        # Import dynamically to avoid circular dependencies.
        from handlers.create import start_new_entry
        # This will start the 'create' conversation, so we return its entry point state.
        return await start_new_entry(update, context)

    # If the callback is not a recognized navigation button, just end the conversation.
    logger.warning(f"Unhandled callback '{query.data}' caught in post_conversation_callback_handler.")
    return ConversationHandler.END


# --- Global Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global error handler. Logs errors and notifies the user.
    """
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

    # Format the traceback for logging.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    
    # For privacy, avoid logging the full update object in public logs if it contains sensitive user data.
    logger.error(f"Update causing error: {json.dumps(update_str, indent=2, ensure_ascii=False)[:1024]}...") # Log snippet
    logger.error(f"Traceback: {tb_string}")

    # Optionally, notify the user that an error occurred.
    if isinstance(update, Update) and update.effective_message:
        error_message_user = (
            "Sorry, an error occurred while processing your request.\n"
            "If the problem persists, please contact an administrator."
        )
        try:
            await update.effective_message.reply_text(error_message_user)
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
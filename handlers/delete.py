import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode
import asyncio

import config
import keyboards
import gsheet_utils
import common_handlers

logger = logging.getLogger(__name__)

# --- Conversation Handler Functions ---

async def start_delete_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the delete conversation by asking for an entry ID."""
    message = update.message or update.callback_query.message
    await message.reply_text("Please enter the ID of the entry you want to delete:")
    return config.DELETE_ASK_ID

async def ask_id_received_for_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the ID, finds the entry, and asks for confirmation."""
    entry_id = update.message.text.strip()
    
    row_num, entry_data_list = await asyncio.to_thread(gsheet_utils.find_row_by_id, entry_id)

    if not entry_data_list:
        await update.message.reply_text(f"No entry found with ID: {entry_id}. Please try again or /cancel.")
        return config.DELETE_ASK_ID

    context.user_data['delete_entry_id'] = entry_id
    context.user_data['delete_row_num'] = row_num

    # Format entry details for display
    entry_data_dict = dict(zip(gsheet_utils.HEADERS, entry_data_list))
    formatted_details = keyboards.format_entry_details_markdown(entry_data_dict)

    keyboard_layout = [
        [InlineKeyboardButton("🗑️ Yes, Delete it", callback_data=config.CB_DELETE_CONFIRM_YES)],
        [InlineKeyboardButton("❌ No, Keep it", callback_data=config.CB_DELETE_CONFIRM_NO)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard_layout)
    
    await update.message.reply_text(
        f"Found entry:\n{formatted_details}\n\n"
        "⚠️ **ARE YOU SURE** you want to delete this entry? This action cannot be undone.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return config.DELETE_CONFIRM

async def confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the final delete confirmation and shows navigation."""
    query = update.callback_query
    await query.answer()
    action = query.data

    final_message = ""
    if action == config.CB_DELETE_CONFIRM_YES:
        row_num = context.user_data['delete_row_num']
        entry_id = context.user_data['delete_entry_id']
        
        # Use asyncio.to_thread for the blocking gspread call
        success = await asyncio.to_thread(gsheet_utils.delete_row_from_sheet, row_num)
        
        if success:
            logger.info(f"Entry ID {entry_id} deleted by {query.from_user.first_name}.")
            escaped_id = keyboards._escape_markdown_v2_keyboards(entry_id)
            final_message = f"✅ Entry ID `{escaped_id}` has been deleted."
        else:
            logger.error(f"Failed to delete row {row_num} (ID {entry_id}) from GSheet.")
            final_message = "❌ Error deleting entry from Google Sheet."
    else: # CB_DELETE_CONFIRM_NO
        final_message = "Deletion canceled."

    final_message += "\n\nWhat would you like to do next?"
    reply_markup = keyboards.build_post_action_keyboard()

    await query.edit_message_text(
        text=keyboards._escape_markdown_v2_keyboards(final_message),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Conversation Handler Definition ---
delete_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("delete", start_delete_entry),
        CallbackQueryHandler(start_delete_entry, pattern=f"^{config.CB_MAIN_MENU_PREFIX}delete$")
    ],
    states={
        config.DELETE_ASK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_id_received_for_delete)],
        config.DELETE_CONFIRM: [CallbackQueryHandler(confirm_delete_callback, pattern=f"^({config.CB_DELETE_CONFIRM_YES}|{config.CB_DELETE_CONFIRM_NO})$")],
    },
    fallbacks=[
        CommandHandler("cancel", common_handlers.cancel_conversation),
        # This universal fallback handles the post-action navigation buttons.
        CallbackQueryHandler(common_handlers.post_conversation_callback_handler),
    ],
    per_message=False
)
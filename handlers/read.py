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

# --- Helper Functions ---
async def _send_or_edit_read(update: Update, text: str, reply_markup=None):
    """Helper to send or edit message for read operations, using MarkdownV2."""
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

def _escape_markdown_v2_read(text: str) -> str:
    """Escapes text for MarkdownV2."""
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f'\\{char}' if char in escape_chars else char for char in text)

# --- Main View Command and Initial Menu ---
async def view_entries_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /view. Displays options for viewing entries."""
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton(f"👁️ View Last {config.DEFAULT_ENTRIES_PER_PAGE_VIEW} Entries", callback_data=f"{config.CB_VIEW_LAST_N_PREFIX}0")],
        [InlineKeyboardButton("🆔 View Entry by ID", callback_data=config.CB_VIEW_BY_ID_PROMPT_ACTION)],
        [InlineKeyboardButton("❌ Cancel View", callback_data=config.CB_VIEW_CANCEL_ACTION)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await _send_or_edit_read(update, text=_escape_markdown_v2_read("How would you like to view entries?"), reply_markup=reply_markup)
    return config.VIEW_AWAITING_MENU_CHOICE

# --- View by ID Flow ---
async def prompt_for_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks user to send the ID."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=_escape_markdown_v2_read("Please send the ID of the entry you want to view:"))
    return config.VIEW_AWAITING_ID_INPUT

async def handle_id_for_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the ID, displays the entry, and shows navigation."""
    entry_id = update.message.text.strip()
    row_num, entry_data_list = await asyncio.to_thread(gsheet_utils.find_row_by_id, entry_id)
    
    nav_keyboard = keyboards.build_post_action_keyboard()
    final_message = ""

    if entry_data_list:
        entry_data_dict = dict(zip(gsheet_utils.HEADERS, entry_data_list))
        formatted_details = keyboards.format_entry_details_markdown(entry_data_dict)
        final_message = f"{formatted_details}\n\nWhat would you like to do next?"
    else:
        escaped_id = _escape_markdown_v2_read(entry_id)
        final_message = f"⚠️ No entry found with ID: `{escaped_id}`\n\nWhat would you like to do next?"
    
    await update.message.reply_text(text=final_message, reply_markup=nav_keyboard, parse_mode=ParseMode.MARKDOWN_V2)
    
    context.user_data.clear()
    return ConversationHandler.END

# --- View Last N Entries Flow with Pagination ---
async def view_last_entries_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles 'View Last N Entries' button, including pagination logic."""
    query = update.callback_query
    await query.answer()

    action_parts = query.data.split('_')
    current_page = 0
    if len(action_parts) >= 2 and action_parts[-1].isdigit():
        current_page = int(action_parts[-1])
        
    await query.edit_message_text(_escape_markdown_v2_read("🔄 Fetching entries..."))

    try:
        all_values = await asyncio.to_thread(gsheet_utils.worksheet.get_all_values)
        if not all_values or len(all_values) <= 1:
            await query.edit_message_text(
                _escape_markdown_v2_read("ℹ️ The sheet has no data entries.\n\nWhat would you like to do next?"),
                reply_markup=keyboards.build_post_action_keyboard()
            )
            return ConversationHandler.END

        header = gsheet_utils.HEADERS
        data_rows = list(reversed(all_values[1:]))
        total_entries = len(data_rows)
        per_page = config.DEFAULT_ENTRIES_PER_PAGE_VIEW
        start_index, end_index = current_page * per_page, (current_page + 1) * per_page
        page_entries = data_rows[start_index:end_index]

        if not page_entries:
            await query.answer("ℹ️ No more entries to display.", show_alert=True)
            return config.VIEW_PAGINATING_ENTRIES

        text_parts = [_escape_markdown_v2_read(f"Displaying Entries (Page {current_page + 1})")]
        for i, row in enumerate(page_entries):
            entry_num = total_entries - (start_index + i)
            text_parts.append(_escape_markdown_v2_read(f"\n--- Entry {entry_num} ---"))
            entry_dict = dict(zip(header, row))
            text_parts.append(keyboards.format_entry_details_markdown(entry_dict, title=""))
        
        nav_row = []
        if current_page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{config.CB_VIEW_LAST_N_PREFIX}{current_page - 1}"))
        if end_index < total_entries:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{config.CB_VIEW_LAST_N_PREFIX}{current_page + 1}"))
        
        markup = InlineKeyboardMarkup([nav_row, [InlineKeyboardButton("↩️ Back to View Options", callback_data=config.CB_VIEW_BACK_TO_MENU_ACTION)]])
        
        await _send_or_edit_read(update, text="\n".join(text_parts), reply_markup=markup)
        return config.VIEW_PAGINATING_ENTRIES

    except Exception as e:
        logger.error(f"Error fetching entries: {e}", exc_info=True)
        await query.edit_message_text(
            _escape_markdown_v2_read("⚠️ An error occurred while fetching data."),
            reply_markup=keyboards.build_post_action_keyboard()
        )
        return ConversationHandler.END

async def navigate_back_to_view_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles navigating back to the main view menu from pagination."""
    await update.callback_query.answer()
    return await view_entries_command(update, context)

async def cancel_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles 'Cancel View' button and shows navigation."""
    query = update.callback_query
    await query.answer()
    text = "View operation canceled.\n\nWhat would you like to do next?"
    await query.edit_message_text(text=text, reply_markup=keyboards.build_post_action_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# --- Conversation Handler Definition ---
read_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("view", view_entries_command),
        CallbackQueryHandler(view_entries_command, pattern=f"^{config.CB_MAIN_MENU_PREFIX}view$")
    ],
    states={
        config.VIEW_AWAITING_MENU_CHOICE: [ 
            CallbackQueryHandler(prompt_for_id_callback, pattern=f"^{config.CB_VIEW_BY_ID_PROMPT_ACTION}$"),
            CallbackQueryHandler(view_last_entries_callback, pattern=f"^{config.CB_VIEW_LAST_N_PREFIX}\\d+$"),
            CallbackQueryHandler(cancel_view_callback, pattern=f"^{config.CB_VIEW_CANCEL_ACTION}$"),
        ],
        config.VIEW_AWAITING_ID_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id_for_view),
        ],
        config.VIEW_PAGINATING_ENTRIES: [ 
            CallbackQueryHandler(view_last_entries_callback, pattern=f"^{config.CB_VIEW_LAST_N_PREFIX}\\d+$"),
            CallbackQueryHandler(navigate_back_to_view_menu, pattern=f"^{config.CB_VIEW_BACK_TO_MENU_ACTION}$"),
            CallbackQueryHandler(cancel_view_callback, pattern=f"^{config.CB_VIEW_CANCEL_ACTION}$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", common_handlers.cancel_conversation), 
        CallbackQueryHandler(cancel_view_callback, pattern=f"^{config.CB_VIEW_CANCEL_ACTION}$"),
        # This universal fallback handles the post-action navigation buttons.
        CallbackQueryHandler(common_handlers.post_conversation_callback_handler),
    ],
    per_message=False,
)
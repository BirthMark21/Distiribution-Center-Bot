import logging
from datetime import datetime
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
import gspread  # Required for batch updates

import config
import keyboards
import gsheet_utils
import common_handlers

logger = logging.getLogger(__name__)

# --- Constants and Mappings for Update Handler ---
UPDATABLE_FIELDS_MAP = {
    "product": config.PRODUCT_FIELD,
    "price": config.PRICE_FIELD,
    "location": config.LOCATION_FIELD,
    "remark": config.REMARK_FIELD,
}
UPDATABLE_FIELDS_DISPLAY_ORDER = ["product", "price", "location", "remark"]

# --- Helper Functions ---
async def _send_or_edit_update(update: Update, text: str, reply_markup=None, parse_mode=None):
    """Helper to send or edit a message, tailored for update operations."""
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    elif update.message:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)

def _escape_markdown(text: str) -> str:
    """A local helper to escape text for MarkdownV2."""
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f'\\{char}' if char in escape_chars else char for char in text)

# --- Conversation Handler Functions ---
async def start_update_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the update conversation by asking for an entry ID."""
    message = update.message or update.callback_query.message
    await message.reply_text("✏️ Please enter the ID of the entry you wish to update:")
    return config.UPDATE_ASK_ID

async def ask_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the entry ID, finds it, and moves to field selection."""
    entry_id = update.message.text.strip()
    row_num, entry_data_list = await asyncio.to_thread(gsheet_utils.find_row_by_id, entry_id)

    if not entry_data_list:
        await update.message.reply_text(f"⚠️ No entry found with ID: `{entry_id}`. Please try again, or /cancel.", parse_mode=ParseMode.MARKDOWN_V2)
        return config.UPDATE_ASK_ID

    context.user_data.update({
        'update_entry_id': entry_id,
        'update_row_num': row_num,
        'update_original_data': dict(zip(gsheet_utils.HEADERS, entry_data_list)),
        'fields_to_update_selected_keys': [],
        'new_values_for_update_map': {}
    })
    return await show_field_selection_for_update(update, context)

async def show_field_selection_for_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays a checklist of fields the user can choose to update."""
    original_data = context.user_data['update_original_data']
    selected_keys = context.user_data.get('fields_to_update_selected_keys', [])
    
    rows = []
    for key in UPDATABLE_FIELDS_DISPLAY_ORDER:
        field = UPDATABLE_FIELDS_MAP[key]
        value = str(original_data.get(field, "N/A"))
        display_value = value[:15] + "..." if len(value) > 15 else value
        emoji = "✅" if key in selected_keys else "☑️"
        rows.append([InlineKeyboardButton(f"{emoji} {key.title()}: {display_value}", callback_data=f"{config.CB_UPDATE_FIELD_TOGGLE_PREFIX}{key}")])

    rows.append([InlineKeyboardButton("➡️ Proceed with Selection", callback_data=config.CB_UPDATE_PROCEED_WITH_SELECTION)])
    rows.append([InlineKeyboardButton("❌ Cancel Update", callback_data=config.CB_UPDATE_CANCEL_FIELD_SELECTION)])
    
    formatted_entry = keyboards.format_entry_details_markdown(original_data)
    message_text = (
        f"✏️ *Updating Entry ID: `{context.user_data['update_entry_id']}`*\n\n"
        f"{formatted_entry}\n\nSelect fields to update, then click 'Proceed'."
    )
    await _send_or_edit_update(update, text=message_text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN_V2)
    return config.UPDATE_SELECT_FIELDS_TOGGLE

async def toggle_field_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles toggling a field in the checklist."""
    query = update.callback_query
    await query.answer()
    key = query.data.replace(config.CB_UPDATE_FIELD_TOGGLE_PREFIX, "")
    selected = context.user_data.get('fields_to_update_selected_keys', [])
    if key in selected:
        selected.remove(key)
    else:
        selected.append(key)
    return await show_field_selection_for_update(update, context)

async def proceed_with_selected_fields_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Checks if fields were selected and proceeds to ask for new values."""
    query = update.callback_query
    await query.answer()
    selected_keys = context.user_data.get('fields_to_update_selected_keys', [])
    if not selected_keys:
        await query.answer("Please select at least one field to update.", show_alert=True)
        return config.UPDATE_SELECT_FIELDS_TOGGLE

    context.user_data['update_fields_queue'] = [key for key in UPDATABLE_FIELDS_DISPLAY_ORDER if key in selected_keys]
    return await ask_for_next_field_value(update, context)

async def ask_for_next_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks for the new value of the next field in the update queue."""
    queue = context.user_data.get('update_fields_queue', [])
    if not queue:
        return await confirm_multiple_changes(update, context)

    key = queue[0]
    context.user_data['current_field_being_updated_key'] = key
    original_value = context.user_data['update_original_data'].get(UPDATABLE_FIELDS_MAP[key], "N/A")
    
    text, markup = "", None
    escaped_original = _escape_markdown(str(original_value))
    if key == "product":
        text = f"Select new *Product* (current: `{escaped_original}`):"
        markup = keyboards.build_keyboard(config.PRODUCTS, prefix=config.CB_UPDATE_NEWVAL_PRODUCT_PREFIX)
    elif key == "location":
        text = f"Select new *Location* (current: `{escaped_original}`):"
        markup = keyboards.build_keyboard(config.LOCATIONS, prefix=config.CB_UPDATE_NEWVAL_LOCATION_PREFIX)
    elif key == "price":
        text = f"Enter new *Price* (current: `{escaped_original}`):"
    elif key == "remark":
        text = f"Enter new *Remark* (current: `{escaped_original}`)\nor use /skip_remark_update."

    await _send_or_edit_update(update, text=text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN_V2)
    return config.UPDATE_ENTER_MULTIPLE_VALUES

async def new_value_for_product_or_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles button clicks for new product or location values."""
    query = update.callback_query
    await query.answer()
    key = context.user_data['current_field_being_updated_key']
    
    prefix = config.CB_UPDATE_NEWVAL_PRODUCT_PREFIX if key == "product" else config.CB_UPDATE_NEWVAL_LOCATION_PREFIX
    slug = query.data.replace(prefix, "")
    new_value = keyboards.clean_and_format_for_display(slug)
    
    context.user_data['new_values_for_update_map'][UPDATABLE_FIELDS_MAP[key]] = new_value
    context.user_data['update_fields_queue'].pop(0)
    return await ask_for_next_field_value(update, context)

async def new_value_for_text_field_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles text input for new price or remark values."""
    key = context.user_data['current_field_being_updated_key']
    new_value = update.message.text
    
    if key == "price":
        try:
            new_value = float(new_value)
            if new_value <= 0: raise ValueError
        except (ValueError, TypeError):
            await update.message.reply_text("⚠️ Invalid price. Please enter a positive number.")
            return config.UPDATE_ENTER_MULTIPLE_VALUES
    
    context.user_data['new_values_for_update_map'][UPDATABLE_FIELDS_MAP[key]] = new_value
    context.user_data['update_fields_queue'].pop(0)
    return await ask_for_next_field_value(update, context)

async def skip_remark_update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the /skip_remark_update command."""
    if context.user_data.get('current_field_being_updated_key') == "remark":
        context.user_data['new_values_for_update_map'][config.REMARK_FIELD] = ""
        context.user_data['update_fields_queue'].pop(0)
        return await ask_for_next_field_value(update, context)
    await update.message.reply_text("This command is only for the remark field.")
    return config.UPDATE_ENTER_MULTIPLE_VALUES

async def confirm_multiple_changes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Shows a final summary of all proposed changes."""
    new_values = context.user_data['new_values_for_update_map']
    if not new_values:
        text = "No changes were made. Update canceled.\n\nWhat would you like to do next?"
        await _send_or_edit_update(update, text=text, reply_markup=keyboards.build_post_action_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    summary = ["*Confirm Changes:*"]
    for field, value in new_values.items():
        field_name = keyboards.clean_and_format_for_display(field)
        original = context.user_data['update_original_data'].get(field, "N/A")
        summary.append(f"  - *{field_name}:* `{_escape_markdown(str(original))}` ➡️ `{_escape_markdown(str(value))}`")

    summary.append("\nApply these updates?")
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Apply Updates", callback_data=config.CB_UPDATE_EXECUTE_CONFIRMED)],
        [InlineKeyboardButton("❌ No, Cancel", callback_data=config.CB_UPDATE_CANCEL_FINAL_CONFIRM)],
    ])
    await _send_or_edit_update(update, text="\n".join(summary), reply_markup=markup, parse_mode=ParseMode.MARKDOWN_V2)
    return config.UPDATE_CONFIRM_MULTIPLE

async def execute_multiple_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Executes the batch update on the Google Sheet."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔄 Applying updates...")

    row_num = context.user_data['update_row_num']
    new_values = context.user_data['new_values_for_update_map']
    
    update_ops = []
    for field, value in new_values.items():
        try:
            col_num = gsheet_utils.HEADERS.index(field) + 1
            update_ops.append({'range': gspread.utils.rowcol_to_a1(row_num, col_num), 'values': [[value]]})
        except ValueError:
            logger.error(f"Field '{field}' not found in HEADERS. Cannot update.")
    
    # Also update the timestamp to reflect the modification time
    try:
        ts_col = gsheet_utils.HEADERS.index(config.TIMESTAMP_FIELD) + 1
        update_ops.append({'range': gspread.utils.rowcol_to_a1(row_num, ts_col), 'values': [[datetime.now().isoformat()]]})
    except ValueError:
        logger.warning(f"Timestamp field '{config.TIMESTAMP_FIELD}' not found. Skipping timestamp update.")

    success = False
    if update_ops:
        success = await asyncio.to_thread(gsheet_utils.worksheet.batch_update, update_ops)

    entry_id = context.user_data['update_entry_id']
    if success:
        final_message = f"✅ Entry ID `{_escape_markdown(entry_id)}` updated successfully."
    else:
        final_message = f"❌ Error! Could not update entry ID `{_escape_markdown(entry_id)}`."

    final_message += "\n\nWhat would you like to do next?"
    reply_markup = keyboards.build_post_action_keyboard()
    
    await query.edit_message_text(text=final_message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_update_operation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the update operation and shows navigation."""
    query = update.callback_query
    await query.answer()
    text = "Update operation has been canceled.\n\nWhat would you like to do next?"
    await query.edit_message_text(text=text, reply_markup=keyboards.build_post_action_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# --- Conversation Handler Definition ---
update_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("update", start_update_entry),
        CallbackQueryHandler(start_update_entry, pattern=f"^{config.CB_MAIN_MENU_PREFIX}update$")
    ],
    states={
        config.UPDATE_ASK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_id_received)],
        config.UPDATE_SELECT_FIELDS_TOGGLE: [
            CallbackQueryHandler(toggle_field_selection_callback, pattern=f"^{config.CB_UPDATE_FIELD_TOGGLE_PREFIX}.*"),
            CallbackQueryHandler(proceed_with_selected_fields_callback, pattern=f"^{config.CB_UPDATE_PROCEED_WITH_SELECTION}$"),
            CallbackQueryHandler(cancel_update_operation_callback, pattern=f"^{config.CB_UPDATE_CANCEL_FIELD_SELECTION}$")
        ],
        config.UPDATE_ENTER_MULTIPLE_VALUES: [
            CallbackQueryHandler(new_value_for_product_or_location_callback, pattern=f"^({config.CB_UPDATE_NEWVAL_PRODUCT_PREFIX}|{config.CB_UPDATE_NEWVAL_LOCATION_PREFIX}).*"),
            CommandHandler("skip_remark_update", skip_remark_update_command),
            MessageHandler(filters.TEXT & ~filters.COMMAND, new_value_for_text_field_received)
        ],
        config.UPDATE_CONFIRM_MULTIPLE: [
            CallbackQueryHandler(execute_multiple_updates, pattern=f"^{config.CB_UPDATE_EXECUTE_CONFIRMED}$"),
            CallbackQueryHandler(common_handlers.cancel_conversation, pattern=f"^{config.CB_UPDATE_CANCEL_FINAL_CONFIRM}$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", common_handlers.cancel_conversation),
        # This universal fallback handles the post-action navigation buttons.
        CallbackQueryHandler(common_handlers.post_conversation_callback_handler),
    ],
    per_message=False
)
import logging
import uuid
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
import asyncio

import config
import keyboards
import gsheet_utils
import common_handlers

logger = logging.getLogger(__name__)

# --- Helper Functions ---
def _get_current_entry_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if 'current_entry' not in context.user_data:
        context.user_data['current_entry'] = {}
    return context.user_data['current_entry']

def _clear_current_entry_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'current_entry' in context.user_data:
        del context.user_data['current_entry']

async def _send_or_edit(update: Update, text: str, reply_markup=None):
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(text=text, reply_markup=reply_markup)
    else:
        logger.error("Cannot send or edit: No message or callback_query in update.")

# --- Conversation Start and Type Selection ---
async def start_new_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the 'create new entry' conversation."""
    user = update.effective_user
    logger.info(f"User {user.first_name} (ID: {user.id}) started /new entry process.")
    context.user_data.clear()
    
    keyboard = [
        [InlineKeyboardButton("☝️ Add Single Product", callback_data=config.CB_CREATE_CHOOSE_TYPE_SINGLE)],
        [InlineKeyboardButton("📦 Add Batch of Products", callback_data=config.CB_CREATE_CHOOSE_TYPE_BATCH)],
        [InlineKeyboardButton("❌ Cancel", callback_data=config.CB_CREATE_CANCEL_ENTIRE)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await _send_or_edit(update, text="How would you like to add new data?", reply_markup=reply_markup)
    return config.CREATE_CHOOSE_ENTRY_TYPE

async def handle_entry_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the user's choice of entry type (single or batch)."""
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == config.CB_CREATE_CHOOSE_TYPE_SINGLE:
        return await ask_single_entry_product(update, context)
    elif choice == config.CB_CREATE_CHOOSE_TYPE_BATCH:
        # Initialize data structures for the new batch flow
        context.user_data['batch_entries'] = []
        context.user_data['batch_selected_products'] = []
        return await ask_batch_common_location(update, context)
    elif choice == config.CB_CREATE_CANCEL_ENTIRE:
        return await common_handlers.cancel_conversation(update, context)
        
    return config.CREATE_CHOOSE_ENTRY_TYPE

# --- Batch Entry Flow (New: Multi-Product Selection) ---

async def ask_batch_common_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks for the common location for the entire batch."""
    keyboard = keyboards.build_keyboard(config.LOCATIONS, prefix=config.CB_CREATE_BATCH_COMMON_LOCATION_PREFIX)
    await _send_or_edit(update, text="--- Batch Entry ---\nPlease select a common LOCATION for this batch:", reply_markup=keyboard)
    return config.CREATE_BATCH_SELECT_LOCATION

async def batch_common_location_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the common location and asks for common remarks."""
    query = update.callback_query
    await query.answer()
    raw_location_slug = query.data.replace(config.CB_CREATE_BATCH_COMMON_LOCATION_PREFIX, "")
    selected_location = keyboards.clean_and_format_for_display(raw_location_slug)
    context.user_data["batch_common_location"] = selected_location
    
    await query.edit_message_text(
        f"✅ Batch Location: {selected_location}\n\n"
        "Now, please enter common remarks for this batch, or use /skip_remark_batch."
    )
    return config.CREATE_BATCH_ENTER_REMARK

async def batch_common_remark_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the common remark and proceeds to product selection."""
    context.user_data["batch_common_remark"] = update.message.text
    await update.message.reply_text("✅ Batch Remark set.")
    return await ask_batch_products_selection(update, context)

async def batch_skip_common_remark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skips the common remark and proceeds to product selection."""
    context.user_data["batch_common_remark"] = ""
    await update.message.reply_text("✅ Batch Remark skipped.")
    return await ask_batch_products_selection(update, context)

async def ask_batch_products_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays a checklist of products for the user to select multiple items."""
    selected_products = context.user_data.setdefault('batch_selected_products', [])
    
    buttons = []
    for product in config.PRODUCTS:
        status_emoji = "✅" if product in selected_products else "☑️"
        # Create a "slug" from the product name for the callback data
        product_slug = product.replace(' ', '_').lower()
        buttons.append(
            InlineKeyboardButton(
                f"{status_emoji} {product}",
                callback_data=f"{config.CB_CREATE_BATCH_PRODUCT_TOGGLE_PREFIX}{product_slug}"
            )
        )
    
    # Arrange buttons in two columns for better readability on mobile
    keyboard_rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    keyboard_rows.append([InlineKeyboardButton("➡️ Done Selecting Products", callback_data=config.CB_CREATE_BATCH_PRODUCTS_DONE)])
    
    num_selected = len(selected_products)
    message_text = (
        f"--- Batch Product Selection ---\n"
        f"Location: {context.user_data['batch_common_location']}\n\n"
        f"Select all products for this batch. You have selected {num_selected} product(s).\n"
        "Click 'Done' when you are finished."
    )
    
    await _send_or_edit(update, text=message_text, reply_markup=InlineKeyboardMarkup(keyboard_rows))
    return config.CREATE_BATCH_TOGGLE_PRODUCTS

async def toggle_batch_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Adds or removes a product from the selection list and redraws the checklist."""
    query = update.callback_query
    await query.answer()
    
    raw_product_slug = query.data.replace(config.CB_CREATE_BATCH_PRODUCT_TOGGLE_PREFIX, "")
    product_name = keyboards.clean_and_format_for_display(raw_product_slug)
    
    selected_products = context.user_data.setdefault('batch_selected_products', [])
    if product_name in selected_products:
        selected_products.remove(product_name)
    else:
        selected_products.append(product_name)
        
    # Redraw the product selection menu with the updated state
    return await ask_batch_products_selection(update, context)

async def batch_products_selection_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Moves to the price entry stage after product selection is complete."""
    query = update.callback_query
    selected_products = context.user_data.get('batch_selected_products', [])
    
    if not selected_products:
        await query.answer("Please select at least one product before proceeding.", show_alert=True)
        return config.CREATE_BATCH_TOGGLE_PRODUCTS
        
    # Create a queue of products for which to ask the price
    context.user_data['batch_price_queue'] = selected_products.copy()
    context.user_data['batch_entries'] = [] # Reset entries list
    return await ask_next_price_for_batch(update, context)

async def ask_next_price_for_batch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks for the price of the next product in the queue."""
    price_queue = context.user_data.get('batch_price_queue', [])
    
    if not price_queue:
        # All prices entered, move to final confirmation
        return await show_batch_confirmation(update, context)
        
    current_product = price_queue[0]
    context.user_data['batch_current_product_for_price'] = current_product
    
    await _send_or_edit(update, text=f"Please enter the buying price for: *{current_product}*")
    return config.CREATE_BATCH_ENTER_PRICE

async def batch_price_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles price entry for a product in the batch queue."""
    try:
        price = float(update.message.text)
        if price <= 0:
            raise ValueError("Price must be positive.")
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Invalid price. Please enter a positive number (e.g., 120.50):")
        return config.CREATE_BATCH_ENTER_PRICE

    product_name = context.user_data.pop('batch_current_product_for_price', None)
    if not product_name:
        logger.warning("batch_price_entry called without a product in context. Canceling.")
        await update.message.reply_text("An error occurred. Please start over.")
        return await common_handlers.cancel_conversation(update, context)

    price_queue = context.user_data.get('batch_price_queue', [])
    if price_queue:
        price_queue.pop(0)

    # Store the processed entry
    entry_data = {
        'product': product_name,
        'price': price,
        'location': context.user_data['batch_common_location'],
        'remark': context.user_data.get('batch_common_remark', '')
    }
    context.user_data['batch_entries'].append(entry_data)
    logger.info(f"Price for '{product_name}' set to {price}. Added to batch.")

    # Ask for the next price in the queue
    return await ask_next_price_for_batch(update, context)

async def show_batch_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays a final summary of the entire batch before submission."""
    batch_entries = context.user_data.get('batch_entries', [])
    if not batch_entries:
        await _send_or_edit(update, "No entries were created. Operation canceled.")
        return await common_handlers.cancel_conversation(update, context)
    
    summary_parts = [
        "--- Confirm Batch Submission ---",
        f"**Location:** {context.user_data['batch_common_location']}",
        f"**Remark:** {context.user_data.get('batch_common_remark') or 'None'}\n",
        "**Products & Prices:**"
    ]
    for i, entry in enumerate(batch_entries):
        summary_parts.append(f"{i+1}. {entry['product']}: **{entry['price']}**")
    summary_parts.append("\nSubmit this batch to the sheet?")
    
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Submit Batch", callback_data=config.CB_CREATE_BATCH_SUBMIT_FINAL)],
        [InlineKeyboardButton("❌ No, Cancel", callback_data=config.CB_CREATE_BATCH_CANCEL_CONFIRM)],
    ]
    await _send_or_edit(update, text="\n".join(summary_parts), reply_markup=InlineKeyboardMarkup(keyboard))
    return config.CREATE_BATCH_CONFIRM_SUBMISSION

async def submit_batch_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Submits the entire batch to the Google Sheet and shows navigation."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔄 Submitting batch entries... This may take a moment.")

    batch_entries_data = context.user_data.get('batch_entries', [])
    rows_to_append = []
    user_identifier = query.from_user.username if query.from_user.username else str(query.from_user.id)

    for item in batch_entries_data:
        row_data = {
            config.ID_FIELD: str(uuid.uuid4()),
            config.TIMESTAMP_FIELD: datetime.now().isoformat(),
            config.EMAIL_FIELD: user_identifier,
            config.PRODUCT_FIELD: item.get('product'),
            config.PRICE_FIELD: item.get('price'),
            config.LOCATION_FIELD: item.get('location'),
            config.REMARK_FIELD: item.get('remark')
        }
        rows_to_append.append([row_data.get(h, "") for h in gsheet_utils.HEADERS])
    
    success = await asyncio.to_thread(gsheet_utils.append_rows_to_sheet, rows_to_append)
    
    if success:
        final_message = f"✅ Batch with {len(rows_to_append)} entries submitted successfully."
        logger.info(f"Batch of {len(rows_to_append)} submitted by user {user_identifier}")
    else:
        final_message = "❌ Batch submission failed. Please contact an admin."
        logger.error(f"Batch submission failed for user {user_identifier}")
        
    final_message += "\n\nWhat would you like to do next?"
    reply_markup = keyboards.build_post_action_keyboard()
    
    await query.edit_message_text(text=final_message, reply_markup=reply_markup)
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Single Entry Flow Functions ---

async def ask_single_entry_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_current_entry_data(context)
    keyboard = keyboards.build_keyboard(config.PRODUCTS, prefix=config.CB_CREATE_SINGLE_PRODUCT_PREFIX)
    await _send_or_edit(update, text="--- Single Product Entry ---\nPlease select the Product:", reply_markup=keyboard)
    return config.CREATE_SINGLE_SELECT_PRODUCT

async def single_entry_product_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    raw_product_slug = query.data.replace(config.CB_CREATE_SINGLE_PRODUCT_PREFIX, "")
    selected_product = keyboards.clean_and_format_for_display(raw_product_slug)
    current_entry = _get_current_entry_data(context)
    current_entry["product"] = selected_product
    await query.edit_message_text(f"Product: {selected_product}\n\nPlease enter the buying price (e.g., 120.50):")
    return config.CREATE_SINGLE_ENTER_PRICE

async def single_entry_price_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    price_text = update.message.text
    current_entry = _get_current_entry_data(context)
    try:
        price = float(price_text)
        if price <= 0: raise ValueError
        current_entry["price"] = price
        keyboard = keyboards.build_keyboard(config.LOCATIONS, prefix=config.CB_CREATE_SINGLE_LOCATION_PREFIX)
        await update.message.reply_text(
            f"Product: {current_entry['product']}\nPrice: {price}\n\nPlease select the Location:",
            reply_markup=keyboard
        )
        return config.CREATE_SINGLE_SELECT_LOCATION
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Invalid price. Please enter a positive number:")
        return config.CREATE_SINGLE_ENTER_PRICE

async def single_entry_location_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    raw_location_slug = query.data.replace(config.CB_CREATE_SINGLE_LOCATION_PREFIX, "")
    selected_location = keyboards.clean_and_format_for_display(raw_location_slug)
    current_entry = _get_current_entry_data(context)
    current_entry["location"] = selected_location
    await query.edit_message_text(
        f"Product: {current_entry['product']}\nPrice: {current_entry['price']}\nLocation: {selected_location}\n\n"
        "Please enter remarks, or use /skip_remark_single."
    )
    return config.CREATE_SINGLE_ENTER_REMARK

async def single_entry_remark_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current_entry = _get_current_entry_data(context)
    current_entry["remark"] = update.message.text
    await update.message.reply_text("✅ Remark set.")
    return await show_single_entry_confirmation(update, context)

async def single_skip_remark_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current_entry = _get_current_entry_data(context)
    current_entry["remark"] = ""
    await update.message.reply_text("✅ Remark skipped.")
    return await show_single_entry_confirmation(update, context)

async def show_single_entry_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current_entry = _get_current_entry_data(context)
    summary = (
        "--- Confirm Single Entry ---\n\n"
        f"Product: {current_entry.get('product')}\n"
        f"Price: {current_entry.get('price')}\n"
        f"Location: {current_entry.get('location')}\n"
        f"Remark: {current_entry.get('remark') or 'None'}\n\n"
        "Submit this entry?"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Submit", callback_data=config.CB_CREATE_SINGLE_SUBMIT_FINAL)],
        [InlineKeyboardButton("❌ No, Cancel", callback_data=config.CB_CREATE_SINGLE_CANCEL_CONFIRM)],
    ]
    await _send_or_edit(update, text=summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return config.CREATE_SINGLE_CONFIRM_SUBMISSION

async def submit_single_entry_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Submits the confirmed single entry and shows navigation."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔄 Submitting entry...")
    
    entry_data = _get_current_entry_data(context)
    user_identifier = query.from_user.username if query.from_user.username else str(query.from_user.id)
    
    entry_id = str(uuid.uuid4())
    row_data = {
        config.ID_FIELD: entry_id,
        config.TIMESTAMP_FIELD: datetime.now().isoformat(),
        config.EMAIL_FIELD: user_identifier,
        config.PRODUCT_FIELD: entry_data.get('product'),
        config.PRICE_FIELD: entry_data.get('price'),
        config.LOCATION_FIELD: entry_data.get('location'),
        config.REMARK_FIELD: entry_data.get('remark', '')
    }
    
    row_values = [row_data.get(h, "") for h in gsheet_utils.HEADERS]
    success = await asyncio.to_thread(gsheet_utils.append_rows_to_sheet, [row_values])
    
    if success:
        final_message = f"✅ Entry submitted successfully.\nID: {entry_id}"
    else:
        final_message = "❌ Entry submission failed. Please contact an admin."
        
    final_message += "\n\nWhat would you like to do next?"
    reply_markup = keyboards.build_post_action_keyboard()
    
    await query.edit_message_text(text=final_message, reply_markup=reply_markup)
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Conversation Handler Definition ---
create_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("new", start_new_entry),
        CallbackQueryHandler(start_new_entry, pattern=f"^{config.CB_MAIN_MENU_PREFIX}new$")
    ],
    states={
        config.CREATE_CHOOSE_ENTRY_TYPE: [
            CallbackQueryHandler(handle_entry_type_selection, pattern=f"^({config.CB_CREATE_CHOOSE_TYPE_SINGLE}|{config.CB_CREATE_CHOOSE_TYPE_BATCH}|{config.CB_CREATE_CANCEL_ENTIRE})$")
        ],
        # --- Batch States ---
        config.CREATE_BATCH_SELECT_LOCATION: [
            CallbackQueryHandler(batch_common_location_selection, pattern=f"^{config.CB_CREATE_BATCH_COMMON_LOCATION_PREFIX}.*")
        ],
        config.CREATE_BATCH_ENTER_REMARK: [
            CommandHandler("skip_remark_batch", batch_skip_common_remark),
            MessageHandler(filters.TEXT & ~filters.COMMAND, batch_common_remark_entry),
        ],
        config.CREATE_BATCH_TOGGLE_PRODUCTS: [
            CallbackQueryHandler(toggle_batch_product_selection, pattern=f"^{config.CB_CREATE_BATCH_PRODUCT_TOGGLE_PREFIX}.*"),
            CallbackQueryHandler(batch_products_selection_done, pattern=f"^{config.CB_CREATE_BATCH_PRODUCTS_DONE}$"),
        ],
        config.CREATE_BATCH_ENTER_PRICE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, batch_price_entry)
        ],
        config.CREATE_BATCH_CONFIRM_SUBMISSION: [
            CallbackQueryHandler(submit_batch_data, pattern=f"^{config.CB_CREATE_BATCH_SUBMIT_FINAL}$"),
            CallbackQueryHandler(common_handlers.cancel_conversation, pattern=f"^{config.CB_CREATE_BATCH_CANCEL_CONFIRM}$"),
        ],
        # --- Single States ---
        config.CREATE_SINGLE_SELECT_PRODUCT: [
            CallbackQueryHandler(single_entry_product_selection, pattern=f"^{config.CB_CREATE_SINGLE_PRODUCT_PREFIX}.*")
        ],
        config.CREATE_SINGLE_ENTER_PRICE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, single_entry_price_entry)
        ],
        config.CREATE_SINGLE_SELECT_LOCATION: [
            CallbackQueryHandler(single_entry_location_selection, pattern=f"^{config.CB_CREATE_SINGLE_LOCATION_PREFIX}.*")
        ],
        config.CREATE_SINGLE_ENTER_REMARK: [
            CommandHandler("skip_remark_single", single_skip_remark_entry),
            MessageHandler(filters.TEXT & ~filters.COMMAND, single_entry_remark_entry),
        ],
        config.CREATE_SINGLE_CONFIRM_SUBMISSION: [
            CallbackQueryHandler(submit_single_entry_data, pattern=f"^{config.CB_CREATE_SINGLE_SUBMIT_FINAL}$"),
            CallbackQueryHandler(common_handlers.cancel_conversation, pattern=f"^{config.CB_CREATE_SINGLE_CANCEL_CONFIRM}$"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", common_handlers.cancel_conversation),
        CallbackQueryHandler(common_handlers.cancel_conversation, pattern=f"^{config.CB_CREATE_CANCEL_ENTIRE}$"),
        # This universal fallback handles the post-action navigation buttons.
        CallbackQueryHandler(common_handlers.post_conversation_callback_handler),
    ],
    per_message=False,
)
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler,
)
from telegram.constants import ParseMode
import asyncio

import config
import gsheet_utils
import keyboards
import common_handlers

logger = logging.getLogger(__name__)

def _escape_markdown_v2_insights(text: str) -> str:
    """Escapes text for MarkdownV2."""
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f'\\{char}' if char in escape_chars else char for char in text)

async def _send_or_edit_insights(update: Update, text: str, reply_markup=None):
    """Helper to send or edit message for insights, using MarkdownV2."""
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    elif update.message:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

async def start_insights_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the insights selection menu."""
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("📊 Avg Price by Product", callback_data=f"{config.CB_INSIGHTS_PREFIX}by_product")],
        [InlineKeyboardButton("📍 Avg Price by Location", callback_data=f"{config.CB_INSIGHTS_PREFIX}by_location")],
        [InlineKeyboardButton("📈 Avg Price by Product & Location", callback_data=f"{config.CB_INSIGHTS_PREFIX}by_prod_loc")],
        [InlineKeyboardButton("❌ Cancel Insights", callback_data=f"{config.CB_INSIGHTS_PREFIX}cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "📈 *Price Insights Menu:*\nSelect the type of insight you want to see\\."
    await _send_or_edit_insights(update, text=text, reply_markup=reply_markup)
    return config.INSIGHTS_MENU_DISPLAYED

async def insights_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Handles insight selection, calculates, displays results, and shows navigation."""
    query = update.callback_query
    await query.answer()
    action = query.data.replace(config.CB_INSIGHTS_PREFIX, "")
    
    # Standard navigation keyboard for all end points
    nav_keyboard = keyboards.build_post_action_keyboard()

    if action == "cancel":
        await query.edit_message_text(
            text="Insights operation canceled.\n\nWhat would you like to do next?",
            reply_markup=nav_keyboard
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    await query.edit_message_text(text=_escape_markdown_v2_insights("🔄 Calculating insights, please wait..."))

    insights_data = await gsheet_utils.get_all_data_for_insights()

    if not insights_data:
        await query.edit_message_text(
            text="ℹ️ No data available for insights.\n\nWhat would you like to do next?",
            reply_markup=nav_keyboard
        )
        context.user_data.clear()
        return ConversationHandler.END

    result_text_parts = ["*Average Price Insights:*\n"]
    calculated_averages = {}

    if action == "by_product":
        calculated_averages = await gsheet_utils.calculate_average_prices(insights_data, 'product')
        for product, data in sorted(calculated_averages.items()):
            escaped_product = _escape_markdown_v2_insights(str(product))
            result_text_parts.append(f"  📦 *{escaped_product}:* `{data['average']:.2f}` \\(from {data['count']} entries\\)")
    
    elif action == "by_location":
        calculated_averages = await gsheet_utils.calculate_average_prices(insights_data, 'location')
        for location, data in sorted(calculated_averages.items()):
            escaped_location = _escape_markdown_v2_insights(str(location))
            result_text_parts.append(f"  📍 *{escaped_location}:* `{data['average']:.2f}` \\(from {data['count']} entries\\)")

    elif action == "by_prod_loc":
        calculated_averages = await gsheet_utils.calculate_average_prices(insights_data, ('product', 'location'))
        grouped_by_prod_display = {}
        for (product_key, location_key), data_val in sorted(calculated_averages.items()):
            if product_key not in grouped_by_prod_display:
                grouped_by_prod_display[product_key] = []
            escaped_location = _escape_markdown_v2_insights(str(location_key))
            grouped_by_prod_display[product_key].append(f"    📍 _{escaped_location}:_ `{data_val['average']:.2f}` \\({data_val['count']} entries\\)")
        
        for product_display, details_list in grouped_by_prod_display.items():
            escaped_product = _escape_markdown_v2_insights(str(product_display))
            result_text_parts.append(f"\n  📦 *{escaped_product}:*")
            result_text_parts.extend(details_list)
    else:
        await query.edit_message_text(text=_escape_markdown_v2_insights("⚠️ Invalid insight selection. Please try again."))
        return config.INSIGHTS_MENU_DISPLAYED

    final_result_text = "\n".join(result_text_parts)
    
    final_result_text += "\n\nWhat would you like to do next?"

    if len(final_result_text) > 4000:
        long_message = _escape_markdown_v2_insights(
            "📊 Insights generated successfully, but the result is too long to display directly.\n\n"
            "What would you like to do next?"
        )
        await query.edit_message_text(text=long_message, reply_markup=nav_keyboard)
    else:
        await query.edit_message_text(text=final_result_text, reply_markup=nav_keyboard)
    
    context.user_data.clear()
    return ConversationHandler.END

# --- Conversation Handler Definition ---
insights_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("insights", start_insights_menu),
        CallbackQueryHandler(start_insights_menu, pattern=f"^{config.CB_MAIN_MENU_PREFIX}insights$")
    ],
    states={
        config.INSIGHTS_MENU_DISPLAYED: [
            CallbackQueryHandler(insights_menu_callback, pattern=f"^{config.CB_INSIGHTS_PREFIX}.*")
        ],
    },
    fallbacks=[
        CommandHandler("cancel", common_handlers.cancel_conversation),
        CallbackQueryHandler(insights_menu_callback, pattern=f"^{config.CB_INSIGHTS_PREFIX}cancel$"),
        # This universal fallback handles the post-action navigation buttons.
        CallbackQueryHandler(common_handlers.post_conversation_callback_handler),
    ],
    per_message=False 
)
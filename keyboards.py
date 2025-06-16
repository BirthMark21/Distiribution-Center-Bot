from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config

# --- Universal Helper Function ---
def clean_and_format_for_display(raw_string: str) -> str:
    """
    Takes a raw internal string (like 'product_list' or 'beet_root')
    and makes it human-readable (like 'Product List' or 'Beet Root').
    """
    if not isinstance(raw_string, str):
        return ""
    return raw_string.replace('_', ' ').title()

# <<<--- NEW FUNCTION FOR NAVIGATION --- >>>
def build_post_action_keyboard() -> InlineKeyboardMarkup:
    """
    Builds a standard navigation keyboard to show after an action is completed.
    """
    keyboard = [
        [
            InlineKeyboardButton("➕ New Entry", callback_data=f"{config.CB_MAIN_MENU_PREFIX}new"),
            InlineKeyboardButton("📋 Main Menu", callback_data=f"{config.CB_MAIN_MENU_PREFIX}menu"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Generic Keyboard Builder ---
def build_keyboard(
    items: list[str],
    prefix: str = "",
    items_per_row: int = 1,
    suffix_from_item: bool = True,
    custom_callback_data: list[str] = None
) -> InlineKeyboardMarkup:
    """Builds an InlineKeyboardMarkup from a list of item strings."""
    keyboard_rows = []
    current_row = []

    if custom_callback_data and len(custom_callback_data) != len(items):
        raise ValueError("custom_callback_data must have the same length as items if provided.")

    for i, item_text in enumerate(items):
        if custom_callback_data:
            callback_val = custom_callback_data[i]
        elif suffix_from_item:
            callback_suffix = str(item_text).replace(" ", "_").lower()
            callback_val = f"{prefix}{callback_suffix}"
        else:
            callback_val = f"{prefix}{i}"

        current_row.append(InlineKeyboardButton(item_text, callback_data=callback_val))
        
        if len(current_row) == items_per_row or i == len(items) - 1:
            keyboard_rows.append(current_row)
            current_row = []
            
    return InlineKeyboardMarkup(keyboard_rows)

# --- Formatting Functions for Displaying Data ---
def _escape_markdown_v2_keyboards(text: str) -> str:
    """Escapes text for Telegram's MarkdownV2 parse mode (local copy)."""
    if not isinstance(text, str):
        text = str(text)
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f'\\{char}' if char in escape_chars else char for char in text)

def format_entry_details(entry_data_list: list, headers: list, title: str = "Entry Details") -> str:
    """Formats a list of entry data into a readable plain text string."""
    details = f"{title}:\n" if title else ""
    for i, header_raw_name in enumerate(headers):
        clean_header = clean_and_format_for_display(header_raw_name)
        value = entry_data_list[i] if i < len(entry_data_list) else "N/A"
        details += f"  {clean_header}: {value}\n"
    return details.strip()

def format_entry_details_markdown(entry_data_dict: dict, title: str = "Entry Details") -> str:
    """Formats a single entry (as a dictionary) into a readable MarkdownV2 string."""
    details_parts = []
    if title:
        details_parts.append(f"*{_escape_markdown_v2_keyboards(title)}:*")

    for header_key, value in entry_data_dict.items():
        display_header = clean_and_format_for_display(header_key)
        escaped_display_header = _escape_markdown_v2_keyboards(display_header)
        escaped_value = _escape_markdown_v2_keyboards(str(value))
        details_parts.append(f"  *{escaped_display_header}:* `{escaped_value}`")
        
    return "\n".join(details_parts)
import os
import logging
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

# --- Core Bot Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Google Sheets Configuration ---
GSHEET_CREDENTIALS_FILE = os.getenv("GOOGLE_SHEET_CREDENTIALS_FILE", "credentials.json")
GSHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME")

# --- Column Name Constants for Google Sheet ---
ID_FIELD = "id"
TIMESTAMP_FIELD = "timestamp"
EMAIL_FIELD = "email_address"
PRODUCT_FIELD = "product_list"
PRICE_FIELD = "buying_price"
LOCATION_FIELD = "location"
REMARK_FIELD = "production_remark"

DEFAULT_HEADERS = [
    ID_FIELD,
    TIMESTAMP_FIELD,
    EMAIL_FIELD,
    PRODUCT_FIELD,
    PRICE_FIELD,
    LOCATION_FIELD,
    REMARK_FIELD
]

# --- Predefined Lists for Bot Choices ---
PRODUCTS = [
    "Red Onion Grade A Restaurant quality", "Red Onion Grade B", "Red Onion Grade C",
    "Red Onion Elfora", "Potatoes", "Potatoes Restaurant Quality",
    "Tomatoes Grade B", "Tomatoes Grade A", "Carrot", "Chilly Green",
    "Chilly Green (Elfora)", "White Cabbage", "White Cabbage (Small)",
    "White Cabbage (Large)", "Avocado", "Strawberry", "Papaya", "Courgette",
    "Cucumber", "Garlic", "Ginger", "Pineapple", "Apple Mango", "Lemon",
    "Apple", "Valencia Orange", "Yerer Orange", "Avocado Shekaraw",
    "Beet root", "Corn", "Orange", "Green Beans", "Salad", "Broccoli"
]

LOCATIONS = [
    "Distribution Center 1 Gerji",
    "Distribution Center 2 Garment",
    "Distribution Center 3 02",
    "Distribution Center Lemi Kura/Alem Bank"
]

# --- Conversation State Management ---
_next_state_value_counter = 0

def _generate_unique_states(count: int) -> tuple:
    global _next_state_value_counter
    start_value = _next_state_value_counter
    _next_state_value_counter += count
    return tuple(range(start_value, start_value + count))

# --- Define Conversation States for Different Bot Modules ---

# Create New Entry States
(
    CREATE_CHOOSE_ENTRY_TYPE,
    # Batch States
    CREATE_BATCH_SELECT_LOCATION,
    CREATE_BATCH_ENTER_REMARK,
    CREATE_BATCH_TOGGLE_PRODUCTS,    # <<<-- NEW STATE -->>>
    CREATE_BATCH_ENTER_PRICE,
    CREATE_BATCH_CONFIRM_SUBMISSION,
    # Single States
    CREATE_SINGLE_SELECT_PRODUCT,
    CREATE_SINGLE_ENTER_PRICE,
    CREATE_SINGLE_SELECT_LOCATION,
    CREATE_SINGLE_ENTER_REMARK,
    CREATE_SINGLE_CONFIRM_SUBMISSION
) = _generate_unique_states(11) # Adjusted count

# Update Entry States
(
    UPDATE_ASK_ID,
    UPDATE_SELECT_FIELDS_TOGGLE,
    UPDATE_ENTER_MULTIPLE_VALUES,
    UPDATE_CONFIRM_MULTIPLE
) = _generate_unique_states(4)

# Delete Entry States
(
    DELETE_ASK_ID,
    DELETE_CONFIRM
) = _generate_unique_states(2)

# Read/View States
(
    VIEW_AWAITING_MENU_CHOICE,
    VIEW_AWAITING_ID_INPUT,
    VIEW_PAGINATING_ENTRIES
) = _generate_unique_states(3)

# Main Menu State
MENU_MAIN_DISPLAYED = _generate_unique_states(1)[0]

# Insights States
(
    INSIGHTS_MENU_DISPLAYED,
    INSIGHTS_AWAITING_PRODUCT,
    INSIGHTS_AWAITING_LOCATION
) = _generate_unique_states(3)


# --- Callback Data Prefixes and Exact Strings ---

# Main Menu Navigation
CB_MAIN_MENU_PREFIX = "menu_nav_"
CB_OPEN_MENU_FROM_START = "menu_open_from_start"

# Create Operation Callbacks
CB_CREATE_CHOOSE_TYPE_SINGLE = "create_choose_single"
CB_CREATE_CHOOSE_TYPE_BATCH = "create_choose_batch"
CB_CREATE_CANCEL_ENTIRE = "create_op_cancel_all"

# Batch specific callbacks
CB_CREATE_BATCH_COMMON_LOCATION_PREFIX = "create_b_loc_"
CB_CREATE_BATCH_PRODUCT_TOGGLE_PREFIX = "create_b_prod_toggle_" # <<<-- NEW -->>>
CB_CREATE_BATCH_PRODUCTS_DONE = "create_b_prod_done"          # <<<-- NEW -->>>
CB_CREATE_BATCH_SUBMIT_FINAL = "create_b_submit_final"
CB_CREATE_BATCH_CANCEL_CONFIRM = "create_b_cancel_conf"

# Single entry specific callbacks
CB_CREATE_SINGLE_PRODUCT_PREFIX = "create_s_prod_"
CB_CREATE_SINGLE_LOCATION_PREFIX = "create_s_loc_"
CB_CREATE_SINGLE_SUBMIT_FINAL = "create_s_submit_final"
CB_CREATE_SINGLE_CANCEL_CONFIRM = "create_s_cancel_conf"

# Update Operation Callbacks
CB_UPDATE_FIELD_TOGGLE_PREFIX = "update_field_"
CB_UPDATE_PROCEED_WITH_SELECTION = "update_proceed_sel"
CB_UPDATE_CANCEL_FIELD_SELECTION = "update_cancel_sel"
CB_UPDATE_NEWVAL_PRODUCT_PREFIX = "update_val_prod_"
CB_UPDATE_NEWVAL_LOCATION_PREFIX = "update_val_loc_"
CB_UPDATE_EXECUTE_CONFIRMED = "update_execute_now"
CB_UPDATE_CANCEL_FINAL_CONFIRM = "update_cancel_final"

# Delete Operation Callbacks
CB_DELETE_CONFIRM_YES = "delete_do_yes"
CB_DELETE_CONFIRM_NO = "delete_do_no"

# View/Read Operation Callbacks
CB_VIEW_LAST_N_PREFIX = "view_last_"
CB_VIEW_BY_ID_PROMPT_ACTION = "view_by_id_ask"
CB_VIEW_CANCEL_ACTION = "view_op_cancel"
CB_VIEW_BACK_TO_MENU_ACTION = "view_back_to_main_menu"

# Insights Operation Callbacks
CB_INSIGHTS_PREFIX = "insights_action_"
CB_INSIGHTS_BACK_TO_MAIN = "insights_back_main"
CB_INSIGHTS_CANCEL = "insights_op_cancel"

# --- Miscellaneous Bot Settings ---
DEFAULT_ENTRIES_PER_PAGE_VIEW = 5

# --- Logging Configuration ---
_config_logger = logging.getLogger(__name__ + ".config_loader")

if not BOT_TOKEN:
    _config_logger.critical("CRITICAL FAILURE: BOT_TOKEN is not set.")
if not GSHEET_CREDENTIALS_FILE:
    _config_logger.warning(f"WARNING: GOOGLE_SHEET_CREDENTIALS_FILE not set. Defaulting to 'credentials.json'. Path: {os.path.abspath(GSHEET_CREDENTIALS_FILE)}")
if not GSHEET_NAME:
    _config_logger.error("ERROR: GOOGLE_SHEET_NAME is not configured.")
if not WORKSHEET_NAME:
    _config_logger.warning("WARNING: WORKSHEET_NAME is not configured. Using first sheet.")

_config_logger.info(f"Configuration loaded. Next state value: {_next_state_value_counter}. GSheet: '{GSHEET_NAME}', Worksheet: '{WORKSHEET_NAME}'.")
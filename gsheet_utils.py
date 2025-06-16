# gsheet_utils.py

import logging
import os
import asyncio # For wrapping blocking gspread calls
import re # <<< NEW: Added for text cleaning

import gspread
from oauth2client.service_account import ServiceAccountCredentials

import config

logger = logging.getLogger(__name__)

worksheet: gspread.Worksheet | None = None
HEADERS: list[str] = []
GSHEET_CONNECTED: bool = False

# <<< NEW HELPER FUNCTION START >>>
def _clean_and_capitalize_text(text: str) -> str:
    """
    Cleans a string by removing non-alphanumeric characters (except spaces)
    and then capitalizes the first letter of each word (title case).
    Handles non-string inputs gracefully.
    """
    if not isinstance(text, str):
        text = str(text)

    # 1. Remove any character that is NOT a letter, a number, or a whitespace character.
    # This gets rid of underscores, slashes, parentheses, etc.
    cleaned_text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    
    # 2. Capitalize the first letter of each word.
    # e.g., "red onion grade a" -> "Red Onion Grade A"
    capitalized_text = cleaned_text.title()
    
    # 3. Remove any potential double spaces that might result from cleaning
    return ' '.join(capitalized_text.split())
# <<< NEW HELPER FUNCTION END >>>


async def connect_and_initialize_sheet() -> tuple[bool, list[str], gspread.Worksheet | None]:
    global worksheet, HEADERS, GSHEET_CONNECTED
    try:
        # Use asyncio.to_thread for Python 3.9+
        GSHEET_CONNECTED, HEADERS, worksheet = await asyncio.to_thread(_connect_to_gsheet_sync)
    except Exception as e:
        logger.critical(f"Critical error during threaded Google Sheet connection: {e}", exc_info=True)
        GSHEET_CONNECTED = False
        HEADERS = []
        worksheet = None
    return GSHEET_CONNECTED, HEADERS, worksheet

def _connect_to_gsheet_sync() -> tuple[bool, list[str], gspread.Worksheet | None]:
    local_worksheet: gspread.Worksheet | None = None
    local_headers: list[str] = []
    is_connected_successfully: bool = False

    credentials_path = config.GSHEET_CREDENTIALS_FILE
    sheet_name = config.GSHEET_NAME
    worksheet_name_config = config.WORKSHEET_NAME

    if not credentials_path or not os.path.exists(credentials_path):
        logger.error(
            f"Google Sheets credentials JSON file not found at configured path: '{credentials_path}'. "
            f"Absolute path checked: '{os.path.abspath(credentials_path)}'"
        )
        return False, [], None

    if not sheet_name:
        logger.error("GSHEET_NAME is not configured. Cannot open spreadsheet.")
        return False, [], None

    try:
        logger.info(f"Attempting to authenticate with Google Sheets using: {credentials_path}")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
        client = gspread.authorize(creds)
        logger.info("Successfully authenticated with Google API.")

        logger.info(f"Attempting to open Google Spreadsheet by name: '{sheet_name}'")
        spreadsheet = client.open(sheet_name)
        
        if worksheet_name_config:
            logger.info(f"Attempting to open worksheet by name: '{worksheet_name_config}' in spreadsheet '{sheet_name}'")
            local_worksheet = spreadsheet.worksheet(worksheet_name_config)
        else:
            logger.warning(f"WORKSHEET_NAME not configured. Using the first available sheet in '{sheet_name}'.")
            local_worksheet = spreadsheet.sheet1
        
        logger.info(f"Successfully opened worksheet: '{local_worksheet.title}'")

        all_sheet_values = local_worksheet.get_all_values()
        
        if not all_sheet_values or not all_sheet_values[0]:
            logger.warning(f"Worksheet '{local_worksheet.title}' is empty or first row is blank. Attempting to set default headers.")
            headers_to_set = config.DEFAULT_HEADERS
            if not headers_to_set:
                 logger.error("config.DEFAULT_HEADERS is empty. Cannot initialize an empty sheet without default headers.")
                 return False, [], local_worksheet
            
            local_worksheet.update('A1', [headers_to_set])
            local_headers = headers_to_set
            logger.info(f"Successfully wrote default headers to worksheet: {local_headers}")
        else:
            local_headers = all_sheet_values[0]
            logger.info(f"Successfully read existing headers from worksheet: {local_headers}")

        required_headers_from_config = config.DEFAULT_HEADERS
        missing_headers = [h for h in required_headers_from_config if h not in local_headers]
        if missing_headers:
            logger.error(
                f"One or more configured default headers are MISSING from the sheet's actual headers. "
                f"Missing: {missing_headers}. "
                f"Sheet headers found: {local_headers}. "
                f"Expected based on config: {config.DEFAULT_HEADERS}. "
                "Bot operations relying on these missing fields will likely fail. "
            )
        
        is_connected_successfully = True

    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"Spreadsheet NOT FOUND: '{sheet_name}'. Please check the name and ensure the service account has access.")
        is_connected_successfully = False
    except gspread.exceptions.WorksheetNotFound:
        logger.error(f"Worksheet NOT FOUND: '{worksheet_name_config}' in spreadsheet '{sheet_name}'. Please check the worksheet name.")
        is_connected_successfully = False
    except FileNotFoundError:
        logger.error(f"Credentials file not found at path: {credentials_path} (re-check).")
        is_connected_successfully = False
    except Exception as e:
        logger.critical(f"An unexpected error occurred during Google Sheet connection or setup: {e.__class__.__name__}: {e}", exc_info=True)
        is_connected_successfully = False
    
    return is_connected_successfully, local_headers, local_worksheet

def find_row_by_id(entry_id_to_find: str) -> tuple[int | None, list | None]:
    if not GSHEET_CONNECTED or not worksheet or not HEADERS:
        logger.error("GSheet not connected or not initialized, cannot find row by ID.")
        return None, None
    if not entry_id_to_find:
        logger.warning("find_row_by_id called with an empty entry_id_to_find.")
        return None, None
    try:
        id_column_index = HEADERS.index(config.ID_FIELD) + 1
    except ValueError: 
        logger.error(f"Critical: ID field '{config.ID_FIELD}' not found in sheet headers: {HEADERS}. Cannot search by ID.")
        return None, None
    try:
        logger.debug(f"Searching for entry_id '{entry_id_to_find}' in column {id_column_index} ('{config.ID_FIELD}').")
        cell = worksheet.find(entry_id_to_find, in_column=id_column_index)
        if cell:
            logger.info(f"Entry ID '{entry_id_to_find}' found at row {cell.row}, column {cell.col}.")
            row_values = worksheet.row_values(cell.row)
            return cell.row, row_values
        else:
            logger.info(f"Entry ID '{entry_id_to_find}' not found in column '{config.ID_FIELD}'.")
            return None, None
    except gspread.exceptions.CellNotFound:
        logger.info(f"Cell with ID '{entry_id_to_find}' explicitly not found by gspread.")
        return None, None
    except Exception as e:
        logger.error(f"Error while finding row by ID '{entry_id_to_find}': {e}", exc_info=True)
        return None, None

def append_rows_to_sheet(rows_data: list[list]) -> bool:
    if not GSHEET_CONNECTED or not worksheet:
        logger.error("GSheet not connected, cannot append rows.")
        return False
    if not rows_data:
        logger.warning("append_rows_to_sheet called with empty rows_data list.")
        return True 
    try:
        logger.info(f"Appending {len(rows_data)} row(s) to sheet '{worksheet.title}'.")
        worksheet.append_rows(rows_data, value_input_option='USER_ENTERED')
        logger.info(f"Successfully appended {len(rows_data)} row(s).")
        return True
    except Exception as e:
        logger.error(f"Error appending rows to sheet: {e}", exc_info=True)
        return False

def update_cell_in_sheet(row_number: int, col_number: int, new_value: any) -> bool:
    if not GSHEET_CONNECTED or not worksheet:
        logger.error("GSheet not connected, cannot update cell.")
        return False
    try:
        logger.info(f"Updating cell at (Row: {row_number}, Col: {col_number}) in sheet '{worksheet.title}' with value: '{str(new_value)[:50]}...'")
        worksheet.update_cell(row_number, col_number, new_value)
        logger.info(f"Successfully updated cell ({row_number},{col_number}).")
        return True
    except Exception as e:
        logger.error(f"Error updating cell ({row_number},{col_number}): {e}", exc_info=True)
        return False

def delete_row_from_sheet(row_number: int) -> bool:
    if not GSHEET_CONNECTED or not worksheet:
        logger.error("GSheet not connected, cannot delete row.")
        return False
    try:
        logger.info(f"Deleting row {row_number} from sheet '{worksheet.title}'.")
        worksheet.delete_rows(row_number)
        logger.info(f"Successfully deleted row {row_number}.")
        return True
    except Exception as e:
        logger.error(f"Error deleting row {row_number}: {e}", exc_info=True)
        return False

# --- Data Retrieval and Processing for Insights ---

async def get_all_data_for_insights() -> list[dict]:
    if not GSHEET_CONNECTED or not worksheet or not HEADERS:
        logger.error("GSheet not connected or not initialized, cannot get data for insights.")
        return []
    required_insight_headers = [config.PRODUCT_FIELD, config.PRICE_FIELD, config.LOCATION_FIELD]
    if not all(h in HEADERS for h in required_insight_headers):
        logger.error(f"Required headers for insights ({required_insight_headers}) are missing from sheet headers: {HEADERS}.")
        return []
    logger.info(f"Fetching all records from '{worksheet.title}' for insights generation...")
    try:
        all_records_from_sheet = await asyncio.to_thread(worksheet.get_all_records) 
        logger.info(f"Retrieved {len(all_records_from_sheet)} total records from sheet for insights.")
    except Exception as e:
        logger.error(f"Error calling worksheet.get_all_records(): {e}", exc_info=True)
        return []

    processed_insights_data = []
    for record_dict in all_records_from_sheet:
        try:
            product = record_dict.get(config.PRODUCT_FIELD)
            location = record_dict.get(config.LOCATION_FIELD)
            price_raw = record_dict.get(config.PRICE_FIELD)
            if not product or not location or price_raw is None:
                continue
            try:
                price_str_cleaned = str(price_raw).strip().replace(',', '')
                price_float = float(price_str_cleaned)
                if price_float <= 0:
                    continue
            except ValueError:
                continue
            
            # <<< MODIFIED/NEW LINES START HERE >>>
            # Apply our new cleaning function to product and location names
            cleaned_product_name = _clean_and_capitalize_text(product)
            cleaned_location_name = _clean_and_capitalize_text(location)

            processed_insights_data.append({
                'product': cleaned_product_name,
                'location': cleaned_location_name,
                'price': price_float
            })
            # <<< MODIFIED/NEW LINES END HERE >>>

        except Exception as e:
            logger.warning(f"Error processing a single record for insights: {e}. Record: {record_dict}", exc_info=False)
            continue
    logger.info(f"Successfully processed {len(processed_insights_data)} valid records for insights analysis.")
    return processed_insights_data

async def calculate_average_prices(
    insights_data: list[dict],
    group_by_key: str | tuple[str, ...]
) -> dict:
    if not insights_data:
        logger.warning("calculate_average_prices called with empty insights_data.")
        return {}
    averages_accumulator = {}
    for item_data in insights_data:
        current_key_tuple = []
        if isinstance(group_by_key, tuple):
            for key_part in group_by_key:
                current_key_tuple.append(str(item_data.get(key_part, "N/A")).strip())
            composite_key = tuple(current_key_tuple)
        else: 
            composite_key = str(item_data.get(group_by_key, "N/A")).strip()
        price_val = item_data.get('price')
        if price_val is None:
            continue
        if composite_key not in averages_accumulator:
            averages_accumulator[composite_key] = {'total_price': 0.0, 'count': 0}
        averages_accumulator[composite_key]['total_price'] += price_val
        averages_accumulator[composite_key]['count'] += 1
    final_averages = {}
    for key, data in averages_accumulator.items():
        if data['count'] > 0:
            avg = data['total_price'] / data['count']
            final_averages[key] = {
                'total_price': data['total_price'],
                'count': data['count'],
                'average': round(avg, 2)
            }
    logger.info(f"Calculated averages for {len(final_averages)} groups based on key(s): {group_by_key}")
    return final_averages

async def run_sync_gsheet_func(func, *args, **kwargs):
    if not GSHEET_CONNECTED:
        logger.error(f"GSheet not connected. Cannot execute gspread function: {func.__name__}")
        if "find" in func.__name__: return None, None
        if "get" in func.__name__: return []
        return False
    try:
        return await asyncio.to_thread(func, *args, **kwargs) 
    except Exception as e:
        logger.error(f"Error running sync gspread function {func.__name__} in thread: {e}", exc_info=True)
        if "find" in func.__name__: return None, None
        if "get" in func.__name__: return []
        return False
# Distribution Center Bot

A sophisticated Telegram bot designed to streamline data entry and analysis for a distribution center. This bot interacts with a Google Sheet, allowing users to perform CRUD (Create, Read, Update, Delete) operations and gain insights into product data through a user-friendly inline menu interface.

## Functional Requirements & Features

This bot provides a complete solution for managing product benchmarking data directly from Telegram.

### 1. Data Entry (`/new`)
- **Single Entry Mode:** A guided, step-by-step process to register a single product, including its name, buying price, location, and remarks.
- **Batch Entry Mode:** A highly efficient workflow for registering multiple products at once.
  - Users first select a common location and provide optional common remarks for the entire batch.
  - A dynamic checklist allows for the selection of multiple products in one step.
  - The bot then sequentially asks for the buying price of each selected product.
  - The entire batch is submitted to the Google Sheet in a single, efficient operation.

### 2. View Data (`/view`)
- **View by ID:** Retrieve the complete details of a specific entry by providing its unique ID.
- **View Last Entries:** A paginated view to browse the most recently added entries, making it easy to review recent work without leaving Telegram.

### 3. Update Entries (`/update`)
- **Targeted Updates:** Users can update an existing entry by providing its ID.
- **Field Selection Checklist:** A dynamic checklist shows the current values and allows the user to select one or more fields (Product, Price, Location, Remark) to modify.
- **Guided Value Entry:** The bot prompts the user for new values only for the fields they selected to update.
- **Confirmation Summary:** Before applying changes, the bot displays a clear summary of the proposed updates for final user confirmation.

### 4. Delete Entries (`/delete`)
- **Safe Deletion:** Users can delete an entry by providing its ID.
- **Confirmation Step:** To prevent accidental data loss, the bot displays the full entry details and requires a final confirmation before deleting the row from the Google Sheet.

### 5. Price Insights (`/insights`)
- **Data-Driven Analysis:** Generate on-the-fly reports to analyze pricing data.
- **Multiple Views:**
  - Average Price by Product
  - Average Price by Location
  - Average Price by both Product & Location (grouped view)
- **Data Cleaning:** Raw product and location names from the sheet are automatically cleaned and standardized (e.g., `red_onion_(elfora)` becomes `Red Onion Elfora`) for professional and accurate reports.

### 6. User Experience & Navigation
- **Menu-Driven Interface:** All operations are accessible through a clean, inline button menu (`/menu`).
- **Seamless Workflow:** After completing any action (creating, updating, deleting, etc.), a navigation menu with "➕ New Entry" and "📋 Main Menu" buttons appears, allowing users to fluidly move to the next task without re-typing commands.
- **Smart Commands:** The bot responds to both `/start` and the text message `start` to display the main menu, making it easy for new users to begin.
- **Robust Error Handling:** The bot is designed to handle invalid inputs gracefully and provides clear feedback to the user.

## Tech Stack
- **Language:** Python
- **Framework:** [python-telegram-bot](https://python-telegram-bot.org/)
- **Database:** [Google Sheets](https://www.google.com/sheets/about/)
- **API Wrappers:** `gspread`, `oauth2client`

## Setup and Installation

Follow these steps to set up and run the bot locally or prepare it for deployment.

### 1. Prerequisites
- Python 3.10 or higher
- A Telegram Bot Token from [BotFather](https://t.me/botfather)
- A Google Cloud Platform (GCP) project with the Google Sheets API and Google Drive API enabled.
- A Google Service Account with credentials (`credentials.json`) that has editor access to your target Google Sheet.

### 2. Clone the Repository
```bash
git clone https://github.com/BirthMark21/Distiribution-Center-Bot.git
cd DC_Bot
```

### 3. Create a Virtual Environment
It's highly recommended to use a virtual environment to manage dependencies.
```bash
# Create the virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Create a file named `.env` in the root of the project directory. This file will hold your secret keys and configuration. **This file is included in `.gitignore` and will not be committed to GitHub.**

```env
# --- Telegram Bot ---
BOT_TOKEN="123456:ABC-DEF1234567890"

# --- Google Sheets Config ---
GOOGLE_SHEET_NAME="Your Google Sheet Name"
WORKSHEET_NAME="Sheet1" # The name of the specific worksheet/tab
GSHEET_CREDENTIALS_FILE="credentials.json"
```

### 6. Add Google Credentials
Place your `credentials.json` file (downloaded from your Google Service Account) in the root of the project directory. **This file is also ignored by Git.**

### 7. Run the Bot
Once the setup is complete, you can start the bot with the following command:
```bash
python bot.py
```

## Deployment

This bot is ready to be deployed on platforms like [Render](https://render.com) or [Heroku](https://www.heroku.com/).

When deploying:
1.  Push your code to a GitHub repository (your `.env` and `credentials.json` files will be ignored).
2.  On the deployment platform, set up a **Background Worker** or equivalent service.
3.  Set the **Start Command** to `python bot.py`.
4.  Add the environment variables from your `.env` file to the platform's secret/environment variable manager.
5.  Add the contents of your `credentials.json` file as a "Secret File" on the platform.

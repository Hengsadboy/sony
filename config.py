import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Settings
# Using the token provided in the prompt
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8542512749:AAE5RzDNMCaqLTBSiccEe9VgZm1d3ecgiio")

# The private Telegram Admin Channel ID or Group ID where notification alerts are sent.
# Replace with your actual admin channel/group chat ID (typically negative numbers like -100xxxxxxxxx)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "-1002302341254")

# Admin Web Credentials
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Sonytradingfx@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Heng@1188")

# Database & Upload Configuration (Platform Independent)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'trading.db')}")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "static", "uploads"))

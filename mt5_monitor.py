import time
import logging
import threading
import os
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "mt5_monitor.log")),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MT5Monitor")

# Try importing MetaTrader5
MT5_AVAILABLE = False
try:
    if os.name == 'nt':  # MT5 python library only runs on Windows
        import MetaTrader5 as mt5
        MT5_AVAILABLE = True
        logger.info("MetaTrader5 library loaded successfully.")
    else:
        logger.warning("MetaTrader5 library is only supported on Windows. Running in Mock/Simulated mode.")
except ImportError:
    logger.warning("MetaTrader5 library not installed. Running in Mock/Simulated mode.")

# Import database session
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from database import SessionLocal, TradingAccount, User
import requests
from config import TELEGRAM_BOT_TOKEN

# We can send Telegram notifications directly via Bot API to notify users immediately
def send_telegram_alert(chat_id, text):
    from database import get_setting
    token = get_setting("telegram_bot_token", TELEGRAM_BOT_TOKEN)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Error sending Telegram alert: {e}")

# Cache of last known balances to detect changes
balance_cache = {}

def parse_credentials(login_str, account_number):
    """
    Parses login string to extract login ID and server name.
    If login_str starts with a non-digit (like 'Exness-MT5Rea128'), returns (int(account_number), login_str).
    If it has both login and server (e.g. '123456@Exness-MT5Rea128'), splits them.
    """
    if not login_str:
        try:
            return int(account_number), None
        except:
            return None, None
            
    login_str = str(login_str).strip()
    if login_str.isdigit():
        return int(login_str), None
        
    import re
    match = re.match(r'^(\d+)[\s@,]+(.+)$', login_str)
    if match:
        return int(match.group(1)), match.group(2).strip()
        
    try:
        return int(account_number), login_str
    except (ValueError, TypeError):
        return None, login_str

def monitor_account(acc_id):
    """
    Monitors a single MT5 account in a loop.
    Checks balance every 1 second.
    """
    logger.info(f"Started monitoring thread for Account ID {acc_id}")
    
    while True:
        db = SessionLocal()
        try:
            acc = db.query(TradingAccount).filter(
                TradingAccount.id == acc_id, 
                TradingAccount.status == "Approved",
                TradingAccount.mt5_active == True
            ).first()
            if not acc or not acc.login or not acc.password or not acc.mt5_active:
                logger.info(f"Account {acc_id} is no longer active, approved, or MT5 monitoring deactivated. Stopping thread.")
                break
                
            login_str = acc.login
            password = acc.password
            account_number = acc.account_number
            user_telegram_id = acc.user_telegram_id
            
            login_id, server = parse_credentials(login_str, account_number)
            if not login_id:
                # If cannot parse integer login ID, fallback to account_number if integer
                try:
                    login_id = int(account_number)
                except (ValueError, TypeError):
                    logger.error(f"Account {acc_id}: Cannot parse integer Login ID from login '{login_str}' or account_number '{account_number}'")
                    time.sleep(5)
                    continue
                    
            if not server:
                server = "MetaQuotes-Demo"  # Default server
                
            new_balance = None
            
            if MT5_AVAILABLE:
                # MT5 connection logic
                authorized = mt5.initialize(login=login_id, password=password, server=server)
                if authorized:
                    if acc.mt5_status != "Online":
                        acc.mt5_status = "Online"
                        db.commit()
                    # Retrieve ONLY the balance as requested
                    acc_info = mt5.account_info()
                    if acc_info is not None:
                        new_balance = float(acc_info.balance)
                    else:
                        logger.error(f"Account {acc_id}: Failed to get account info. Error code: {mt5.last_error()}")
                    mt5.shutdown()
                else:
                    if acc.mt5_status != "Offline":
                        acc.mt5_status = "Offline"
                        db.commit()
                    logger.error(f"Account {acc_id}: Failed to initialize/authorize with login {login_id} on server {server}. Error code: {mt5.last_error()}")
            else:
                # Mock Mode (runs on Linux/VPS without MT5 installed)
                if acc.mt5_status != "Online":
                    acc.mt5_status = "Online"
                    db.commit()
                new_balance = float(acc.balance)
                
            if new_balance is not None:
                status_str = "Online" if (MT5_AVAILABLE or acc.mt5_status == "Online") else "Offline"
                logger.info(f"[Active MT5 Check] Account #{account_number} | Server: {server} | Status: {status_str} | Balance: ${new_balance:,.2f}")
                
                # Check cache
                last_balance = balance_cache.get(acc_id)
                if last_balance is None:
                    # Initialize cache
                    balance_cache[acc_id] = new_balance
                    # If DB has a different balance, sync it without alert
                    if abs(acc.balance - new_balance) > 0.001:
                        acc.balance = new_balance
                        db.commit()
                elif abs(last_balance - new_balance) > 0.001:
                    logger.info(f"Account {acc_id} balance changed: ${last_balance:.2f} -> ${new_balance:.2f}")
                    
                    # Update cache
                    balance_cache[acc_id] = new_balance
                    
                    # Update database
                    acc.balance = new_balance
                    db.commit()
                    
                    # Fetch user language
                    user = db.query(User).filter(User.telegram_id == user_telegram_id).first()
                    lang = user.language if (user and user.language) else "en"
                    
                    # Notify user immediately via Telegram
                    if lang == "km":
                        alert_text = (
                            f"🔔 *ដំណឹងបច្ចុប្បន្នភាពសមតុល្យ*\n\n"
                            f"សមតុល្យគណនីជួញដូរ *#{account_number}* របស់អ្នកបានផ្លាស់ប្តូរ៖\n"
                            f"• សមតុល្យថ្មី: *${new_balance:,.2f}*"
                        )
                    else:
                        alert_text = (
                            f"🔔 *Balance Update Alert*\n\n"
                            f"Your trading account *#{account_number}* balance has changed:\n"
                            f"• New Balance: *${new_balance:,.2f}*"
                        )
                    send_telegram_alert(user_telegram_id, alert_text)
                    
        except Exception as e:
            logger.error(f"Exception in monitoring loop for Account {acc_id}: {e}")
        finally:
            db.close()
            
        time.sleep(1)  # Check every 1 second

def main_monitor_loop():
    logger.info("Starting MetaTrader 5 Balance Monitor coordinator...")
    active_threads = {}  # acc_id -> thread object
    
    while True:
        db = SessionLocal()
        try:
            # Find all active approved accounts with MT5 monitoring enabled
            accounts = db.query(TradingAccount).filter(
                TradingAccount.status == "Approved", 
                TradingAccount.mt5_active == True
            ).all()
            active_ids = {acc.id for acc in accounts}
            
            # Start threads for new accounts
            for acc in accounts:
                if acc.id not in active_threads or not active_threads[acc.id].is_alive():
                    t = threading.Thread(target=monitor_account, args=(acc.id,), daemon=True)
                    t.start()
                    active_threads[acc.id] = t
                    
            # Clean up threads list for removed accounts
            dead_ids = [acc_id for acc_id in active_threads if acc_id not in active_ids]
            for acc_id in dead_ids:
                del active_threads[acc_id]
                if acc_id in balance_cache:
                    del balance_cache[acc_id]
                    
        except Exception as e:
            logger.error(f"Error in main monitor coordinator: {e}")
        finally:
            db.close()
            
        time.sleep(5)  # Coordinate threads every 5 seconds

if __name__ == "__main__":
    main_monitor_loop()

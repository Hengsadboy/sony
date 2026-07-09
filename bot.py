import os
import logging
import io
import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from database import init_db, SessionLocal, User, TradingAccount, Transaction
from config import TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, UPLOAD_DIR


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Conversation States
(
    # Registration States
    REG_CHOOSE_TYPE,
    REG_GET_NAME,
    REG_GET_EMAIL,
    
    # Deposit States
    DEP_CHOOSE_ACCOUNT,
    DEP_GET_AMOUNT,
    DEP_GET_RECEIPT,
    
    # Withdrawal States
    WITHDRAW_CHOOSE_ACCOUNT,
    WITHDRAW_GET_AMOUNT,
    WITHDRAW_GET_BANK_NAME,
    WITHDRAW_GET_ACC_NUM,
    WITHDRAW_GET_ACC_NAME,
    
    # Forgot Password States
    FORGOT_GET_EMAIL,
    FORGOT_GET_ACC_NUM,
) = range(13)


# Helper function to send notification to the Admin Channel
async def send_admin_notification(application: Application, text: str):
    try:
        await application.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=text,
            parse_mode="Markdown"
        )
        logger.info("Admin notification sent successfully.")
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")


# Persistent Bottom Menu Markup
from telegram import ReplyKeyboardMarkup

reply_keyboard = [
    ["📝 Register Account", "ℹ️ My Account Info"],
    ["💰 Deposit", "💸 Withdraw"],
    ["🔑 Forgot Password"]
]
persistent_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)


# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 Welcome *{user.first_name}* to our *Manual Forex Broker*!\n\n"
        "Here you can register accounts, deposit, withdraw, and check your status completely manually. "
        "Our admin team will process your requests quickly.\n\n"
        "Please choose an option from the menu under the chat:"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=persistent_markup, parse_mode="Markdown")
    else:
        await update.callback_query.message.reply_text(welcome_text, reply_markup=persistent_markup, parse_mode="Markdown")
        await update.callback_query.answer()



# --- MY ACCOUNT INFO ---
async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        telegram_id = query.from_user.id
        message_target = query.message
    else:
        telegram_id = update.effective_user.id
        message_target = update.message
        
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not db_user:
            await message_target.reply_text(
                "❌ You are not registered yet. Please click *📝 Register Account* to start.",
                reply_markup=persistent_markup,
                parse_mode="Markdown"
            )
            return
        
        info_text = (
            f"👤 *Profile Details*\n"
            f"Name: {db_user.name}\n"
            f"Email: {db_user.email}\n"
            f"Status: {db_user.status}\n\n"
            f"💳 *Trading Accounts:*\n"
        )
        
        accounts = db.query(TradingAccount).filter(TradingAccount.user_telegram_id == telegram_id).all()
        if not accounts:
            info_text += "_No trading accounts created yet._\n"
        else:
            for i, acc in enumerate(accounts, 1):
                acc_num = acc.account_number if acc.account_number else "Pending Admin Assign"
                login = acc.login if acc.login else "Pending"
                password = acc.password if acc.password else "Pending"
                info_text += (
                    f"*{i}. {acc.account_type} Account*\n"
                    f"  • ID: {acc.id}\n"
                    f"  • Account Number: `{acc_num}`\n"
                    f"  • Login Details: `{login}`\n"
                    f"  • Password: `{password}`\n"
                    f"  • Balance: `${acc.balance:,.2f}`\n"
                    f"  • Status: {acc.status}\n\n"
                )
        
        await message_target.reply_text(info_text, reply_markup=persistent_markup, parse_mode="Markdown")
    finally:
        db.close()


# --- REGISTRATION FLOW ---
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        telegram_id = query.from_user.id
        message_target = query.message
    else:
        telegram_id = update.effective_user.id
        message_target = update.message

    db = SessionLocal()
    try:
        # Enforce 1 account per Telegram profile rule
        existing_acc = db.query(TradingAccount).filter(TradingAccount.user_telegram_id == telegram_id).first()
        if existing_acc:
            await message_target.reply_text(
                "❌ *Registration Rejected*\n\n"
                "You already have a trading account. You can only register *one trading account* per Telegram profile.",
                reply_markup=persistent_markup,
                parse_mode="Markdown"
            )
            return ConversationHandler.END

        # Check if user already exists
        db_user = db.query(User).filter(User.telegram_id == telegram_id).first()
        context.user_data["reg_user_exists"] = db_user is not None
    finally:
        db.close()

    keyboard = [
        [
            InlineKeyboardButton("🪙 Cent Account", callback_data="type_Cent"),
            InlineKeyboardButton("💵 USD Account", callback_data="type_USD"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_conv")],
    ]
    await message_target.reply_text(
        "📝 *Choose your trading account type:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return REG_CHOOSE_TYPE

async def register_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acc_type = query.data.split("_")[1]
    context.user_data["reg_acc_type"] = acc_type
    
    if context.user_data.get("reg_user_exists"):
        # If user profile already exists, skip name and email collection, directly create the account!
        telegram_id = query.from_user.id
        db = SessionLocal()
        try:
            db_user = db.query(User).filter(User.telegram_id == telegram_id).first()
            new_acc = TradingAccount(
                user_telegram_id=telegram_id,
                account_type=acc_type,
                status="Pending"
            )
            db.add(new_acc)
            db.commit()
            
            # Send notification
            alert = (
                f"🚨 *NEW TRADING ACCOUNT REQUEST*\n"
                f"👤 Name: {db_user.name}\n"
                f"📧 Email: {db_user.email}\n"
                f"💳 Telegram ID: `{telegram_id}`\n"
                f"💰 Account Type: *{acc_type}*\n"
                f"🔢 DB Account ID: `{new_acc.id}`\n"
                f"Please open the Web Admin Panel to assign MT4/MT5 details."
            )
            await send_admin_notification(context.application, alert)
            
            # Notify specific group ID
            try:
                await context.application.bot.send_message(
                    chat_id="-5536620816",
                    text=alert,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error sending account request notification to group -5536620816: {e}")
            
            await query.message.reply_text(
                "✅ Your request for a new trading account has been submitted!\n"
                "Our admin will assign your login credentials shortly. You will be notified here.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="btn_back")]]),
                parse_mode="Markdown"
            )
        finally:
            db.close()
        return ConversationHandler.END

    await query.message.reply_text("Please enter your *Full Name*:", parse_mode="Markdown")
    return REG_GET_NAME

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["reg_name"] = update.message.text
    await update.message.reply_text("Please enter your *Email Address*:", parse_mode="Markdown")
    return REG_GET_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text
    telegram_id = update.effective_user.id
    name = context.user_data["reg_name"]
    acc_type = context.user_data["reg_acc_type"]
    
    db = SessionLocal()
    try:
        # Check if email is already taken
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            await update.message.reply_text("❌ This email is already registered. Please enter a different email address:")
            return REG_GET_EMAIL
        
        # Save User
        new_user = User(
            telegram_id=telegram_id,
            name=name,
            email=email,
            status="Pending"
        )
        db.add(new_user)
        
        # Save Trading Account
        new_acc = TradingAccount(
            user_telegram_id=telegram_id,
            account_type=acc_type,
            status="Pending"
        )
        db.add(new_acc)
        db.commit()
        
        # Admin Alert
        alert = (
            f"🚨 *NEW REGISTRATION REQUEST*\n"
            f"👤 Name: {name}\n"
            f"📧 Email: {email}\n"
            f"💳 Telegram ID: `{telegram_id}`\n"
            f"💰 Account Type: *{acc_type}*\n"
            f"🔢 DB Account ID: `{new_acc.id}`\n"
            f"Please open the Web Admin Panel to approve the user and assign credentials."
        )
        await send_admin_notification(context.application, alert)
        
        # Notify specific group ID
        try:
            await context.application.bot.send_message(
                chat_id="-5536620816",
                text=alert,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error sending registration notification to group -5536620816: {e}")
        
        await update.message.reply_text(
            "✅ Registration submitted successfully!\n"
            "Your profile and trading account are now *Pending Admin Approval*.\n"
            "You will receive a message once approved with your credentials.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="btn_back")]]),
            parse_mode="Markdown"
        )
    finally:
        db.close()
        
    return ConversationHandler.END


# --- DEPOSIT FLOW ---
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        telegram_id = query.from_user.id
        message_target = query.message
    else:
        telegram_id = update.effective_user.id
        message_target = update.message
        
    db = SessionLocal()
    try:
        # User needs to have approved accounts
        accounts = db.query(TradingAccount).filter(
            TradingAccount.user_telegram_id == telegram_id,
            TradingAccount.status == "Approved"
        ).all()
        
        if not accounts:
            await message_target.reply_text(
                "❌ You do not have any approved trading accounts to deposit into. "
                "Please wait for your registration to be approved, or register an account.",
                reply_markup=persistent_markup,
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        keyboard = []
        for acc in accounts:
            label = f"{acc.account_type} - #{acc.account_number} (${acc.balance:,.2f})"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"depacc_{acc.id}")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_conv")])
        
        await message_target.reply_text(
            "💰 *Select the account you want to deposit into:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return DEP_CHOOSE_ACCOUNT
    finally:
        db.close()

async def deposit_choose_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acc_id = int(query.data.split("_")[1])
    context.user_data["dep_account_id"] = acc_id
    
    db = SessionLocal()
    try:
        acc = db.query(TradingAccount).filter(TradingAccount.id == acc_id).first()
        context.user_data["dep_acc_type"] = acc.account_type
        min_dep = 5.0 if acc.account_type == "Cent" else 10.0
        await query.message.reply_text(
            f"💰 You chose your *{acc.account_type} Account*.\n"
            f"The minimum deposit is *${min_dep:,.2f}*.\n\n"
            f"Please enter the amount you wish to deposit:",
            parse_mode="Markdown"
        )
        return DEP_GET_AMOUNT
    finally:
        db.close()

def generate_qr_code(link: str) -> io.BytesIO:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

def get_dynamic_khqr(amount: float) -> str:
    import requests
    url = "https://2008.site/payway/api/create-qr"
    headers = {"Content-Type": "application/json"}
    data = {
        "url": "https://link.payway.com.kh/ABAPAYMu475556i",
        "amount": f"{amount:.2f}"
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            res_json = response.json()
            return res_json.get("qr_string")
    except Exception as e:
        logger.error(f"Error fetching dynamic KHQR from 2008.site: {e}")
    return None

async def deposit_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount_str = update.message.text
    acc_type = context.user_data.get("dep_acc_type", "Cent")
    min_dep = 5.0 if acc_type == "Cent" else 10.0
    
    try:
        amount = float(amount_str)
        if amount < min_dep:
            await update.message.reply_text(
                f"❌ The minimum deposit for a *{acc_type} Account* is *${min_dep:,.2f}*.\n"
                f"Please enter a valid amount equal or higher:",
                parse_mode="Markdown"
            )
            return DEP_GET_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid positive number:")
        return DEP_GET_AMOUNT
        
    context.user_data["dep_amount"] = amount
    
    payment_details = (
        f"🏦 *ABA PAY Deposit Details*\n\n"
        f"💰 *Amount to Pay:* `${amount:,.2f}`\n\n"
        f"Scan the QR code below using your bank app to pay:\n\n"
        f"⚠️ *Instructions:*\n"
        f"After transferring the money, please take a screenshot or photo of your payment receipt and *send/upload* it directly in this chat."
    )
    
    qr_string = get_dynamic_khqr(amount)
    if qr_string:
        try:
            qr_io = generate_qr_code(qr_string)
            await update.message.reply_photo(
                photo=qr_io,
                caption=payment_details,
                parse_mode="Markdown"
            )
            return DEP_GET_RECEIPT
        except Exception as e:
            logger.error(f"Failed to generate dynamic QR: {e}")
            
    # Fallback to static merchant QR if API is down
    qr_path = "d:/work/trading/static/aba_qr.png"
    if os.path.exists(qr_path):
        await update.message.reply_photo(
            photo=open(qr_path, "rb"),
            caption=payment_details,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(payment_details, parse_mode="Markdown")
        
    return DEP_GET_RECEIPT




async def deposit_get_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a valid photo of your payment receipt.")
        return DEP_GET_RECEIPT
    
    photo_file = await update.message.photo[-1].get_file()
    telegram_id = update.effective_user.id
    acc_id = context.user_data["dep_account_id"]
    amount = context.user_data["dep_amount"]
    
    # Save receipt file locally
    file_name = f"receipt_{telegram_id}_{acc_id}_{photo_file.file_unique_id}.jpg"
    local_path = os.path.join(UPLOAD_DIR, file_name)
    await photo_file.download_to_drive(local_path)
    
    db = SessionLocal()
    try:
        acc = db.query(TradingAccount).filter(TradingAccount.id == acc_id).first()
        db_user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        new_tx = Transaction(
            user_telegram_id=telegram_id,
            trading_account_id=acc_id,
            type="Deposit",
            amount=amount,
            receipt_path=file_name,
            status="Pending"
        )
        db.add(new_tx)
        db.commit()
        
        # Notify Admin Channel
        alert = (
            f"💸 *NEW DEPOSIT REQUEST*\n"
            f"👤 User: {db_user.name}\n"
            f"💳 Account Number: `{acc.account_number}`\n"
            f"💰 Amount Sent: *${amount:,.2f}*\n"
            f"🔢 Transaction ID: `{new_tx.id}`\n"
            f"📂 Receipt saved as: `{file_name}`\n"
            f"Go to Web Admin Panel to verify and approve."
        )
        await send_admin_notification(context.application, alert)
        
        await update.message.reply_text(
            "✅ Payment receipt uploaded successfully!\n"
            "Our admin team will verify the payment and credit your account balance shortly.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="btn_back")]]),
            parse_mode="Markdown"
        )
    finally:
        db.close()
        
    return ConversationHandler.END


# --- WITHDRAWAL FLOW ---
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        telegram_id = query.from_user.id
        message_target = query.message
    else:
        telegram_id = update.effective_user.id
        message_target = update.message
        
    db = SessionLocal()
    try:
        # Only approved accounts with balance > 0
        accounts = db.query(TradingAccount).filter(
            TradingAccount.user_telegram_id == telegram_id,
            TradingAccount.status == "Approved",
            TradingAccount.balance > 0
        ).all()
        
        if not accounts:
            await message_target.reply_text(
                "❌ You do not have any approved trading accounts with a positive balance to withdraw from.",
                reply_markup=persistent_markup,
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        keyboard = []
        for acc in accounts:
            label = f"{acc.account_type} - #{acc.account_number} (${acc.balance:,.2f})"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"withacc_{acc.id}")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_conv")])
        
        await message_target.reply_text(
            "💸 *Select the account to withdraw from:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return WITHDRAW_CHOOSE_ACCOUNT
    finally:
        db.close()

async def withdraw_choose_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    acc_id = int(query.data.split("_")[1])
    context.user_data["with_account_id"] = acc_id
    
    db = SessionLocal()
    try:
        acc = db.query(TradingAccount).filter(TradingAccount.id == acc_id).first()
        context.user_data["with_max_balance"] = acc.balance
        context.user_data["with_acc_type"] = acc.account_type
        min_with = 5.0 if acc.account_type == "Cent" else 10.0
        await query.message.reply_text(
            f"Balance: *${acc.balance:,.2f}*\n"
            f"Minimum withdrawal: *${min_with:,.2f}*\n\n"
            f"Please enter the amount you wish to withdraw:",
            parse_mode="Markdown"
        )
        return WITHDRAW_GET_AMOUNT
    finally:
        db.close()

async def withdraw_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount_str = update.message.text
    acc_type = context.user_data.get("with_acc_type", "Cent")
    min_with = 5.0 if acc_type == "Cent" else 10.0
    try:
        amount = float(amount_str)
        max_balance = context.user_data["with_max_balance"]
        if amount < min_with:
            await update.message.reply_text(
                f"❌ The minimum withdrawal for a *{acc_type} Account* is *${min_with:,.2f}*.\n"
                f"Please enter a valid amount equal or higher:"
            )
            return WITHDRAW_GET_AMOUNT
        if amount > max_balance:
            await update.message.reply_text(
                f"❌ Insufficient funds. Your balance is ${max_balance:,.2f}.\n"
                f"Please enter a valid amount:"
            )
            return WITHDRAW_GET_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid positive number:")
        return WITHDRAW_GET_AMOUNT
        
    context.user_data["with_amount"] = amount
    await update.message.reply_text("Please enter your *Bank Name* (e.g., ABA Bank):", parse_mode="Markdown")
    return WITHDRAW_GET_BANK_NAME

async def withdraw_get_bank_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["with_bank_name"] = update.message.text
    await update.message.reply_text("Please enter your *Bank Account Number*:", parse_mode="Markdown")
    return WITHDRAW_GET_ACC_NUM

async def withdraw_get_acc_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["with_acc_num"] = update.message.text
    await update.message.reply_text("Please enter your *Bank Account Name*:", parse_mode="Markdown")
    return WITHDRAW_GET_ACC_NAME

async def withdraw_get_acc_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    acc_name = update.message.text
    telegram_id = update.effective_user.id
    acc_id = context.user_data["with_account_id"]
    amount = context.user_data["with_amount"]
    bank_name = context.user_data["with_bank_name"]
    acc_num = context.user_data["with_acc_num"]
    
    # Construct structured details
    details = f"Bank: {bank_name}\nAcc No: {acc_num}\nAcc Name: {acc_name}"
    
    db = SessionLocal()
    try:
        acc = db.query(TradingAccount).filter(TradingAccount.id == acc_id).first()
        db_user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        # Deduct balance temporarily (escrow status) so they can't double withdraw
        acc.balance -= amount
        
        # Save Transaction as Pending
        new_tx = Transaction(
            user_telegram_id=telegram_id,
            trading_account_id=acc_id,
            type="Withdrawal",
            amount=amount,
            details=details,
            status="Pending"
        )
        db.add(new_tx)
        db.commit()
        
        # Notify Admin Channel
        alert = (
            f"🚨 *NEW WITHDRAWAL REQUEST*\n"
            f"👤 User: {db_user.name}\n"
            f"💳 Account Number: `{acc.account_number}`\n"
            f"💰 Amount: *${amount:,.2f}*\n"
            f"🏦 Payment Details:\n"
            f"  • Bank Name: `{bank_name}`\n"
            f"  • Account Number: `{acc_num}`\n"
            f"  • Account Name: `{acc_name}`\n"
            f"🔢 Transaction ID: `{new_tx.id}`\n"
            f"Go to Web Admin Panel to approve or reject."
        )
        await send_admin_notification(context.application, alert)
        
        # Notify specific withdrawal group ID
        try:
            await context.application.bot.send_message(
                chat_id="-5536620816",
                text=alert,
                parse_mode="Markdown"
            )
            logger.info("Withdrawal notification sent to group -5536620816 successfully.")
        except Exception as e:
            logger.error(f"Error sending withdrawal notification to group -5536620816: {e}")
        
        await update.message.reply_text(
            "✅ Withdrawal request submitted successfully!\n"
            "Your funds have been placed in pending status. Our admin team will process your payment soon.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Menu", callback_data="btn_back")]]),
            parse_mode="Markdown"
        )
    finally:
        db.close()
        
    return ConversationHandler.END


# --- FORGOT PASSWORD FLOW ---
async def forgot_password_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_target = update.message if update.message else update.callback_query.message
    await message_target.reply_text(
        "🔑 *Forgot Password Request*\n\n"
        "Please enter the *Email Address* linked to your trading account:",
        parse_mode="Markdown"
    )
    return FORGOT_GET_EMAIL

async def forgot_password_get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text
    context.user_data["forgot_email"] = email
    await update.message.reply_text(
        "Please enter your *Trading Account ID / Number*:",
        parse_mode="Markdown"
    )
    return FORGOT_GET_ACC_NUM

async def forgot_password_get_acc_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    acc_num = update.message.text
    email = context.user_data.get("forgot_email")
    user = update.effective_user
    
    # 1. Send Admin Notification to Channel
    alert = (
        f"🔑 *PASSWORD RESET REQUEST*\n"
        f"👤 User: {user.first_name}\n"
        f"💳 Telegram ID: `{user.id}`\n"
        f"📧 Email: `{email}`\n"
        f"🔢 Trading Account ID: `{acc_num}`\n\n"
        f"Please reset the password for this account in the MT4/MT5 manager."
    )
    await send_admin_notification(context.application, alert)
    
    # 2. Send specifically to the group ID
    try:
        await context.application.bot.send_message(
            chat_id="-5536620816",
            text=alert,
            parse_mode="Markdown"
        )
        logger.info("Forgot password notification sent to group successfully.")
    except Exception as e:
        logger.error(f"Error sending forgot password to group: {e}")
        
    await update.message.reply_text(
        "✅ *Password Reset Request Submitted!*\n\n"
        "Your request has been sent to our admin team. We will reset your password and send it to you shortly.",
        reply_markup=persistent_markup,
        parse_mode="Markdown"
    )
    return ConversationHandler.END


# --- CANCEL / BACK HANDLERS ---
async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("❌ Request cancelled.")
    await start(update, context)
    return ConversationHandler.END


# Global Application reference to send notifications from FastAPI
application_instance = None

class PatchedApplication(Application):
    __slots__ = ("_Application__stop_running_marker", "__stop_running_marker")

def run_bot():
    global application_instance
    init_db()
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).application_class(PatchedApplication).build()
    application_instance = application

    
    # Registration Conversation Handler
    reg_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(register_start, pattern="^btn_register$"),
            MessageHandler(filters.Regex("^📝 Register Account$"), register_start)
        ],
        states={
            REG_CHOOSE_TYPE: [CallbackQueryHandler(register_type, pattern="^type_")],
            REG_GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            REG_GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern="^cancel_conv$")],
    )
    
    # Deposit Conversation Handler
    dep_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(deposit_start, pattern="^btn_deposit$"),
            MessageHandler(filters.Regex("^💰 Deposit$"), deposit_start)
        ],
        states={
            DEP_CHOOSE_ACCOUNT: [CallbackQueryHandler(deposit_choose_account, pattern="^depacc_")],
            DEP_GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_get_amount)],
            DEP_GET_RECEIPT: [MessageHandler(filters.PHOTO, deposit_get_receipt)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern="^cancel_conv$")],
    )
    
    # Withdrawal Conversation Handler
    withdraw_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(withdraw_start, pattern="^btn_withdraw$"),
            MessageHandler(filters.Regex("^💸 Withdraw$"), withdraw_start)
        ],
        states={
            WITHDRAW_CHOOSE_ACCOUNT: [CallbackQueryHandler(withdraw_choose_account, pattern="^withacc_")],
            WITHDRAW_GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_get_amount)],
            WITHDRAW_GET_BANK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_get_bank_name)],
            WITHDRAW_GET_ACC_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_get_acc_num)],
            WITHDRAW_GET_ACC_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_get_acc_name)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern="^cancel_conv$")],
    )
    
    # Forgot Password Conversation Handler
    forgot_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🔑 Forgot Password$"), forgot_password_start)
        ],
        states={
            FORGOT_GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, forgot_password_get_email)],
            FORGOT_GET_ACC_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, forgot_password_get_acc_num)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern="^cancel_conv$")],
    )
    
    # Basic Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(start, pattern="^btn_back$"))
    application.add_handler(CallbackQueryHandler(show_info, pattern="^btn_info$"))
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ My Account Info$"), show_info))
    
    # Add Conversations
    application.add_handler(reg_handler)
    application.add_handler(dep_handler)
    application.add_handler(withdraw_handler)
    application.add_handler(forgot_handler)
    
    # Start the Bot using polling
    logger.info("Starting Telegram Bot...")
    application.run_polling()

if __name__ == "__main__":
    run_bot()

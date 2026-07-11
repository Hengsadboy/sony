import os
import logging
import io
import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from database import init_db, SessionLocal, User, TradingAccount, Transaction, PasswordResetRequest, SystemSetting, get_setting
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
        group_id = get_setting("telegram_group_id", ADMIN_CHAT_ID)
        await application.bot.send_message(
            chat_id=group_id,
            text=text,
            parse_mode="Markdown"
        )
        logger.info("Admin notification sent successfully.")
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")


def is_bot_under_maintenance():
    db = SessionLocal()
    try:
        setting = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
        return setting and setting.value == "true"
    except Exception as e:
        logger.error(f"Error checking maintenance status: {e}")
        return False
    finally:
        db.close()


# Bilingual Localized Texts
TEXTS = {
    "start_lang": {
        "en": "🌐 Please choose your language / សូមជ្រើសរើសភាសារបស់អ្នក:",
        "km": "🌐 Please choose your language / សូមជ្រើសរើសភាសារបស់អ្នក:"
    },
    "welcome": {
        "en": (
            "👋 Welcome *{name}* to our *Manual Forex Broker*!\n\n"
            "Here you can register accounts, deposit, withdraw, and check your status completely manually. "
            "Our admin team will process your requests quickly.\n\n"
            "Please choose an option from the menu under the chat:"
        ),
        "km": (
            "👋 សូមស្វាគមន៍ *{name}* មកកាន់ *Manual Forex Broker* របស់យើង!\n\n"
            "នៅទីនេះអ្នកអាចចុះឈ្មោះគណនី, ដាក់ប្រាក់, ដកប្រាក់ និងពិនិត្យមើលស្ថានភាពរបស់អ្នកដោយផ្ទាល់។ "
            "ក្រុមការងាររបស់យើងនឹងដំណើរការសំណើរបស់អ្នកយ៉ាងរហ័ស។\n\n"
            "សូមជ្រើសរើសជម្រើសពីម៉ឺនុយខាងក្រោម:"
        )
    },
    "not_registered": {
        "en": "❌ You are not registered yet. Please click *📝 Register Account* to start.",
        "km": "❌ អ្នកមិនទាន់បានចុះឈ្មោះនៅឡើយទេ។ សូមចុច *📝 ចុះឈ្មោះគណនី* ដើម្បីចាប់ផ្តើម។"
    },
    "already_registered_title": {
        "en": "👤 *Profile Details*\nName: {name}\nEmail: {email}\nStatus: {status}\n\n💳 *Trading Accounts:*\n",
        "km": "👤 *ព័ត៌មានប្រវត្តិរូប*\nឈ្មោះ: {name}\nអ៊ីមែល: {email}\nស្ថានភាព: {status}\n\n💳 *គណនីជួញដូរ:*\n"
    },
    "no_trading_accounts": {
        "en": "_No trading accounts created yet._\n",
        "km": "_មិនទាន់មានគណនីជួញដូរនៅឡើយទេ។_\n"
    },
    "already_registered_limit": {
        "en": "❌ *Registration Rejected*\n\nYou already have a trading account. You can only register *one trading account* per Telegram profile.",
        "km": "❌ *ការចុះឈ្មោះត្រូវបានបដិសេធ*\n\nអ្នកមានគណនីជួញដូររួចហើយ។ អ្នកអាចចុះឈ្មោះបានតែ *គណនីជួញដូរមួយប៉ុណ្ណោះ* ក្នុងមួយ Telegram profile។"
    },
    "choose_type_instructions": {
        "en": (
            "📝 *How to Register:*\n"
            "1. Choose your account type below (Cent or USD).\n"
            "2. Provide your **Full Name**.\n"
            "3. Provide your **Email Address**.\n\n"
            "Our admin team will verify your request and issue your MT4/MT5 login details shortly!\n\n"
            "📝 *Choose your trading account type:*"
        ),
        "km": (
            "📝 *របៀបចុះឈ្មោះ:*\n"
            "1. ជ្រើសរើសប្រភេទគណនីខាងក្រោម (Cent ឬ USD)។\n"
            "2. ផ្តល់ជូន **ឈ្មោះពេញ** របស់អ្នក។\n"
            "3. ផ្តល់ជូន **អាសយដ្ឋានអ៊ីមែល** របស់អ្នក។\n\n"
            "ក្រុមការងាររបស់យើងនឹងផ្ទៀងផ្ទាត់សំណើរបស់អ្នក និងផ្តល់ព័ត៌មានគណនី MT4/MT5 ក្នុងពេលឆាប់ៗនេះ!\n\n"
            "📝 *សូមជ្រើសរើសប្រភេទគណនីជួញដូររបស់អ្នក:*"
        )
    },
    "reg_get_name": {
        "en": "Please enter your **Full Name** (for your trading account profile):",
        "km": "សូមបញ្ចូល **ឈ្មោះពេញ** របស់អ្នក (សម្រាប់ប្រវត្តិរូបគណនីជួញដូរ):"
    },
    "reg_get_email": {
        "en": "Please enter your **Email Address**:",
        "km": "សូមបញ្ចូល **អាសយដ្ឋានអ៊ីមែល** របស់អ្នក:"
    },
    "reg_invalid_email": {
        "en": "❌ Invalid email format. Please enter a valid email address:",
        "km": "❌ ទម្រង់អ៊ីមែលមិនត្រឹមត្រូវទេ។ សូមបញ្ចូលអាសយដ្ឋានអ៊ីមែលត្រឹមត្រូវ:"
    },
    "reg_email_exists": {
        "en": "❌ This email address is already registered. Please enter a different email address:",
        "km": "❌ អាសយដ្ឋានអ៊ីមែលនេះត្រូវបានចុះឈ្មោះរួចហើយ។ សូមបញ្ចូលអាសយដ្ឋានអ៊ីមែលផ្សេងទៀត:"
    },
    "reg_success": {
        "en": (
            "✅ Registration submitted successfully!\n"
            "Your profile and trading account are now *Pending Admin Approval*.\n"
            "You will receive a message once approved with your credentials."
        ),
        "km": (
            "✅ ការចុះឈ្មោះត្រូវបានដាក់ជូនដោយជោគជ័យ!\n"
            "ប្រវត្តិរូប និងគណនីជួញដូររបស់អ្នកស្ថិតក្នុងស្ថានភាព *រង់ចាំការអនុម័តពី Admin*។\n"
            "អ្នកនឹងទទួលបានសារប្រាប់នៅពេលទទួលបានការអនុម័ត និងគណនីចូល។"
        )
    },
    "dep_no_accounts": {
        "en": "❌ You do not have any approved trading accounts to deposit into. Please wait for registration approval.",
        "km": "❌ អ្នកមិនទាន់មានគណនីជួញដូរដែលបានអនុម័តសម្រាប់ដាក់ប្រាក់ឡើយទេ។ សូមរង់ចាំការអនុម័តចុះឈ្មោះជាមុនសិន។"
    },
    "dep_choose_instructions": {
        "en": (
            "💰 *How to Deposit:*\n"
            "1. Select the approved trading account from the list below.\n"
            "2. Enter the amount you want to deposit ($5 min for Cent, $10 min for USD).\n"
            "3. Scan the official KHQR code to send the funds via your banking app.\n"
            "4. Upload the screenshot of your payment receipt.\n\n"
            "💰 *Select the account you want to deposit into:*"
        ),
        "km": (
            "💰 *របៀបដាក់ប្រាក់:*\n"
            "1. ជ្រើសរើសគណនីជួញដូរដែលបានអនុម័តពីបញ្ជីខាងក្រោម។\n"
            "2. បញ្ចូលចំនួនទឹកប្រាក់ដែលចង់ដាក់ (អប្បបរមា $5 សម្រាប់ Cent, $10 សម្រាប់ USD)។\n"
            "3. ស្កែនកូដ KHQR ផ្លូវការដើម្បីផ្ញើប្រាក់តាមរយៈកម្មវិធីធនាគាររបស់អ្នក។\n"
            "4. ផ្ញើ/អាប់ឡូតរូបភាពបង្កាន់ដៃបង់ប្រាក់។\n\n"
            "💰 *សូមជ្រើសរើសគណនីដែលអ្នកចង់ដាក់ប្រាក់ចូល:*"
        )
    },
    "dep_get_amount": {
        "en": "Please enter the amount you wish to deposit:",
        "km": "សូមបញ្ចូលចំនួនទឹកប្រាក់ដែលអ្នកចង់ដាក់:"
    },
    "dep_invalid_amount": {
        "en": "❌ Minimum deposit is ${min_dep:,.2f}. Please enter a valid amount:",
        "km": "❌ ប្រាក់បញ្ញើអប្បបរមាគឺ ${min_dep:,.2f}។ សូមបញ្ចូលចំនួនទឹកប្រាក់ត្រឹមត្រូវ:"
    },
    "dep_payment_details": {
        "en": (
            "🏦 *ABA PAY Deposit Details*\n\n"
            "💰 *Amount to Pay:* `${amount:,.2f}`\n\n"
            "Scan the QR code below using your bank app to pay:\n\n"
            "⚠️ *Instructions:*\n"
            "After transferring the money, please take a screenshot of your payment receipt and *send/upload* it directly in this chat."
        ),
        "km": (
            "🏦 *ព័ត៌មានលម្អិតអំពីការដាក់ប្រាក់តាម ABA PAY*\n\n"
            "💰 *ចំនួនទឹកប្រាក់ត្រូវបង់:* `${amount:,.2f}`\n\n"
            "ស្កែនកូដ QR ខាងក្រោមដោយប្រើកម្មវិធីធនាគាររបស់អ្នកដើម្បីបង់ប្រាក់:\n\n"
            "⚠️ *ការណែនាំ:*\n"
            "បន្ទាប់ពីផ្ទេរប្រាក់រួច សូមថតរូបភាពបង្កាន់ដៃបង់ប្រាក់របស់អ្នក រួច *ផ្ញើ/អាប់ឡូត* វាដោយផ្ទាល់នៅក្នុងការជជែកនេះ។"
        )
    },
    "dep_invalid_receipt": {
        "en": "❌ Please send a valid photo of your payment receipt.",
        "km": "❌ សូមផ្ញើរូបភាពបង្កាន់ដៃបង់ប្រាក់ដែលមានសុពលភាព។"
    },
    "dep_success": {
        "en": (
            "✅ Payment receipt uploaded successfully!\n"
            "Our admin team will verify the payment and credit your account balance shortly."
        ),
        "km": (
            "✅ បង្កាន់ដៃបង់ប្រាក់ត្រូវបានអាប់ឡូតដោយជោគជ័យ!\n"
            "ក្រុមការងារ Admin របស់យើងនឹងផ្ទៀងផ្ទាត់ការបង់ប្រាក់ និងបញ្ចូលសមតុល្យគណនីរបស់អ្នកក្នុងពេលឆាប់ៗនេះ។"
        )
    },
    "with_no_accounts": {
        "en": "❌ You do not have any approved trading accounts to withdraw from.",
        "km": "❌ អ្នកមិនទាន់មានគណនីជួញដូរដែលបានអនុម័តសម្រាប់ដកប្រាក់ឡើយទេ។"
    },
    "with_choose_instructions": {
        "en": (
            "💸 *How to Withdraw:*\n"
            "1. Select the account you want to withdraw from.\n"
            "2. Enter the withdrawal amount ($5 min for Cent, $10 min for USD).\n"
            "3. Enter the Bank Name, Account Number, and Account Name.\n\n"
            "⚠️ *IMPORTANT WARNING:*\n"
            "The **Bank Account Name** and your **Trading Profile Name** *must match exactly*!\n"
            "If they do not match, the withdrawal request *will be cancelled* and the funds will be *lost with no refund*!\n\n"
            "💸 *Select the account to withdraw from:*"
        ),
        "km": (
            "💸 *របៀបដកប្រាក់:*\n"
            "1. ជ្រើសរើសគណនីដែលចង់ដកប្រាក់ចេញ។\n"
            "2. បញ្ចូលចំនួនទឹកប្រាក់ដែលត្រូវដក (អប្បបរមា $5 សម្រាប់ Cent, $10 សម្រាប់ USD)។\n"
            "3. បញ្ចូលឈ្មោះធនាគារ, លេខគណនី និងឈ្មោះម្ចាស់គណនី។\n\n"
            "⚠️ *ការព្រមានសំខាន់:*\n"
            "**ឈ្មោះគណនីធនាគារ** និង **ឈ្មោះប្រវត្តិរូបគណនីជួញដូរ** របស់អ្នក *ត្រូវតែដូចគ្នាទាំងស្រុង*!\n"
            "ប្រសិនបើមិនដូចគ្នាទេ សំណើដកប្រាក់ *នឹងត្រូវលុបចោល* ហើយប្រាក់នឹងត្រូវ *បាត់បង់ដោយគ្មានការបង្វិលសងឡើយ*!\n\n"
            "💸 *សូមជ្រើសរើសគណនីដែលត្រូវដកប្រាក់ចេញ:*"
        )
    },
    "with_min_warning": {
        "en": "Minimum withdrawal: *$5.00*\n\nPlease enter the amount you wish to withdraw:",
        "km": "ការដកប្រាក់អប្បបរមា: *$5.00*\n\nសូមបញ្ចូលចំនួនទឹកប្រាក់ដែលអ្នកចង់ដក:"
    },
    "with_invalid_amount": {
        "en": "❌ The minimum withdrawal is *$5.00*.\nPlease enter a valid amount equal or higher:",
        "km": "❌ ការដកប្រាក់អប្បបរមាគឺ *$5.00*។\nសូមបញ្ចូលចំនួនទឹកប្រាក់ស្មើ ឬខ្ពស់ជាងនេះ:"
    },
    "with_get_bank": {
        "en": "Please enter your *Bank Name* (e.g., ABA Bank):",
        "km": "សូមបញ្ចូល *ឈ្មោះធនាគារ* របស់អ្នក (ឧទាហរណ៍៖ ធនាគារ ABA)៖"
    },
    "with_get_acc_num": {
        "en": "Please enter your *Bank Account Number*:",
        "km": "សូមបញ្ចូល *លេខគណនីធនាគារ* របស់អ្នក៖"
    },
    "with_get_acc_name": {
        "en": "Please enter your *Bank Account Name*:",
        "km": "សូមបញ្ចូល *ឈ្មោះគណនីធនាគារ* របស់អ្នក៖"
    },
    "with_name_mismatch": {
        "en": (
            "❌ *Withdrawal Rejected!*\n\n"
            "The provided Bank Account Name (*{provided}*) does not match your trading profile name (*{profile}*).\n"
            "To prevent fraud, withdrawal bank accounts must belong to the registered user. "
            "This request has been cancelled and no funds were deducted."
        ),
        "km": (
            "❌ *ការដកប្រាក់ត្រូវបានបដិសេធ!*\n\n"
            "ឈ្មោះគណនីធនាគារដែលបានផ្តល់ជូន (*{provided}*) មិនត្រូវគ្នានឹងឈ្មោះប្រវត្តិរូបជួញដូររបស់អ្នក (*{profile}*) ឡើយ។\n"
            "ដើម្បីការពារការបន្លំ គណនីធនាគារដកប្រាក់ត្រូវតែជារបស់អ្នកចុះឈ្មោះផ្ទាល់ខ្លួន។ "
            "សំណើនេះត្រូវបានលុបចោល ហើយគ្មានការដកប្រាក់ឡើយ។"
        )
    },
    "with_success": {
        "en": (
            "✅ Withdrawal request submitted successfully!\n"
            "Our admin team will process your payment soon."
        ),
        "km": (
            "✅ សំណើដកប្រាក់ត្រូវបានដាក់ជូនដោយជោគជ័យ!\n"
            "ក្រុមការងារ Admin របស់យើងនឹងដំណើរការការបង់ប្រាក់ជូនអ្នកក្នុងពេលឆាប់ៗនេះ។"
        )
    },
    "forgot_instructions": {
        "en": (
            "🔑 *How to Reset Password:*\n"
            "1. Enter the registered email address of your profile.\n"
            "2. Enter your MT4/MT5 Trading Account ID / Number.\n\n"
            "Our admin team will reset the password and contact you directly in this chat with the new login details!\n\n"
            "🔑 Please enter the *Email Address* linked to your trading account:"
        ),
        "km": (
            "🔑 *របៀបផ្លាស់ប្តូរលេខសម្ងាត់:*\n"
            "1. បញ្ចូលអាសយដ្ឋានអ៊ីមែលដែលបានចុះឈ្មោះ។\n"
            "2. បញ្ចូលលេខសម្គាល់/លេខគណនីជួញដូរ MT4/MT5 របស់អ្នក។\n\n"
            "ក្រុមការងារ Admin របស់យើងនឹងផ្លាស់ប្តូរលេខសម្ងាត់ថ្មី និងផ្ញើជូនអ្នកដោយផ្ទាល់នៅក្នុងការជជែកនេះ!\n\n"
            "🔑 សូមបញ្ចូល *អាសយដ្ឋានអ៊ីមែល* ដែលភ្ជាប់ជាមួយគណនីជួញដូររបស់អ្នក:"
        )
    },
    "forgot_invalid_email": {
        "en": "❌ This email address is not registered in our system. Please enter a valid email address:",
        "km": "❌ អាសយដ្ឋានអ៊ីមែលនេះមិនត្រូវបានចុះឈ្មោះក្នុងប្រព័ន្ធរបស់យើងទេ។ សូមបញ្ចូលអាសយដ្ឋានអ៊ីមែលដែលមានសុពលភាព:"
    },
    "forgot_get_acc_num": {
        "en": "Please enter your *Trading Account ID / Number*:",
        "km": "សូមបញ្ចូល *លេខសម្គាល់ / លេខគណនីជួញដូរ* របស់អ្នក:"
    },
    "forgot_acc_not_found": {
        "en": "❌ Trading Account number not found under this email. Please enter a valid Account Number:",
        "km": "❌ រកមិនឃើញលេខគណនីជួញដូរក្រោមអ៊ីមែលនេះទេ។ សូមបញ្ចូលលេខគណនីត្រឹមត្រូវ:"
    },
    "forgot_success": {
        "en": (
            "✅ *Password Reset Request Submitted!*\n\n"
            "Your request for Account *#{acc_num}* has been sent to our admin team. "
            "We will reset your password and contact you shortly."
        ),
        "km": (
            "✅ *សំណើផ្លាស់ប្តូរលេខសម្ងាត់ត្រូវបានដាក់ជូន!*\n\n"
            "សំណើរបស់អ្នកសម្រាប់គណនី *#{acc_num}* ត្រូវបានផ្ញើទៅកាន់ក្រុមការងារ Admin។ "
            "យើងនឹងផ្លាស់ប្តូរលេខសម្ងាត់របស់អ្នក និងទាក់ទងទៅអ្នកវិញក្នុងពេលឆាប់ៗនេះ។"
        )
    }
}


def get_user_lang(telegram_id, context):
    if context and "lang" in context.user_data:
        return context.user_data["lang"]
        
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if user and user.language:
            return user.language
    except Exception:
        pass
    finally:
        db.close()
    return "en"


def get_persistent_markup(lang):
    if lang == "km":
        reply_keyboard = [
            ["📝 ចុះឈ្មោះគណនី", "ℹ️ ព័ត៌មានគណនី"],
            ["💰 ដាក់ប្រាក់", "💸 ដកប្រាក់"],
            ["🔑 ភ្លេចលេខសម្ងាត់"]
        ]
    else:
        reply_keyboard = [
            ["📝 Register Account", "ℹ️ My Account Info"],
            ["💰 Deposit", "💸 Withdraw"],
            ["🔑 Forgot Password"]
        ]
    return ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)


# --- START COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_bot_under_maintenance():
        message_target = update.message if update.message else update.callback_query.message
        await message_target.reply_text(
            "⚠️ *System Maintenance in Progress*\n\n"
            "Our Telegram bot is currently undergoing maintenance/updates to improve our services.\n"
            "All trading systems, deposits, and withdrawals remain safe. "
            "Please try again in a little while! Thank you for your patience.",
            parse_mode="Markdown"
        )
        if update.callback_query:
            await update.callback_query.answer()
        return

    message_target = update.message if update.message else update.callback_query.message
    
    # Render language selection inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            InlineKeyboardButton("🇰🇭 Khmer (ភាសាខ្មែរ)", callback_data="lang_km")
        ]
    ]
    await message_target.reply_text(
        "🌐 Please choose your language / សូមជ្រើសរើសភាសារបស់អ្នក:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    if update.callback_query:
        await update.callback_query.answer()


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_")[1]
    
    context.user_data["lang"] = lang
    telegram_id = query.from_user.id
    
    # Save selection to user in database if they already exist
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if user:
            user.language = lang
            db.commit()
    except Exception as e:
        logger.error(f"Error saving language selection: {e}")
    finally:
        db.close()
        
    # Send welcome text in selected language with keyboard
    first_name = (query.from_user.first_name or "Trader").replace("*", "").replace("_", "").replace("[", "").replace("`", "")
    welcome_template = get_setting(f"welcome_msg_{lang}", TEXTS["welcome"][lang])
    welcome_text = welcome_template.format(name=first_name)
    persistent_markup = get_persistent_markup(lang)
    
    target_msg = query.message if query.message else update.effective_message
    await target_msg.reply_text(
        welcome_text,
        reply_markup=persistent_markup,
        parse_mode="Markdown"
    )



# --- MY ACCOUNT INFO ---
async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_bot_under_maintenance():
        message_target = update.message if update.message else update.callback_query.message
        await message_target.reply_text(
            "⚠️ *System Maintenance in Progress*\n\n"
            "Our Telegram bot is currently undergoing maintenance/updates to improve our services.\n"
            "All trading systems, deposits, and withdrawals remain safe. "
            "Please try again in a little while! Thank you for your patience.",
            parse_mode="Markdown"
        )
        if update.callback_query:
            await update.callback_query.answer()
        return

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
        lang = get_user_lang(telegram_id, context)
        db_user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not db_user:
            await message_target.reply_text(
                TEXTS["not_registered"][lang],
                reply_markup=get_persistent_markup(lang),
                parse_mode="Markdown"
            )
            return
        
        info_text = TEXTS["already_registered_title"][lang].format(
            name=db_user.name,
            email=db_user.email,
            status=db_user.status
        )
        
        accounts = db.query(TradingAccount).filter(TradingAccount.user_telegram_id == telegram_id).all()
        if not accounts:
            info_text += TEXTS["no_trading_accounts"][lang]
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
                    f"  • Status: {acc.status}\n\n"
                )
        
        await message_target.reply_text(info_text, reply_markup=get_persistent_markup(lang), parse_mode="Markdown")
    finally:
        db.close()


# --- REGISTRATION FLOW ---
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_bot_under_maintenance():
        message_target = update.message if update.message else update.callback_query.message
        await message_target.reply_text(
            "⚠️ *System Maintenance in Progress*\n\n"
            "Our Telegram bot is currently undergoing maintenance/updates to improve our services.\n"
            "All trading systems, deposits, and withdrawals remain safe. "
            "Please try again in a little while! Thank you for your patience.",
            parse_mode="Markdown"
        )
        if update.callback_query:
            await update.callback_query.answer()
        return ConversationHandler.END

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
        lang = get_user_lang(telegram_id, context)
        # Enforce 1 account per Telegram profile rule
        existing_acc = db.query(TradingAccount).filter(TradingAccount.user_telegram_id == telegram_id).first()
        if existing_acc:
            await message_target.reply_text(
                TEXTS["already_registered_limit"][lang],
                reply_markup=get_persistent_markup(lang),
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
        [InlineKeyboardButton("❌ Cancel / បោះបង់", callback_data="cancel_conv")],
    ]
    await message_target.reply_text(
        TEXTS["choose_type_instructions"][lang],
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
        lang = get_user_lang(telegram_id, context)
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
                group_id = get_setting("telegram_group_id", "-5536620816")
                await context.application.bot.send_message(
                    chat_id=group_id,
                    text=alert,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error sending account request notification: {e}")
            
            success_msg = (
                "✅ Your request for a new trading account has been submitted!\n"
                "Our admin will assign your login credentials shortly. You will be notified here."
                if lang == "en" else
                "✅ សំណើសម្រាប់គណនីជួញដូរថ្មីរបស់អ្នកត្រូវបានដាក់ជូន!\n"
                "ក្រុមការងារ Admin របស់យើងនឹងផ្តល់ព័ត៌មានគណនីក្នុងពេលឆាប់ៗនេះ។ អ្នកនឹងទទួលបានសារជូនដំណឹងនៅទីនេះ។"
            )
            
            await query.message.reply_text(
                success_msg,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back / ត្រឡប់ក្រោយ", callback_data="btn_back")]]),
                parse_mode="Markdown"
            )
        finally:
            db.close()
        return ConversationHandler.END

    lang = get_user_lang(query.from_user.id, context)
    await query.message.reply_text(TEXTS["reg_get_name"][lang], parse_mode="Markdown")
    return REG_GET_NAME

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(update.effective_user.id, context)
    context.user_data["reg_name"] = update.message.text
    await update.message.reply_text(TEXTS["reg_get_email"][lang], parse_mode="Markdown")
    return REG_GET_EMAIL

async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    telegram_id = update.effective_user.id
    name = context.user_data["reg_name"]
    acc_type = context.user_data["reg_acc_type"]
    lang = get_user_lang(telegram_id, context)
    
    # Simple email validation
    if "@" not in email or "." not in email:
        await update.message.reply_text(TEXTS["reg_invalid_email"][lang])
        return REG_GET_EMAIL

    db = SessionLocal()
    try:
        # Check if email is already taken
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            await update.message.reply_text(TEXTS["reg_email_exists"][lang])
            return REG_GET_EMAIL
        
        # Save User (store language preference)
        new_user = User(
            telegram_id=telegram_id,
            name=name,
            email=email,
            language=lang,
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
            group_id = get_setting("telegram_group_id", "-5536620816")
            await context.application.bot.send_message(
                chat_id=group_id,
                text=alert,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error sending registration notification: {e}")
            
        await update.message.reply_text(
            TEXTS["reg_success"][lang],
            reply_markup=get_persistent_markup(lang),
            parse_mode="Markdown"
        )
    finally:
        db.close()
        
    return ConversationHandler.END


# --- DEPOSIT FLOW ---
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_bot_under_maintenance():
        message_target = update.message if update.message else update.callback_query.message
        await message_target.reply_text(
            "⚠️ *System Maintenance in Progress*\n\n"
            "Our Telegram bot is currently undergoing maintenance/updates to improve our services.\n"
            "All trading systems, deposits, and withdrawals remain safe. "
            "Please try again in a little while! Thank you for your patience.",
            parse_mode="Markdown"
        )
        if update.callback_query:
            await update.callback_query.answer()
        return ConversationHandler.END

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
        
        lang = get_user_lang(telegram_id, context)
        if not accounts:
            await message_target.reply_text(
                TEXTS["dep_no_accounts"][lang],
                reply_markup=get_persistent_markup(lang),
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        keyboard = []
        for acc in accounts:
            label = f"{acc.account_type} Account - #{acc.account_number}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"depacc_{acc.id}")])
        keyboard.append([InlineKeyboardButton("❌ Cancel / បោះបង់", callback_data="cancel_conv")])
        
        await message_target.reply_text(
            TEXTS["dep_choose_instructions"][lang],
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
        min_dep = 1.0 if acc.account_type == "Cent" else 5.0
        max_dep = 1000.0
        lang = get_user_lang(query.from_user.id, context)
        
        choose_msg = (
            f"💰 You chose your *{acc.account_type} Account*.\n"
            f"The deposit limit is *${min_dep:,.2f}* to *${max_dep:,.2f}*.\n\n"
            f"Please enter the amount you wish to deposit:"
            if lang == "en" else
            f"💰 អ្នកបានជ្រើសរើស *គណនី {acc.account_type}*។\n"
            f"ចំនួនកំណត់ដាក់ប្រាក់គឺ *${min_dep:,.2f}* ដល់ *${max_dep:,.2f}*។\n\n"
            f"សូមបញ្ចូលចំនួនទឹកប្រាក់ដែលអ្នកចង់ដាក់:"
        )
        
        await query.message.reply_text(
            choose_msg,
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
    aba_link = get_setting("aba_pay_link", "https://link.payway.com.kh/ABAPAYMu475556i")
    data = {
        "url": aba_link,
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
    min_dep = 1.0 if acc_type == "Cent" else 5.0
    max_dep = 1000.0
    lang = get_user_lang(update.effective_user.id, context)
    
    try:
        amount = float(amount_str)
        if amount < min_dep or amount > max_dep:
            if lang == "en":
                err_msg = f"❌ Deposit must be between *${min_dep:,.2f}* and *${max_dep:,.2f}*."
            else:
                err_msg = f"❌ ការដាក់ប្រាក់ត្រូវតែស្ថិតនៅចន្លោះ *${min_dep:,.2f}* ដល់ *${max_dep:,.2f}*។"
            await update.message.reply_text(
                err_msg,
                parse_mode="Markdown"
            )
            return DEP_GET_AMOUNT
    except ValueError:
        invalid_num_msg = "❌ Please enter a valid positive number:" if lang == "en" else "❌ សូមបញ្ចូលចំនួនលេខវិជ្ជមានដែលមានសុពលភាព:"
        await update.message.reply_text(invalid_num_msg)
        return DEP_GET_AMOUNT
        
    context.user_data["dep_amount"] = amount
    
    payment_details = TEXTS["dep_payment_details"][lang].format(amount=amount)
    
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
    if is_bot_under_maintenance():
        message_target = update.message if update.message else update.callback_query.message
        await message_target.reply_text(
            "⚠️ *System Maintenance in Progress*\n\n"
            "Our Telegram bot is currently undergoing maintenance/updates to improve our services.\n"
            "All trading systems, deposits, and withdrawals remain safe. "
            "Please try again in a little while! Thank you for your patience.",
            parse_mode="Markdown"
        )
        if update.callback_query:
            await update.callback_query.answer()
        return ConversationHandler.END

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
        accounts = db.query(TradingAccount).filter(
            TradingAccount.user_telegram_id == telegram_id,
            TradingAccount.status == "Approved"
        ).all()
        lang = get_user_lang(telegram_id, context)
        if not accounts:
            await message_target.reply_text(
                TEXTS["with_no_accounts"][lang],
                reply_markup=get_persistent_markup(lang),
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        keyboard = []
        for acc in accounts:
            label = f"{acc.account_type} Account - #{acc.account_number}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"withacc_{acc.id}")])
        keyboard.append([InlineKeyboardButton("❌ Cancel / បោះបង់", callback_data="cancel_conv")])
        
        await message_target.reply_text(
            TEXTS["with_choose_instructions"][lang],
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
        context.user_data["with_acc_type"] = acc.account_type
        lang = get_user_lang(query.from_user.id, context)
        await query.message.reply_text(
            TEXTS["with_min_warning"][lang],
            parse_mode="Markdown"
        )
        return WITHDRAW_GET_AMOUNT
    finally:
        db.close()

async def withdraw_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount_str = update.message.text
    min_with = 5.0
    lang = get_user_lang(update.effective_user.id, context)
    try:
        amount = float(amount_str)
        if amount < min_with:
            await update.message.reply_text(
                TEXTS["with_invalid_amount"][lang]
            )
            return WITHDRAW_GET_AMOUNT
    except ValueError:
        invalid_num_msg = "❌ Please enter a valid positive number:" if lang == "en" else "❌ សូមបញ្ចូលចំនួនលេខវិជ្ជមានដែលមានសុពលភាព:"
        await update.message.reply_text(invalid_num_msg)
        return WITHDRAW_GET_AMOUNT
        
    context.user_data["with_amount"] = amount
    await update.message.reply_text(TEXTS["with_get_bank"][lang], parse_mode="Markdown")
    return WITHDRAW_GET_BANK_NAME

async def withdraw_get_bank_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(update.effective_user.id, context)
    context.user_data["with_bank_name"] = update.message.text
    await update.message.reply_text(TEXTS["with_get_acc_num"][lang], parse_mode="Markdown")
    return WITHDRAW_GET_ACC_NUM

async def withdraw_get_acc_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(update.effective_user.id, context)
    context.user_data["with_acc_num"] = update.message.text
    await update.message.reply_text(TEXTS["with_get_acc_name"][lang], parse_mode="Markdown")
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
        
        # Verify that the provided Bank Account Name matches the user's trading profile name
        lang = get_user_lang(telegram_id, context)
        clean_provided_name = " ".join(acc_name.lower().split())
        clean_profile_name = " ".join(db_user.name.lower().split())
        if clean_provided_name != clean_profile_name:
            err_msg = TEXTS["with_name_mismatch"][lang].format(provided=acc_name, profile=db_user.name)
            await update.message.reply_text(
                err_msg,
                reply_markup=get_persistent_markup(lang),
                parse_mode="Markdown"
            )
            return ConversationHandler.END
            
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
            group_id = get_setting("telegram_group_id", "-5536620816")
            await context.application.bot.send_message(
                chat_id=group_id,
                text=alert,
                parse_mode="Markdown"
            )
            logger.info("Withdrawal notification sent to group successfully.")
        except Exception as e:
            logger.error(f"Error sending withdrawal notification: {e}")
        
        await update.message.reply_text(
            TEXTS["with_success"][lang],
            reply_markup=get_persistent_markup(lang),
            parse_mode="Markdown"
        )
    finally:
        db.close()
        
    return ConversationHandler.END


# --- FORGOT PASSWORD FLOW ---
async def forgot_password_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_bot_under_maintenance():
        message_target = update.message if update.message else update.callback_query.message
        await message_target.reply_text(
            "⚠️ *System Maintenance in Progress*\n\n"
            "Our Telegram bot is currently undergoing maintenance/updates to improve our services.\n"
            "All trading systems, deposits, and withdrawals remain safe. "
            "Please try again in a little while! Thank you for your patience.",
            parse_mode="Markdown"
        )
        if update.callback_query:
            await update.callback_query.answer()
        return ConversationHandler.END

    message_target = update.message if update.message else update.callback_query.message
    lang = get_user_lang(update.effective_user.id, context)
    await message_target.reply_text(
        TEXTS["forgot_instructions"][lang],
        parse_mode="Markdown"
    )
    return FORGOT_GET_EMAIL

async def forgot_password_get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    telegram_id = update.effective_user.id
    lang = get_user_lang(telegram_id, context)
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            await update.message.reply_text(
                TEXTS["forgot_invalid_email"][lang],
                parse_mode="Markdown"
            )
            return FORGOT_GET_EMAIL
    finally:
        db.close()
        
    context.user_data["forgot_email"] = email
    await update.message.reply_text(
        TEXTS["forgot_get_acc_num"][lang],
        parse_mode="Markdown"
    )
    return FORGOT_GET_ACC_NUM

async def forgot_password_get_acc_num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    acc_num = update.message.text
    email = context.user_data.get("forgot_email")
    
    db = SessionLocal()
    try:
        lang = get_user_lang(update.effective_user.id, context)
        # Check if the user profile exists with this email
        db_user = db.query(User).filter(User.email == email).first()
        if not db_user:
            cancel_msg = "❌ This email is not registered. Request cancelled." if lang == "en" else "❌ អ៊ីមែលនេះមិនត្រូវបានចុះឈ្មោះទេ។ សំណើត្រូវបានលុបចោល។"
            await update.message.reply_text(
                cancel_msg,
                reply_markup=get_persistent_markup(lang),
                parse_mode="Markdown"
            )
            return ConversationHandler.END
            
        # Check if there is a trading account with this account number belonging to this user
        acc = db.query(TradingAccount).filter(
            TradingAccount.user_telegram_id == db_user.telegram_id,
            TradingAccount.account_number == acc_num
        ).first()
        
        if not acc:
            await update.message.reply_text(
                TEXTS["forgot_acc_not_found"][lang],
                parse_mode="Markdown"
            )
            return FORGOT_GET_ACC_NUM
            
        # Create a database record for the password reset request
        new_request = PasswordResetRequest(
            user_telegram_id=db_user.telegram_id,
            trading_account_id=acc.id,
            status="Pending"
        )
        db.add(new_request)
        db.commit()

        # If it exists, proceed to notify the admins
        alert = (
            f"🔑 *PASSWORD RESET REQUEST*\n"
            f"👤 User: {db_user.name}\n"
            f"💳 Telegram ID: `{db_user.telegram_id}`\n"
            f"📧 Email: `{email}`\n"
            f"🔢 Trading Account ID: `{acc_num}` ({acc.account_type})\n\n"
            f"Please reset the password for this account in the MT4/MT5 manager."
        )
        await send_admin_notification(context.application, alert)
        
        # Notify specific group
        try:
            group_id = get_setting("telegram_group_id", "-5536620816")
            await context.application.bot.send_message(
                chat_id=group_id,
                text=alert,
                parse_mode="Markdown"
            )
            logger.info("Forgot password notification sent to group successfully.")
        except Exception as e:
            logger.error(f"Error sending forgot password to group: {e}")
            
        await update.message.reply_text(
            TEXTS["forgot_success"][lang].format(acc_num=acc_num),
            reply_markup=get_persistent_markup(lang),
            parse_mode="Markdown"
        )
    finally:
        db.close()
        
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
    
    token = get_setting("telegram_bot_token", TELEGRAM_BOT_TOKEN)
    application = Application.builder().token(token).application_class(PatchedApplication).build()
    application_instance = application

    
    # Registration Conversation Handler
    reg_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(register_start, pattern="^btn_register$"),
            MessageHandler(filters.Regex("^(📝 Register Account|📝 ចុះឈ្មោះគណនី)$"), register_start)
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
            MessageHandler(filters.Regex("^(💰 Deposit|💰 ដាក់ប្រាក់)$"), deposit_start)
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
            MessageHandler(filters.Regex("^(💸 Withdraw|💸 ដកប្រាក់)$"), withdraw_start)
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
            MessageHandler(filters.Regex("^(🔑 Forgot Password|🔑 ភ្លេចលេខសម្ងាត់)$"), forgot_password_start)
        ],
        states={
            FORGOT_GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, forgot_password_get_email)],
            FORGOT_GET_ACC_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, forgot_password_get_acc_num)],
        },
        fallbacks=[CallbackQueryHandler(cancel_conv, pattern="^cancel_conv$")],
    )
    
    # Basic Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(set_language, pattern="^lang_"))
    application.add_handler(CallbackQueryHandler(start, pattern="^btn_back$"))
    application.add_handler(CallbackQueryHandler(show_info, pattern="^btn_info$"))
    application.add_handler(MessageHandler(filters.Regex("^(ℹ️ My Account Info|ℹ️ ព័ត៌មានគណនី)$"), show_info))
    
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

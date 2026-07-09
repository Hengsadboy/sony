import os
import shutil
from fastapi import FastAPI, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from database import get_db, init_db, User, TradingAccount, Transaction, PasswordResetRequest, SystemSetting
from config import ADMIN_USERNAME, ADMIN_PASSWORD, TELEGRAM_BOT_TOKEN, UPLOAD_DIR, BASE_DIR
from telegram import Bot
import uvicorn

# Initialize database
init_db()

app = FastAPI(title="Forex Broker Admin Panel")

# Mount Static Files & Templates (Platform Independent)
os.makedirs(UPLOAD_DIR, exist_ok=True)
static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(os.path.join(static_dir, "css"), exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
templates.env.cache = None

# Standalone Telegram Bot for sending alerts
class DynamicBot:
    def __getattr__(self, name):
        from database import get_setting
        token = get_setting("telegram_bot_token", TELEGRAM_BOT_TOKEN)
        actual_bot = Bot(token=token)
        return getattr(actual_bot, name)

bot = DynamicBot()

# Simple Mock Session store for Admin Login
admin_sessions = set()

# Helper to verify auth
def get_current_admin(request: Request):
    session_token = request.cookies.get("admin_session")
    if session_token not in admin_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return True

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Redirect to dashboard if logged in, else login page
    session_token = request.cookies.get("admin_session")
    if session_token in admin_sessions:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/dashboard", status_code=303)
        # Generate dummy session token
        session_token = "secure_admin_session_token_12345"
        admin_sessions.add(session_token)
        response.set_cookie(key="admin_session", value=session_token, httponly=True)
        return response
    
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Invalid username or password"}
    )

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("admin_session")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        get_current_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
    
    # Fetch pending registrations
    pending_registrations = db.query(TradingAccount).filter(TradingAccount.status == "Pending").all()
    
    # Fetch pending transactions (Deposits & Withdrawals)
    pending_txs = db.query(Transaction).filter(Transaction.status == "Pending").all()
    
    # Split deposits and withdrawals
    pending_deposits = [tx for tx in pending_txs if tx.type == "Deposit"]
    pending_withdrawals = [tx for tx in pending_txs if tx.type == "Withdrawal"]
    
    # Fetch overall approved accounts for reference
    all_accounts = db.query(TradingAccount).filter(TradingAccount.status == "Approved").all()
    
    # Fetch pending password reset requests
    pending_resets = db.query(PasswordResetRequest).filter(PasswordResetRequest.status == "Pending").all()
    
    # Fetch historical processed transactions (Approved or Rejected)
    history_txs = db.query(Transaction).filter(
        Transaction.status.in_(["Approved", "Rejected"])
    ).order_by(Transaction.created_at.desc()).all()
    
    # Split historical transactions into separate lists for deposits and withdrawals
    history_deposits = [tx for tx in history_txs if tx.type == "Deposit"]
    history_withdrawals = [tx for tx in history_txs if tx.type == "Withdrawal"]
    
    # Fetch maintenance mode status
    maintenance = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
    maintenance_enabled = maintenance and maintenance.value == "true"
    
    aba_pay_link_setting = db.query(SystemSetting).filter(SystemSetting.key == "aba_pay_link").first()
    aba_pay_link = aba_pay_link_setting.value if aba_pay_link_setting else "https://link.payway.com.kh/ABAPAYMu475556i"
    
    telegram_group_id_setting = db.query(SystemSetting).filter(SystemSetting.key == "telegram_group_id").first()
    telegram_group_id = telegram_group_id_setting.value if telegram_group_id_setting else "-5536620816"
    
    telegram_bot_token_setting = db.query(SystemSetting).filter(SystemSetting.key == "telegram_bot_token").first()
    telegram_bot_token = telegram_bot_token_setting.value if telegram_bot_token_setting else ""
    
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "pending_registrations": pending_registrations,
            "pending_deposits": pending_deposits,
            "pending_withdrawals": pending_withdrawals,
            "all_accounts": all_accounts,
            "pending_resets": pending_resets,
            "history_deposits": history_deposits,
            "history_withdrawals": history_withdrawals,
            "maintenance_enabled": maintenance_enabled,
            "aba_pay_link": aba_pay_link,
            "telegram_group_id": telegram_group_id,
            "telegram_bot_token": telegram_bot_token
        }
    )

# --- APPROVAL ACTIONS ---

@app.post("/approve-registration/{acc_id}")
async def approve_registration(
    acc_id: int,
    account_number: str = Form(...),
    login_details: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    acc = db.query(TradingAccount).filter(TradingAccount.id == acc_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
        
    acc.account_number = account_number
    acc.login = login_details
    acc.password = password
    acc.status = "Approved"
    
    # Also set user status to Approved if this is their first account
    user = db.query(User).filter(User.telegram_id == acc.user_telegram_id).first()
    if user:
        user.status = "Approved"
        
    db.commit()
    
    # Send telegram message to user
    try:
        lang = user.language if (user and user.language) else "en"
        if lang == "km":
            user_message = (
                f"🎉 *គណនីជួញដូរត្រូវបានអនុម័ត!*\n\n"
                f"សំណើសម្រាប់ *គណនី {acc.account_type}* របស់អ្នកត្រូវបានអនុម័តដោយ Admin។\n\n"
                f"🔑 *ព័ត៌មានលម្អិតគណនី:*\n"
                f"• លេខគណនី: `{account_number}`\n"
                f"• ឈ្មោះចូល: `{login_details}`\n"
                f"• លេខសម្ងាត់: `{password}`\n\n"
                f"ឥឡូវនេះអ្នកអាចដាក់ប្រាក់ដើម្បីចាប់ផ្តើមជួញដូរបានហើយ។"
            )
        else:
            user_message = (
                f"🎉 *Trading Account Approved!*\n\n"
                f"Your request for a *{acc.account_type} Account* has been approved by the Admin.\n\n"
                f"🔑 *Account Details:*\n"
                f"• Account Number: `{account_number}`\n"
                f"• Login: `{login_details}`\n"
                f"• Password: `{password}`\n\n"
                f"You can now deposit funds to begin trading."
            )
        await bot.send_message(chat_id=acc.user_telegram_id, text=user_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending message to user: {e}")
        
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/approve-deposit/{tx_id}")
async def approve_deposit(
    tx_id: int,
    amount: float = Form(...),
    db: Session = Depends(get_db)
):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    tx.status = "Approved"
    tx.amount = amount  # overwrite amount in case the admin typed in correct amount from the receipt
    
    acc = db.query(TradingAccount).filter(TradingAccount.id == tx.trading_account_id).first()
    if acc:
        acc.balance += amount
        
    db.commit()
    
    # Send telegram message to user
    try:
        user = db.query(User).filter(User.telegram_id == tx.user_telegram_id).first()
        lang = user.language if (user and user.language) else "en"
        if lang == "km":
            user_message = (
                f"💰 *ការដាក់ប្រាក់ត្រូវបានអនុម័ត!*\n\n"
                f"ការដាក់ប្រាក់ចំនួន *${amount:,.2f}* ទៅក្នុងគណនី *#{acc.account_number}* របស់អ្នកត្រូវបានអនុម័ត និងបញ្ចូលសមតុល្យរួចរាល់ហើយ។\n"
                f"សមតុល្យបច្ចុប្បន្ន: *${acc.balance:,.2f}*"
            )
        else:
            user_message = (
                f"💰 *Deposit Approved!*\n\n"
                f"Your deposit of *${amount:,.2f}* into account *#{acc.account_number}* has been approved and credited.\n"
                f"Current Balance: *${acc.balance:,.2f}*"
            )
        await bot.send_message(chat_id=tx.user_telegram_id, text=user_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending message to user: {e}")
        
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/reject-deposit/{tx_id}")
async def reject_deposit(tx_id: int, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    tx.status = "Rejected"
    db.commit()
    
    # Send telegram message to user
    try:
        user = db.query(User).filter(User.telegram_id == tx.user_telegram_id).first()
        lang = user.language if (user and user.language) else "en"
        if lang == "km":
            user_message = (
                f"❌ *ការដាក់ប្រាក់ត្រូវបានបដិសេធ*\n\n"
                f"សំណើដាក់ប្រាក់របស់អ្នកត្រូវបានបដិសេធដោយ Admin។ "
                f"សូមប្រាកដថាអ្នកបានផ្ញើបង្កាន់ដៃផ្ទេរប្រាក់ត្រឹមត្រូវ ឬទាក់ទងផ្នែកគាំទ្រ។"
            )
        else:
            user_message = (
                f"❌ *Deposit Rejected*\n\n"
                f"Your deposit request has been rejected by the admin. "
                f"Please ensure you uploaded the correct proof of transfer, or contact support."
            )
        await bot.send_message(chat_id=tx.user_telegram_id, text=user_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending message to user: {e}")
        
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/approve-withdrawal/{tx_id}")
async def approve_withdrawal(tx_id: int, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    tx.status = "Approved"
    db.commit()
    
    acc = db.query(TradingAccount).filter(TradingAccount.id == tx.trading_account_id).first()
    
    # Send telegram message to user
    try:
        user = db.query(User).filter(User.telegram_id == tx.user_telegram_id).first()
        lang = user.language if (user and user.language) else "en"
        if lang == "km":
            user_message = (
                f"💸 *ការដកប្រាក់ត្រូវបានអនុម័ត!*\n\n"
                f"ការដកប្រាក់ចំនួន *${tx.amount:,.2f}* ពីគណនី *#{acc.account_number}* របស់អ្នកត្រូវបានអនុម័ត និងផ្ទេររួចរាល់ហើយ។\n"
                "សូមពិនិត្យមើលគណនីធនាគាររបស់អ្នក។"
            )
        else:
            user_message = (
                f"💸 *Withdrawal Approved!*\n\n"
                f"Your withdrawal of *${tx.amount:,.2f}* from account *#{acc.account_number}* has been approved and paid out.\n"
                "Please check your bank account."
            )
        await bot.send_message(chat_id=tx.user_telegram_id, text=user_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending message to user: {e}")
        
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/reject-withdrawal/{tx_id}")
async def reject_withdrawal(tx_id: int, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    tx.status = "Rejected"
    db.commit()
    
    # Send telegram message to user
    try:
        user = db.query(User).filter(User.telegram_id == tx.user_telegram_id).first()
        lang = user.language if (user and user.language) else "en"
        if lang == "km":
            user_message = (
                f"❌ *ការដកប្រាក់ត្រូវបានបដិសេធ*\n\n"
                f"សំណើដកប្រាក់ចំនួន *${tx.amount:,.2f}* របស់អ្នកត្រូវបានបដិសេធដោយ Admin។"
            )
        else:
            user_message = (
                f"❌ *Withdrawal Rejected*\n\n"
                f"Your withdrawal request of *${tx.amount:,.2f}* has been rejected by the admin."
            )
        await bot.send_message(chat_id=tx.user_telegram_id, text=user_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending message to user: {e}")
        
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/adjust-balance/{acc_id}")
async def adjust_balance(
    acc_id: int,
    amount: float = Form(...),
    action: str = Form(...),
    db: Session = Depends(get_db)
):
    acc = db.query(TradingAccount).filter(TradingAccount.id == acc_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
        
    if action == "add":
        acc.balance += amount
        change_text = f"+${amount:,.2f}"
    elif action == "subtract":
        acc.balance = max(0.0, acc.balance - amount)
        change_text = f"-${amount:,.2f}"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
        
    db.commit()
    
    # Notify user on Telegram
    try:
        user_message = (
            f"🔔 *Balance Adjustment Alert*\n\n"
            f"Your trading account *#{acc.account_number}* balance has been adjusted by the Admin:\n"
            f"• Change: *{change_text}*\n"
            f"• New Balance: *${acc.balance:,.2f}*"
        )
        await bot.send_message(chat_id=acc.user_telegram_id, text=user_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending message to user: {e}")
        
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/toggle-mt5-active/{acc_id}")
async def toggle_mt5_active(acc_id: int, db: Session = Depends(get_db)):
    acc = db.query(TradingAccount).filter(TradingAccount.id == acc_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    acc.mt5_active = not acc.mt5_active
    if not acc.mt5_active:
        acc.mt5_status = "Offline"
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/delete-account/{acc_id}")
async def delete_account(acc_id: int, db: Session = Depends(get_db)):
    acc = db.query(TradingAccount).filter(TradingAccount.id == acc_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
        
    acc_num = acc.account_number
    acc_type = acc.account_type
    user_id = acc.user_telegram_id
    
    # 1. Delete associated transactions first to prevent foreign key errors
    db.query(Transaction).filter(Transaction.trading_account_id == acc_id).delete()
    
    # 2. Delete the trading account
    db.delete(acc)
    db.commit()
    
    # 3. Notify user on Telegram
    try:
        user_message = (
            f"❌ *Trading Account Deleted*\n\n"
            f"Your *{acc_type} Account* (Number: `{acc_num}`) has been deleted by the Admin."
        )
        await bot.send_message(chat_id=user_id, text=user_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending deletion message to user: {e}")
        
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/approve-password-reset/{req_id}")
async def approve_password_reset(
    req_id: int,
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    req = db.query(PasswordResetRequest).filter(PasswordResetRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    acc = req.account
    acc.password = new_password
    req.status = "Completed"
    db.commit()
    
    # Send Telegram message to user with the new login details
    try:
        user = db.query(User).filter(User.telegram_id == acc.user_telegram_id).first()
        lang = user.language if (user and user.language) else "en"
        if lang == "km":
            user_message = (
                f"🔑 *ការផ្លាស់ប្តូរលេខសម្ងាត់ត្រូវបានបញ្ចប់*\n\n"
                f"សំណើសម្រាប់ *គណនី {acc.account_type} #{acc.account_number}* របស់អ្នកត្រូវបានដំណើរការរួចរាល់ហើយ។\n"
                f"ព័ត៌មានគណនីថ្មីរបស់អ្នក៖\n"
                f"• ឈ្មោះចូល: `{acc.login}`\n"
                f"• លេខសម្ងាត់ថ្មី: `{new_password}`"
            )
        else:
            user_message = (
                f"🔑 *Password Reset Completed*\n\n"
                f"Your request for *{acc.account_type} Account #{acc.account_number}* has been processed.\n"
                f"Here are your new login details:\n"
                f"• Login: `{acc.login}`\n"
                f"• New Password: `{new_password}`"
            )
        await bot.send_message(chat_id=acc.user_telegram_id, text=user_message, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending password reset message to user: {e}")
        
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/api/check-updates")
async def check_updates(db: Session = Depends(get_db)):
    reg_count = db.query(TradingAccount).filter(TradingAccount.status == "Pending").count()
    tx_count = db.query(Transaction).filter(Transaction.status == "Pending").count()
    reset_count = db.query(PasswordResetRequest).filter(PasswordResetRequest.status == "Pending").count()
    active_accounts = db.query(TradingAccount).filter(TradingAccount.status == "Approved").all()
    
    # Hash of balances and MT5 statuses to trigger client-side reloads on changes
    active_hash = hash(tuple((acc.id, acc.balance, acc.mt5_status) for acc in active_accounts))
    
    maintenance = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
    maintenance_status = "true" if (maintenance and maintenance.value == "true") else "false"
    
    return {
        "pending_registrations": reg_count,
        "pending_transactions": tx_count,
        "pending_resets": reset_count,
        "active_accounts": len(active_accounts),
        "active_hash": active_hash,
        "maintenance_mode": maintenance_status
    }


@app.get("/api/active-accounts")
async def get_active_accounts(secret: str, db: Session = Depends(get_db)):
    from database import get_setting
    from config import TELEGRAM_BOT_TOKEN
    token = get_setting("telegram_bot_token", TELEGRAM_BOT_TOKEN)
    if secret != token:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    accounts = db.query(TradingAccount).filter(
        TradingAccount.status == "Approved",
        TradingAccount.mt5_active == True
    ).all()
    
    return [
        {
            "id": acc.id,
            "account_number": acc.account_number,
            "login": acc.login,
            "password": acc.password,
            "balance": acc.balance,
            "user_telegram_id": acc.user_telegram_id
        }
        for acc in accounts
    ]


@app.post("/api/update-balance")
async def api_update_balance(
    secret: str = Form(...),
    account_id: int = Form(...),
    balance: float = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    from database import get_setting
    from config import TELEGRAM_BOT_TOKEN
    token = get_setting("telegram_bot_token", TELEGRAM_BOT_TOKEN)
    if secret != token:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    acc = db.query(TradingAccount).filter(TradingAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
        
    old_balance = acc.balance
    acc.balance = balance
    acc.mt5_status = status
    db.commit()
    
    # Notify user on Telegram if balance changed
    if abs(old_balance - balance) > 0.001:
        user = db.query(User).filter(User.telegram_id == acc.user_telegram_id).first()
        lang = user.language if (user and user.language) else "en"
        
        if lang == "km":
            alert_text = (
                f"🔔 *ដំណឹងបច្ចុប្បន្នភាពសមតុល្យ*\n\n"
                f"សមតុល្យគណនីជួញដូរ *#{acc.account_number}* របស់អ្នកបានផ្លាស់ប្តូរ៖\n"
                f"• សមតុល្យថ្មី: *${balance:,.2f}*"
            )
        else:
            alert_text = (
                f"🔔 *Balance Update Alert*\n\n"
                f"Your trading account *#{acc.account_number}* balance has changed:\n"
                f"• New Balance: *${balance:,.2f}*"
            )
        try:
            await bot.send_message(chat_id=acc.user_telegram_id, text=alert_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Error sending balance alert: {e}")
            
    return {"status": "success"}


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    try:
        get_current_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    maintenance = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
    maintenance_enabled = maintenance and maintenance.value == "true"
    
    aba_pay_link_setting = db.query(SystemSetting).filter(SystemSetting.key == "aba_pay_link").first()
    aba_pay_link = aba_pay_link_setting.value if aba_pay_link_setting else "https://link.payway.com.kh/ABAPAYMu475556i"
    
    telegram_group_id_setting = db.query(SystemSetting).filter(SystemSetting.key == "telegram_group_id").first()
    telegram_group_id = telegram_group_id_setting.value if telegram_group_id_setting else "-5536620816"
    
    telegram_bot_token_setting = db.query(SystemSetting).filter(SystemSetting.key == "telegram_bot_token").first()
    telegram_bot_token = telegram_bot_token_setting.value if telegram_bot_token_setting else ""
    
    welcome_msg_en_setting = db.query(SystemSetting).filter(SystemSetting.key == "welcome_msg_en").first()
    welcome_msg_en = welcome_msg_en_setting.value if welcome_msg_en_setting else "👋 Welcome *{name}* to our *Manual Forex Broker*!"
    
    welcome_msg_km_setting = db.query(SystemSetting).filter(SystemSetting.key == "welcome_msg_km").first()
    welcome_msg_km = welcome_msg_km_setting.value if welcome_msg_km_setting else "👋 សូមស្វាគមន៍ *{name}* មកកាន់ *Manual Forex Broker* របស់យើង!"
    
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "maintenance_enabled": maintenance_enabled,
            "aba_pay_link": aba_pay_link,
            "telegram_group_id": telegram_group_id,
            "telegram_bot_token": telegram_bot_token,
            "welcome_msg_en": welcome_msg_en,
            "welcome_msg_km": welcome_msg_km
        }
    )


@app.post("/toggle-maintenance")
async def toggle_maintenance(enabled: str = Form(...), db: Session = Depends(get_db)):
    setting = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
    if not setting:
        setting = SystemSetting(key="maintenance_mode")
        db.add(setting)
    setting.value = "true" if enabled == "true" else "false"
    db.commit()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/broadcast")
async def broadcast(
    type: str = Form(...),
    message: str = Form(...),
    db: Session = Depends(get_db)
):
    if type == "giveaway":
        formatted_message = (
            "🎁✨ *SPECIAL GIVEAWAY ALERT* ✨🎁\n\n"
            f"{message}\n\n"
            "🚀 *Best of luck trading!*"
        )
    else:
        formatted_message = (
            "📢 *OFFICIAL BROKER ANNOUNCEMENT* 📢\n\n"
            f"{message}"
        )
        
    users = db.query(User).all()
    for u in users:
        try:
            await bot.send_message(chat_id=u.telegram_id, text=formatted_message, parse_mode="Markdown")
        except Exception as e:
            print(f"Failed to send broadcast to user {u.telegram_id}: {e}")
            
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/update-settings")
async def update_settings(
    request: Request,
    aba_pay_link: str = Form(...),
    telegram_group_id: str = Form(...),
    telegram_bot_token: str = Form(...),
    welcome_msg_en: str = Form(...),
    welcome_msg_km: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        get_current_admin(request)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)

    for key, val in [
        ("aba_pay_link", aba_pay_link),
        ("telegram_group_id", telegram_group_id),
        ("telegram_bot_token", telegram_bot_token),
        ("welcome_msg_en", welcome_msg_en),
        ("welcome_msg_km", welcome_msg_km)
    ]:
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not setting:
            setting = SystemSetting(key=key)
            db.add(setting)
        setting.value = val.strip()
    db.commit()
    
    return RedirectResponse(url="/settings", status_code=303)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    telegram_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    status = Column(String, default="Pending")  # Pending, Approved
    language = Column(String, default="en")     # en, km
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    accounts = relationship("TradingAccount", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")

class TradingAccount(Base):
    __tablename__ = "trading_accounts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    account_type = Column(String, nullable=False)  # Cent, USD
    account_number = Column(String, unique=True, nullable=True)  # Filled by admin
    login = Column(String, nullable=True)          # Filled by admin
    password = Column(String, nullable=True)       # Filled by admin
    balance = Column(Float, default=0.0)
    status = Column(String, default="Pending")      # Pending, Approved
    mt5_active = Column(Boolean, default=False)
    mt5_status = Column(String, default="Offline")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    trading_account_id = Column(Integer, ForeignKey("trading_accounts.id"), nullable=False)
    type = Column(String, nullable=False)          # Deposit, Withdrawal
    amount = Column(Float, nullable=False)
    details = Column(String, nullable=True)        # Bank details / payment address for withdrawals
    receipt_path = Column(String, nullable=True)   # Image receipt path for deposits
    status = Column(String, default="Pending")     # Pending, Approved, Rejected
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="transactions")
    account = relationship("TradingAccount", back_populates="transactions")

class PasswordResetRequest(Base):
    __tablename__ = "password_reset_requests"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    trading_account_id = Column(Integer, ForeignKey("trading_accounts.id"), nullable=False)
    status = Column(String, default="Pending") # Pending, Completed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    account = relationship("TradingAccount")

class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String, primary_key=True)
    value = Column(String)

class Giveaway(Base):
    __tablename__ = "giveaways"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    message = Column(String, nullable=False)
    duration_minutes = Column(Integer, default=60)
    status = Column(String, default="Active")  # Active, Ended
    winner_telegram_id = Column(Integer, nullable=True)
    winner_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
class GiveawayParticipant(Base):
    __tablename__ = "giveaway_participants"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    giveaway_id = Column(Integer, ForeignKey("giveaways.id"), nullable=False)
    user_telegram_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    user_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AccountStock(Base):
    __tablename__ = "account_stock"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    account_number = Column(String, nullable=False, unique=True)
    login = Column(String, nullable=False)
    password = Column(String, nullable=False)
    account_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Ensure missing columns exist in tables (migration fallback)
    db = SessionLocal()
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR DEFAULT 'en'"))
        db.commit()
    except Exception:
        pass
    try:
        db.execute(text("ALTER TABLE trading_accounts ADD COLUMN mt5_active BOOLEAN DEFAULT 0"))
        db.commit()
    except Exception:
        pass
    try:
        db.execute(text("ALTER TABLE trading_accounts ADD COLUMN mt5_status VARCHAR DEFAULT 'Offline'"))
        db.commit()
    except Exception:
        pass
    finally:
        db.close()
        
    # Initialize default settings
    db = SessionLocal()
    try:
        from config import TELEGRAM_BOT_TOKEN
        
        maintenance = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
        if not maintenance:
            db.add(SystemSetting(key="maintenance_mode", value="false"))
            
        aba_link = db.query(SystemSetting).filter(SystemSetting.key == "aba_pay_link").first()
        if not aba_link:
            db.add(SystemSetting(key="aba_pay_link", value="https://link.payway.com.kh/ABAPAYMu475556i"))
            
        group_id = db.query(SystemSetting).filter(SystemSetting.key == "telegram_group_id").first()
        if not group_id:
            db.add(SystemSetting(key="telegram_group_id", value="-5536620816"))
            
        bot_token = db.query(SystemSetting).filter(SystemSetting.key == "telegram_bot_token").first()
        if not bot_token:
            db.add(SystemSetting(key="telegram_bot_token", value=TELEGRAM_BOT_TOKEN))
            
        welcome_en = db.query(SystemSetting).filter(SystemSetting.key == "welcome_msg_en").first()
        if not welcome_en:
            db.add(SystemSetting(key="welcome_msg_en", value="👋 Welcome *{name}* to our *Manual Forex Broker*!\n\nHere you can register accounts, deposit, withdraw, and check your status completely manually. Our admin team will process your requests quickly.\n\nPlease choose an option from the menu under the chat:"))
            
        welcome_km = db.query(SystemSetting).filter(SystemSetting.key == "welcome_msg_km").first()
        if not welcome_km:
            db.add(SystemSetting(key="welcome_msg_km", value="👋 សូមស្វាគមន៍ *{name}* មកកាន់ *Manual Forex Broker* របស់យើង!\n\nនៅទីនេះអ្នកអាចចុះឈ្មោះគណនី, ដាក់ប្រាក់, ដកប្រាក់ និងពិនិត្យមើលស្ថានភាពរបស់អ្នកដោយផ្ទាល់។ ក្រុមការងាររបស់យើងនឹងដំណើរការសំណើរបស់អ្នកយ៉ាងរហ័ស។\n\nសូមជ្រើសរើសជម្រើសពីម៉ឺនុយខាងក្រោម:"))
            
        db.commit()
    except Exception:
        pass
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_setting(key: str, default: str = "") -> str:
    db = SessionLocal()
    try:
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting:
            return setting.value
    except Exception:
        pass
    finally:
        db.close()
    return default

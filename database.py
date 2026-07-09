import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
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

def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Initialize default settings
    db = SessionLocal()
    try:
        maintenance = db.query(SystemSetting).filter(SystemSetting.key == "maintenance_mode").first()
        if not maintenance:
            db.add(SystemSetting(key="maintenance_mode", value="false"))
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

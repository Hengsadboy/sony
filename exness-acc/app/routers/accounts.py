from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from app.database import get_db, MT5Account
from app.config import settings
from app.security import encrypt_password, decrypt_password
from app.services.mt5_service import mt5_service
from app.utils.logger import get_logger

logger = get_logger("AccountsRouter")
router = APIRouter(prefix="/accounts", tags=["accounts"])

# Security Dependency
async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.API_KEY:
        logger.warning(f"Unauthorized access attempt with API Key: {x_api_key}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )

# Pydantic Schemas
class AccountRegisterRequest(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the user (from telegram or website)")
    login: int = Field(..., description="MT5 account number")
    password: str = Field(..., description="MT5 account password")
    server: str = Field(..., description="MT5 server name (e.g. Exness-MT5Real1)")

class AccountLoginRequest(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the user")
    login: int = Field(..., description="MT5 account number")
    password: str = Field(..., description="MT5 account password")
    server: str = Field(..., description="MT5 server name")

# Endpoints
@router.post("/register", dependencies=[Depends(verify_api_key)])
async def register_account(payload: AccountRegisterRequest, db: Session = Depends(get_db)):
    """Saves and encrypts the MT5 account credentials in database."""
    # Check if the login is already registered
    existing_account = db.query(MT5Account).filter(MT5Account.login == payload.login).first()
    if existing_account:
        # If user_id is different, block or update. Let's update credentials.
        if existing_account.user_id != payload.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This MT5 account login is already registered to a different user."
            )
        
        # Update credentials
        existing_account.encrypted_password = encrypt_password(payload.password)
        existing_account.server = payload.server
        db.commit()
        logger.info(f"Updated credentials for registered account {payload.login} for user {payload.user_id}")
        return {"status": "success", "message": "Credentials updated successfully"}

    # Create new account credentials entry
    encrypted_pw = encrypt_password(payload.password)
    new_account = MT5Account(
        user_id=payload.user_id,
        login=payload.login,
        encrypted_password=encrypted_pw,
        server=payload.server
    )
    db.add(new_account)
    db.commit()
    logger.info(f"Registered new MT5 account {payload.login} for user {payload.user_id}")
    return {"status": "success", "message": "Account credentials registered and secured"}

@router.post("/login", dependencies=[Depends(verify_api_key)])
async def login_account(payload: AccountLoginRequest):
    """Verifies credentials by attempting live authentication check with MT5."""
    try:
        logger.info(f"Checking login authorization for account {payload.login} on {payload.server}")
        result = await mt5_service.check_credentials(
            login=payload.login,
            password=payload.password,
            server=payload.server
        )
        if not result.get("authenticated"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=result.get("error", "Authentication failed")
            )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Login endpoint error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during authentication: {str(e)}"
        )

@router.get("/{user_id}/balance", dependencies=[Depends(verify_api_key)])
async def get_account_balance(user_id: str, db: Session = Depends(get_db)):
    """Fetches balance from MT5 for the user's registered account."""
    # Find registered account for user_id
    account = db.query(MT5Account).filter(MT5Account.user_id == user_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No registered account found for this user."
        )

    # Decrypt password
    try:
        password = decrypt_password(account.encrypted_password)
    except Exception as e:
        logger.error(f"Failed to decrypt password for account {account.login}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database decyption error. Please re-register your credentials."
        )

    try:
        # Fetch balance details
        balance_info = await mt5_service.get_balance(
            login=account.login,
            password=password,
            server=account.server
        )
        return {"status": "success", "data": balance_info}
    except Exception as e:
        logger.error(f"Failed to check balance for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve balance from MT5: {str(e)}"
        )

@router.get("/list", dependencies=[Depends(verify_api_key)])
async def list_accounts(db: Session = Depends(get_db)):
    """Lists all registered accounts (excluding credentials)."""
    accounts = db.query(MT5Account).all()
    return {
        "status": "success",
        "accounts": [
            {
                "user_id": acc.user_id,
                "login": acc.login,
                "server": acc.server,
                "created_at": acc.created_at.isoformat() if acc.created_at else None
            }
            for acc in accounts
        ]
    }

@router.delete("/{login}", dependencies=[Depends(verify_api_key)])
async def delete_account(login: int, db: Session = Depends(get_db)):
    """Deletes MT5 account credentials from the database."""
    account = db.query(MT5Account).filter(MT5Account.login == login).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found."
        )
    db.delete(account)
    db.commit()
    logger.info(f"Deleted MT5 account {login} from database.")
    return {"status": "success", "message": f"Account {login} deleted successfully."}

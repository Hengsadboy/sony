from cryptography.fernet import Fernet
from app.config import settings

# Initialize Fernet key if provided, otherwise default to a mock key for development
ENCRYPTION_KEY = settings.ENCRYPTION_KEY.encode() if settings.ENCRYPTION_KEY else Fernet.generate_key()
fernet = Fernet(ENCRYPTION_KEY)

def encrypt_password(password: str) -> str:
    """Encrypts a plaintext password string into an encrypted string."""
    if not password:
        return ""
    return fernet.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password: str) -> str:
    """Decrypts an encrypted password string back into plaintext."""
    if not encrypted_password:
        return ""
    return fernet.decrypt(encrypted_password.encode()).decode()

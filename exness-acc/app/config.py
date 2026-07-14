import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # App Settings
    API_KEY: str = Field(default="dev-key-replace-in-production")
    ENCRYPTION_KEY: str = Field(default="")
    DATABASE_URL: str = Field(default="sqlite:///./exness_service.db")
    
    # MT5 Terminal Settings
    MT5_MOCK_MODE: bool = Field(default=True)
    MT5_TERMINAL_PATH: str = Field(default="")

    # Configuration for loading from .env file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Check and validate encryption key if not in mock mode or if key is provided
if settings.ENCRYPTION_KEY:
    try:
        from cryptography.fernet import Fernet
        # Test if valid key
        Fernet(settings.ENCRYPTION_KEY.encode())
    except Exception as e:
        raise ValueError(f"Invalid ENCRYPTION_KEY: {e}. It must be a valid 32-byte base64-encoded key.")
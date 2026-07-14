import asyncio
from typing import Dict, Any, Optional
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger("MT5Service")

class MT5Service:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.initialized = False
        self.current_login: Optional[int] = None
        self._mt5 = None

    def _import_mt5(self):
        """Dynamically imports MetaTrader5 to allow mock testing on non-Windows systems."""
        if self._mt5 is not None:
            return self._mt5
        
        if settings.MT5_MOCK_MODE:
            return None
            
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
            return self._mt5
        except ImportError as e:
            logger.error("MetaTrader5 package is not installed. Required for real mode.")
            raise e

    async def initialize_terminal(self) -> bool:
        """Initializes connection to the MT5 terminal program."""
        if settings.MT5_MOCK_MODE:
            self.initialized = True
            logger.info("MT5 Service initialized in MOCK MODE.")
            return True

        mt5 = self._import_mt5()
        if self.initialized:
            return True

        # Check if terminal path is specified
        init_kwargs = {}
        if settings.MT5_TERMINAL_PATH:
            init_kwargs["path"] = settings.MT5_TERMINAL_PATH

        # Initialize connection
        success = mt5.initialize(**init_kwargs)
        if success:
            self.initialized = True
            logger.info("MT5 Terminal initialized successfully.")
        else:
            logger.error(f"Failed to initialize MT5 Terminal. Error code: {mt5.last_error()}")
        return success

    async def shutdown(self):
        """Closes the connection to the MT5 terminal."""
        if settings.MT5_MOCK_MODE:
            self.initialized = False
            return

        mt5 = self._import_mt5()
        if self.initialized:
            mt5.shutdown()
            self.initialized = False
            self.current_login = None
            logger.info("MT5 Terminal shutdown.")

    async def login(self, login: int, password: str, server: str) -> bool:
        """Switch to and log in with specific MT5 credentials."""
        await self.initialize_terminal()

        if settings.MT5_MOCK_MODE:
            self.current_login = login
            logger.info(f"[MOCK] Successfully logged into account {login} on server {server}")
            return True

        mt5 = self._import_mt5()
        
        # If already logged in, skip login
        if self.current_login == login:
            return True

        # Perform account login
        success = mt5.login(login=login, password=password, server=server)
        if success:
            self.current_login = login
            logger.info(f"Successfully logged into MT5 account {login} on server {server}")
        else:
            logger.error(f"Failed to log into MT5 account {login} on server {server}. Error: {mt5.last_error()}")
        return success

    async def check_credentials(self, login: int, password: str, server: str) -> Dict[str, Any]:
        """Validates if the credentials are valid by attempting login and getting account info."""
        async with self.lock:
            success = await self.login(login, password, server)
            if not success:
                return {"authenticated": False, "error": "Invalid credentials or connection timeout"}
            
            if settings.MT5_MOCK_MODE:
                return {
                    "authenticated": True,
                    "name": "Mock User",
                    "balance": 10000.0,
                    "server": server,
                    "currency": "USD"
                }

            mt5 = self._import_mt5()
            account_info = mt5.account_info()
            if account_info is None:
                return {"authenticated": False, "error": f"Failed to retrieve account info: {mt5.last_error()}"}
            
            return {
                "authenticated": True,
                "name": account_info.name,
                "balance": account_info.balance,
                "server": account_info.server,
                "currency": account_info.currency
            }

    async def get_balance(self, login: int, password: str, server: str) -> Dict[str, Any]:
        """Thread-safe method to check account balance details."""
        async with self.lock:
            # Re-verify/Login dynamically
            success = await self.login(login, password, server)
            if not success:
                raise ValueError("Authentication with MetaTrader 5 server failed.")

            if settings.MT5_MOCK_MODE:
                return {
                    "balance": 10000.0,
                    "equity": 10050.0,
                    "margin": 200.0,
                    "free_margin": 9850.0,
                    "currency": "USD"
                }

            mt5 = self._import_mt5()
            account_info = mt5.account_info()
            if account_info is None:
                raise ValueError(f"Failed to retrieve account info: {mt5.last_error()}")

            return {
                "balance": account_info.balance,
                "equity": account_info.equity,
                "margin": account_info.margin,
                "free_margin": account_info.margin_free,
                "currency": account_info.currency
            }

mt5_service = MT5Service()

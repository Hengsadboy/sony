from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager
from pathlib import Path

from app.database import init_db
from app.routers import accounts
from app.services.mt5_service import mt5_service
from app.utils.logger import get_logger

logger = get_logger("Main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting Exness MT5 Service API...")
    init_db()
    
    # Initialize the MT5 terminal connection
    success = await mt5_service.initialize_terminal()
    if not success:
        logger.warning("MT5 Terminal could not be initialized during startup. Operations will retry dynamically.")
        
    yield
    
    # Shutdown actions
    logger.info("Stopping Exness MT5 Service API...")
    await mt5_service.shutdown()

app = FastAPI(
    title="Exness MT5 Service Layer API",
    description="Dedicated service layer for Exness/MT5 operations with dynamic account switching",
    version="1.0.0",
    lifespan=lifespan
)

# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception occurred on path {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error occurred."}
    )

# Include routers
app.include_router(accounts.router, prefix="/api/v1")

@app.get("/")
async def serve_admin_panel():
    """Serves the main admin panel dashboard."""
    static_file_path = Path("app/static/index.html")
    if not static_file_path.exists():
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Admin Panel static files not found."}
        )
    return FileResponse(static_file_path)

@app.get("/health")
async def health_check():
    """Service health status endpoint."""
    return {
        "status": "healthy",
        "mt5_initialized": mt5_service.initialized,
        "mock_mode": mt5_service.current_login is not None or mt5_service.initialized
    }

import threading
import time
import uvicorn
from bot import run_bot
from admin_panel import app

def start_web_server():
    import os
    port = int(os.environ.get("PORT", 8000))
    print(f"[SYSTEM] Starting FastAPI Admin Panel on http://0.0.0.0:{port} ...")
    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except Exception as e:
        print(f"[SYSTEM ERROR] FastAPI Server failed: {e}")

if __name__ == "__main__":
    # Start FastAPI Web Server in a daemon thread
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    # Give the web server a moment to start
    time.sleep(2)
    
    # Start Telegram Bot in the main thread (blocking, handles event loops and signals properly)
    print("[SYSTEM] Starting Telegram Bot in main thread...")
    try:
        run_bot()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[SYSTEM ERROR] Telegram Bot failed: {e}")



"""
Main entry point for detect_qr_cccd application.
Runs FastAPI server + Celery worker in background.
Can run as: python run.py (dev) or through built exe.
"""
import os
import datetime
from threading import Thread

# ============================================================================
# Configure Redis URL BEFORE importing modules (they read env vars on import)
# ============================================================================
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_DB = os.getenv("REDIS_DB", "10")
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
os.environ["REDIS_URL"] = REDIS_URL


import uvicorn
from celery_app import celery
from service import app as fastapi_app


# ============================================================================
# Configuration - Modify these for different environments
# ============================================================================

# Server configuration
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")  # "0.0.0.0" for remote access
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

# Logging configuration
LOGGING_DIR = os.getenv("LOGGING_DIR", "./logs")
LOG_LEVEL_DEV = "info"
LOG_LEVEL_PROD = "error"

# ============================================================================
# Celery configuration
# ============================================================================

def start_celery_worker_development():
    """
    Start Celery worker in development mode.
    Logs to .temp/ folder with INFO level.
    """
    import datetime
    from logger import get_log_dir

    print(f"[Celery] Starting worker (Development mode)")
    print(f"[Redis] {REDIS_URL}")

    log_dir = get_log_dir()
    now = datetime.datetime.now()
    date_str = now.strftime('%Y%m%d')
    log_file = f"{log_dir}/celery_{date_str}.log"

    celery.worker_main(
        argv=[
            "worker",
            "-l", LOG_LEVEL_DEV,
            "-P", "threads",  # Use threads pool for lighter footprint
            f"--logfile={log_file}",
        ]
    )


def start_celery_worker_production():
    """
    Start Celery worker in production mode.
    Logs to file with ERROR level only.
    """
    print(f"🔄 Starting Celery worker (Production mode)")
    print(f"📍 Redis: {REDIS_URL}")

    # Create logs directory if it doesn't exist
    os.makedirs(LOGGING_DIR, exist_ok=True)

    now = datetime.datetime.now()
    date_str = now.strftime('%Y%m%d')
    log_file = os.path.join(LOGGING_DIR, f"celery_{date_str}.log")

    celery.worker_main(
        argv=[
            "worker",
            "-l", LOG_LEVEL_PROD,
            "-P", "threads",
            f"--logfile={log_file}"
        ]
    )


def start_development_env():
    """
    Development mode: FastAPI server + Celery worker in background.
    Server listens on 127.0.0.1:8000 with hot reload.
    Logs to console and .temp/YYYY-MM-DD.txt
    """
    print("\n" + "="*60)
    print("[DEV] Starting CCCD QR Detector (Development Mode)")
    print("="*60)
    print(f"Server: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"Redis: {REDIS_URL}")
    print("="*60 + "\n")

    # Start Celery worker in background thread (daemon, won't block shutdown)
    celery_thread = Thread(target=start_celery_worker_development, daemon=True)
    celery_thread.start()

    # Give Celery time to connect to Redis
    import time
    time.sleep(2)

    print("[FastAPI] Server starting...\n")

    # Start FastAPI server in main thread (blocking)
    # Note: reload=False because we import the app object directly
    # For hot reload, use: uvicorn run.py:fastapi_app --reload
    # Uvicorn logs will use root logger (DailyTextHandler) via propagation
    uvicorn.run(
        fastapi_app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level=LOG_LEVEL_DEV.lower()
    )


def start_production_env():
    """
    Production mode: FastAPI server + Celery worker in background.
    Server listens on 0.0.0.0 for remote access.
    Logs to .temp/YYYY-MM-DD.txt and optionally to LOGGING_DIR (legacy).
    """
    print("\n" + "="*60)
    print("[PROD] Starting CCCD QR Detector (Production Mode)")
    print("="*60)
    print(f"Server: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"Redis: {REDIS_URL}")
    print(f"Logs: {LOGGING_DIR}")
    print("="*60 + "\n")

    # Create logs directory if it doesn't exist
    os.makedirs(LOGGING_DIR, exist_ok=True)

    # Start Celery worker in background thread
    celery_thread = Thread(target=start_celery_worker_production, daemon=True)
    celery_thread.start()

    # Give Celery time to start
    import time
    time.sleep(2)

    # Start FastAPI server with Uvicorn
    # Uvicorn logs will use root logger (DailyTextHandler) via propagation
    uvicorn.run(
        fastapi_app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level=LOG_LEVEL_PROD.lower()
    )

    celery_thread.join()


if __name__ == "__main__":
    """
    Main entry point.

    Environment modes:
    - Development: python run.py (or set ENV=dev)
    - Production: set ENV=prod && python run.py

    Configuration via environment variables:
    - SERVER_HOST (default: 127.0.0.1, use 0.0.0.0 for remote)
    - SERVER_PORT (default: 8000)
    - REDIS_HOST (default: localhost)
    - REDIS_PORT (default: 6379)
    - REDIS_DB (default: 10, range: 10-15) ⚠️ Use DB 10-15 to avoid conflicts
    - LOGGING_DIR (default: ./logs)
    - ENV (dev or prod, default: dev)

    Examples:
    # Development (default)
    python run.py

    # Production
    ENV=prod python run.py

    # Custom Redis server
    REDIS_HOST=192.168.1.100 REDIS_DB=2 python run.py

    # Remote access with custom port
    SERVER_HOST=0.0.0.0 SERVER_PORT=5000 python run.py
    """

    env = os.getenv("ENV", "dev").lower()

    if env == "prod":
        start_production_env()
    else:
        start_development_env()

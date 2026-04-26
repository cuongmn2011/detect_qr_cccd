# CCCD QR Code Detector - Claude Code Documentation

## Project Overview

**detectQRCCCD** is a FastAPI service that detects and decodes QR codes from Vietnamese CCCD (Citizen ID Cards) images. It uses:
- **FastAPI** for HTTP gateway
- **Celery + Redis** for async task processing
- **OpenCV + zxingcpp** for QR detection
- **WeChat QRCode** for deep learning-based detection

Supports 100+ concurrent users without blocking.

---

## Project Structure

```
detect_qr_cccd/
├── run.py                 # Main entry point (dev/prod modes)
├── service.py             # FastAPI endpoints & HTTP handlers
├── tasks.py               # Celery task definitions
├── main.py                # Core QR detection & CCCD parsing logic
├── celery_app.py          # Celery app configuration
├── requirements.txt       # Python dependencies
├── detect_qr_cccd.spec    # PyInstaller configuration
│
├── .temp/                 # Runtime logs (created automatically)
│   ├── celery_20260426.log
│   ├── celery_20260427.log
│   └── ...
│
├── .claude/               # Claude Code documentation & plans
├── web/                   # Web UI (HTML/CSS/JS)
├── asset/                 # Test images for development
└── README.md              # User-facing documentation
```

---

## How It Works

### 1. **FastAPI Service** (service.py)
- `/health` - Health check endpoint
- `/` - Web UI
- `/decode/file` - Upload image, detect QR code
- `/decode/path` - Detect QR from file path
- `/current-detect-image/{request_id}` - Get preview image

### 2. **Celery Worker** (tasks.py)
- `detect_qr_task` - Async task that:
  1. Loads image from Redis
  2. Calls `detect_cccd_from_image()` from main.py
  3. Returns detection result as dict

### 3. **QR Detection Logic** (main.py)
- **Strategy 1**: Try WeChat QRCode (ML-based, handles distortion)
- **Strategy 2**: Fallback to region-based detection with zxingcpp
  - Extract QR candidates from image
  - Preprocess variants (CLAHE, Gaussian, Otsu, etc.)
  - Parallel decode with early-exit
- **CCCD Field Parsing**: Extract 12 fields from QR payload

---

## Error Handling & Logging

### Error Handling Strategy

All exceptions are caught and handled gracefully:

| Scenario | Handling |
|----------|----------|
| Corrupted image | Return 400 Bad Request with error detail |
| Redis unavailable | Return 500 Service Unavailable |
| Celery broker down | Return 500 Service Unavailable |
| Invalid QR result | Validate dict + return 500 if invalid |
| Processing crash | Graceful fallback, return "detected: false" |

**Key principle**: Never crash the API, always return valid HTTP responses.

### Logging System

- **All logs** go to single file: `.temp/celery_YYYYMMDD.log`
- **Log sources**: FastAPI, Celery worker, Application code
- **Format**: `[timestamp: LEVEL/Process] logger_name | message + traceback`
- **Daily rotation**: Automatic file switch at midnight

See [ERROR_HANDLING.md](.claude/ERROR_HANDLING.md) for detailed error handling approach.

See [LOGGING_SYSTEM.md](.claude/LOGGING_SYSTEM.md) for logging architecture.

---

## Running the Application

### Development Mode (Local Testing)
```bash
python run.py
# Server: http://127.0.0.1:8000
# Logs: .temp/celery_YYYYMMDD.log
```

### Production Mode
```bash
ENV=prod python run.py
# Server: http://0.0.0.0:8000 (allows remote access)
# Logs: .temp/celery_YYYYMMDD.log
```

### Docker Compose
```bash
docker compose up -d --build
# Includes Redis, Celery worker, FastAPI service
```

### Windows EXE
```bash
pyinstaller detect_qr_cccd.spec
dist/detect_qr_cccd/detect_qr_cccd.exe
# Creates .temp folder next to exe
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SERVER_HOST` | `127.0.0.1` | FastAPI bind address |
| `SERVER_PORT` | `8000` | FastAPI port |
| `REDIS_HOST` | `localhost` | Redis server address |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `10` | Redis database (10-15 to avoid conflicts) |
| `ENV` | `dev` | `dev` or `prod` mode |

---

## Key Decisions

### 1. Single Log File Architecture
- **Why**: Simpler than multiple files, easier to debug
- **How**: Celery captures all Python logging → writes to celery_YYYYMMDD.log
- **Benefits**: All logs in one place, automatic daily rotation

### 2. Redis + Celery for Async Processing
- **Why**: Supports 100+ concurrent users without blocking
- **How**: FastAPI queues task → Celery worker processes → Redis stores results
- **Benefits**: Scalable, can add more workers easily

### 3. Strategy 1 + Strategy 2 Detection
- **Why**: ML (WeChat) handles distortion, zxingcpp is reliable fallback
- **How**: Try WeChat first, fallback to region-based if fails
- **Benefits**: High accuracy on distorted images, fast processing

### 4. Graceful Error Handling
- **Why**: Never crash, always respond with valid HTTP
- **How**: Wrap all critical sections in try-catch
- **Benefits**: Robust production-ready service

---

## Monitoring & Debugging

### View Logs
```bash
# Windows
type .temp\celery_20260426.log

# Linux/Mac
tail -f .temp/celery_20260426.log

# Search for errors
grep ERROR .temp/celery_20260426.log
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Redis connection error | Check Redis is running: `redis-cli ping` |
| Task timeout (60s) | Reduce image size or add more workers |
| Port 8000 already in use | Change `SERVER_PORT=8001` and retry |
| Image not detected | Check image quality, try debug mode |

### Debug Mode (Save variant images)
```python
from main import detect_cccd_from_image
import cv2

img = cv2.imread('test.jpg')
result = detect_cccd_from_image(img, debug_dir='./debug_output/')
# Creates debug_output/region_variant.jpg for each preprocessing step
```

---

## Performance Metrics

- **Single image**: 2-5 seconds (depends on quality)
- **Concurrent users**: 100+ supported
- **QR detection accuracy**: 37.5% baseline (improved with WeChat)
- **Memory per worker**: ~100-150 MB

---

## Recent Changes (v1.0.1)

### 2026-04-26
- ✅ **Added comprehensive error handling** across all endpoints
- ✅ **Replaced all print() statements** with proper logging
- ✅ **Validates task results** before using
- ✅ **Redis error handling** with graceful fallback
- ✅ **Fixed bare except blocks** in main.py

See git log for full history:
```bash
git log --oneline | head -10
```

---

## Contacts & Resources

- **Documentation**: See [README.md](README.md)
- **API Docs**: http://localhost:8000/docs (when running)
- **Plans**: See [.claude/](`.claude/`) folder
- **Test Images**: `asset/` folder

---

## Notes for Future Development

1. **Caching**: Consider caching CLAHE preprocessing results
2. **Scaling**: Add more Celery workers: `docker compose up -d --scale detectqrcccd-worker=3`
3. **Monitoring**: Add Prometheus metrics for production
4. **Database**: Store results in PostgreSQL for audit trail
5. **Auth**: Add API key authentication for production

# Logging System Architecture

## Overview

The detect_qr_cccd service implements a **single unified logging system** where all logs (FastAPI, Celery worker, application code) are captured and written to **one file per day**.

---

## Architecture

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                   Application Startup (run.py)                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
        ┌────────────────┴────────────────┐
        │                                 │
        ▼                                 ▼
   ┌─────────────┐              ┌─────────────────┐
   │  FastAPI    │              │  Celery Worker  │
   │  Server     │              │  (Background)   │
   │ :8000       │              │  (Thread Pool)  │
   └──────┬──────┘              └────────┬────────┘
          │                               │
          │  logger.info()                │  logger.error()
          │  logger.error()               │  logger.debug()
          │                               │
          └───────────────┬───────────────┘
                          │
                          ▼
            ┌──────────────────────────┐
            │  Python logging module   │
            │  getLogger('service')    │
            │  getLogger('tasks')      │
            │  getLogger('main')       │
            └───────────┬──────────────┘
                        │
                        ▼
            ┌──────────────────────────┐
            │  Celery logging hijack   │
            │  (worker_main runs)      │
            └───────────┬──────────────┘
                        │
                        ▼
            ┌──────────────────────────┐
            │  Celery --logfile=...    │
            │  parameter writes to:    │
            │  .temp/celery_YYYYMMDD   │
            │           .log           │
            └──────────────────────────┘
```

---

## Configuration

### Logging Module Setup

**run.py** (Celery configuration):
```python
# Celery automatically captures ALL Python logging
celery.worker_main(
    argv=[
        "worker",
        "-l", LOG_LEVEL,
        "-P", "threads",
        f"--logfile={log_file}",  # ← Writes all logs here
    ]
)
```

**service.py, tasks.py, main.py** (Application loggers):
```python
import logging

# Each module creates its own logger
logger = logging.getLogger('service')     # or 'tasks', 'main'

# All logs via these loggers get captured by Celery
logger.info("Request received")
logger.error("Database error", exc_info=True)
logger.debug("Processing step 5")
```

### Log File Location

**Development Mode**:
```
detect_qr_cccd/
└── .temp/
    ├── celery_20260426.log  (created automatically)
    ├── celery_20260427.log  (created next day)
    └── ...
```

**Production Mode (PyInstaller EXE)**:
```
C:\Program Files\detect_qr_cccd\
├── detect_qr_cccd.exe
└── .temp/
    ├── celery_20260426.log
    └── ...
```

Path detection in [run.py](../run.py):
```python
if getattr(sys, 'frozen', False):
    # Running as exe
    base_dir = os.path.dirname(sys.executable)
else:
    # Running as .py
    base_dir = os.path.dirname(os.path.abspath(__file__))

log_dir = os.path.join(base_dir, '.temp')
os.makedirs(log_dir, exist_ok=True)
```

---

## Log Format

### Celery Format

```
[2026-04-26 22:25:33,091: INFO/MainProcess] POST /decode/file | file=test.jpg | size=256K
[2026-04-26 22:25:34,102: ERROR/MainProcess] Task failed: Redis unavailable
```

**Breakdown**:
- `2026-04-26 22:25:33,091` - Timestamp (date, time, milliseconds)
- `INFO` - Log level
- `MainProcess` - Celery process name
- `POST /decode/file | ...` - Logger message

### Standard Python Logging Format

Each application logger produces:
```
[%(asctime)s: %(levelname)s/%(processName)s] %(name)s | %(message)s
```

Where:
- `%(asctime)s` - ISO format timestamp
- `%(levelname)s` - DEBUG, INFO, WARNING, ERROR, CRITICAL
- `%(processName)s` - MainProcess, Worker-1, etc.
- `%(name)s` - Logger name (service, tasks, main)
- `%(message)s` - Actual log message

---

## Log Samples

### Successful Image Upload

```
[2026-04-26 22:25:33,091: INFO/MainProcess] POST /decode/file | file=CCCD_5.jpg | size=335214 bytes | request_id=abc-123
[2026-04-26 22:25:33,102: INFO/MainProcess] [detect_qr] task started | image_key=img:abc-123
[2026-04-26 22:25:35,234: DEBUG/MainProcess] Deskew rotation: 15.32 degrees
[2026-04-26 22:25:40,456: DEBUG/MainProcess] Loaded image: /path/to/image | shape=(1080, 1920, 3)
[2026-04-26 22:25:45,123: DEBUG/MainProcess] Preprocessing variant for qr_focused: clahe_3x success
[2026-04-26 22:25:47,501: INFO/MainProcess] [detect_qr] task completed | detected=True | duration=14.40s | region=qr_focused_region_0
```

### Failed Image Upload

```
[2026-04-26 22:26:10,123: INFO/MainProcess] POST /decode/file | file=invalid.jpg | size=1234 bytes | request_id=def-456
[2026-04-26 22:26:10,234: INFO/MainProcess] [detect_qr] task started | image_key=img:def-456
[2026-04-26 22:26:10,345: ERROR/MainProcess] Cannot process image: cannot identify image file <_io.BytesIO object at 0x...>
Traceback (most recent call last):
  File "tasks.py", line 42, in detect_qr_task
    pil_img = Image.open(BytesIO(raw)).convert("RGB")
  File "/env/lib/PIL/Image.py", line 3092, in open
    raise UnidentifiedImageError(...)
PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object at 0x...>

[2026-04-26 22:26:10,456: INFO/MainProcess] [detect_qr] task failed | image_key=img:def-456 | error=Invalid image format: ... | duration=0.23s
```

### Redis Unavailable

```
[2026-04-26 22:27:01,123: INFO/MainProcess] POST /decode/file | file=test.jpg | size=256K | request_id=ghi-789
[2026-04-26 22:27:01,234: ERROR/MainProcess] Failed to save image to Redis: [Errno 10049] The requested address is not valid in its context
[2026-04-26 22:27:01,345: INFO/MainProcess] [ERROR] Server error: failed to process request
```

---

## Daily Log Rotation

### How It Works

Celery's `--logfile` parameter automatically creates a new file each time the worker starts:

```python
# run.py
now = datetime.datetime.now()
date_str = now.strftime('%Y%m%d')  # YYYYMMDD format
log_file = f"{log_dir}/celery_{date_str}.log"

# Each day, a new log_file path is created
# 2026-04-26 → celery_20260426.log
# 2026-04-27 → celery_20260427.log
# ... etc
```

### Log Files Accumulate

Old log files are **NOT deleted**:
```
.temp/
├── celery_20260421.log  (2 weeks old - 2.5 MB)
├── celery_20260422.log  (2 weeks old - 1.8 MB)
├── celery_20260423.log  (2 weeks old - 3.2 MB)
├── celery_20260424.log  (1 week old - 2.1 MB)
├── celery_20260425.log  (2 days old - 4.5 MB)
├── celery_20260426.log  (today - 2.3 MB)
└── celery_20260427.log  (tomorrow, when service restarts)
```

### Disk Space Management

On production, you may need to clean up old logs:

```bash
# Delete logs older than 30 days
find .temp/ -name "celery_*.log" -mtime +30 -delete

# Archive logs to compressed file
tar -czf .temp/logs_archive_202604.tar.gz .temp/celery_2604*.log
```

---

## Viewing Logs

### Windows

**Real-time viewing**:
```bash
# PowerShell - follow new lines
Get-Content -Path .\.temp\celery_20260426.log -Wait

# CMD - last 50 lines
type .temp\celery_20260426.log | tail -50
```

**Search logs**:
```bash
# Find all errors
findstr "ERROR" .temp\celery_20260426.log

# Find specific request
findstr "request_id=abc-123" .temp\celery_20260426.log
```

### Linux / Mac

**Real-time viewing**:
```bash
tail -f .temp/celery_20260426.log
```

**Search logs**:
```bash
# Find all errors
grep ERROR .temp/celery_20260426.log

# Find specific request
grep request_id=abc-123 .temp/celery_20260426.log

# Count errors by type
grep ERROR .temp/celery_20260426.log | sort | uniq -c
```

---

## Log Levels Explained

### DEBUG
- Detailed execution information
- Used for development and troubleshooting
- Examples: deskew angle, preprocessing variants, image shapes

```
[2026-04-26 22:25:35,234: DEBUG/MainProcess] Deskew rotation: 15.32 degrees
[2026-04-26 22:25:40,456: DEBUG/MainProcess] Loaded image: /path | shape=(1080, 1920, 3)
```

### INFO
- Key events and milestones
- Used for production monitoring
- Examples: request received, task started, task completed

```
[2026-04-26 22:25:33,091: INFO/MainProcess] POST /decode/file | request_id=abc-123
[2026-04-26 22:25:47,501: INFO/MainProcess] [detect_qr] task completed | detected=True | duration=14.40s
```

### WARNING
- Non-fatal issues that should be investigated
- Service continues to operate
- Examples: WeChat QRCode failed, preprocessing skipped

```
[2026-04-26 22:25:40,456: WARNING/MainProcess] WeChat QRCode detection failed: could not find detector
[2026-04-26 22:25:45,789: WARNING/MainProcess] Failed to save preview to Redis: connection timeout
```

### ERROR
- Fatal errors that need immediate attention
- Service may be degraded but still responding
- Examples: Redis unavailable, corrupted image, task failed

```
[2026-04-26 22:26:10,234: ERROR/MainProcess] Cannot process image: cannot identify image file
[2026-04-26 22:27:01,234: ERROR/MainProcess] Failed to save image to Redis: connection refused
```

### CRITICAL
- System-level failures
- Usually requires manual intervention
- Examples: Out of memory, disk full, Celery broker down

---

## Performance Impact

### Logging Overhead

- **File I/O**: ~1-2ms per log line
- **Timestamp formatting**: <0.5ms per call
- **String formatting**: <1ms for normal messages
- **Total impact**: <5% latency increase

### Disk Space

- **Per image**: 2-5 KB of log data
- **Per 1000 images**: 2-5 MB
- **Per day (100 requests)**: 200-500 KB

---

## Troubleshooting

### Logs Not Being Written

1. **Check .temp folder exists**:
   ```bash
   ls -la .temp/  # Linux/Mac
   dir .temp\     # Windows
   ```

2. **Check permissions**:
   ```bash
   chmod 755 .temp/  # Allow write access
   ```

3. **Check Celery is running**:
   ```bash
   ps aux | grep celery
   ```

### Logs Growing Too Fast

1. **Check for infinite loops**: Search for repeated error messages
   ```bash
   grep ERROR .temp/celery_*.log | sort | uniq -c | sort -rn
   ```

2. **Archive old logs**:
   ```bash
   tar -czf .temp/logs_old.tar.gz .temp/celery_2604*.log
   ```

### Cannot Find Specific Error

1. **Search across all dates**:
   ```bash
   grep -r "specific error text" .temp/
   ```

2. **Check with request_id**:
   ```bash
   grep request_id=YOUR_ID_HERE .temp/celery_*.log
   ```

---

## Related Documentation

- [ERROR_HANDLING.md](ERROR_HANDLING.md) - Error handling strategy
- [../README.md](../README.md) - User documentation
- [../run.py](../run.py) - Log file initialization
- [../service.py](../service.py) - HTTP endpoint logging
- [../tasks.py](../tasks.py) - Celery task logging
- [../main.py](../main.py) - Core logic logging

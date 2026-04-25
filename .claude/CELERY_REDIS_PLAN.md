# Plan: Refactor sang Celery + Redis Architecture

## Context
Hiện tại `service.py` gọi `detect_cccd_from_image()` trực tiếp trong HTTP request cycle → block khi có nhiều requests đồng thời. Mục tiêu: FastAPI chỉ làm HTTP gateway, đẩy task vào Redis queue, Celery worker xử lý ngầm.

---

## Kiến Trúc Mới

```
Client
  │
  ▼ HTTP POST /decode/file
FastAPI (service.py)
  │  ① Lưu image bytes vào Redis với temp key (UUID)
  │  ② Submit Celery task(image_key) → Redis Queue
  │  ③ await task.get(timeout=60) [asyncio.to_thread]
  │
  ▼ Celery Worker (tasks.py)
  │  ① Đọc image bytes từ Redis key
  │  ② Xóa temp key (cleanup)
  │  ③ detect_cccd_from_image(img)
  │  ④ Store result trong Celery backend (Redis)
  │
  ▼ HTTP Response trả về client
```

**Vì sao lưu image vào Redis thay vì truyền qua task args?**
- Task args đi qua Celery message broker (Redis) - với JSON serializer phải base64 encode (~1.3x size)  
- Lưu vào Redis riêng → task chỉ truyền key (UUID string) → message nhỏ gọn, clean
- Dễ debug hơn (có thể inspect key trong Redis)

---

## Files Cần Tạo / Sửa

### Tạo mới: `celery_app.py`
Celery configuration, kết nối Redis:
```python
from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "detect_qr",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,  # kết quả tồn tại 1 giờ
)
```

### Tạo mới: `tasks.py`
Celery task wrapper cho detection:
```python
import os, redis, uuid
import cv2, numpy as np
from PIL import Image
from io import BytesIO
from celery_app import celery
from main import detect_cccd_from_image

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis = redis.from_url(REDIS_URL)

@celery.task(bind=True, name="detect_qr")
def detect_qr_task(self, image_key: str) -> dict:
    raw = _redis.get(image_key)
    _redis.delete(image_key)           # cleanup ngay
    if raw is None:
        raise ValueError("Image key expired or not found")
    
    pil_img = Image.open(BytesIO(raw)).convert("RGB")
    img = np.array(pil_img)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    
    return detect_cccd_from_image(img)
```

### Sửa: `service.py`
Refactor endpoints:
```python
import asyncio, uuid, os, redis as redis_lib
from celery.result import AsyncResult
from tasks import detect_qr_task

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis = redis_lib.from_url(REDIS_URL)
IMAGE_TTL = 300  # 5 phút

@app.post("/decode/file")
async def decode_from_upload(file: UploadFile = File(...)):
    raw = await file.read()
    
    # Lưu image vào Redis, push task
    image_key = f"img:{uuid.uuid4()}"
    _redis.setex(image_key, IMAGE_TTL, raw)
    task = detect_qr_task.delay(image_key)
    
    # Chờ kết quả (non-blocking với asyncio.to_thread)
    result = await asyncio.to_thread(task.get, timeout=60)
    return {"filename": file.filename, **result}

# Giữ nguyên /decode/path nhưng cũng qua Celery
```

### Sửa: `docker-compose.yml`
Thêm Redis service + Celery worker:
```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"

  detectqrcccd-worker:
    build: .
    command: celery -A celery_app worker --loglevel=info --concurrency=4
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - redis
    restart: unless-stopped

  detectqrcccd-api:
    build: .
    command: python -m uvicorn service:app --host 0.0.0.0 --port 8000
    ports:
      - "${HOST_PORT:-8000}:8000"
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - redis
      - detectqrcccd-worker
    restart: unless-stopped
```

### Sửa: `requirements.docker.txt` và `requirements.txt`
Thêm:
```
celery[redis]>=5.3
redis>=5.0
```

### Sửa: `.env.example`
Thêm:
```
REDIS_URL=redis://localhost:6379/0
```

---

## Thứ Tự Thực Hiện

1. Tạo `celery_app.py`
2. Tạo `tasks.py`
3. Sửa `service.py` - thêm Redis client + refactor endpoints
4. Sửa `requirements.*.txt`
5. Sửa `docker-compose.yml`
6. Sửa `.env.example`

---

## Không Làm

- Không thay đổi `main.py` (detection logic)
- Không thay đổi API response format (client không cần update)
- Không implement polling endpoint (sync-wait pattern, ẩn Celery với client)

---

## Verification

```bash
# 1. Chạy stack
docker compose up --build

# 2. Test single request
curl -X POST http://localhost:8000/decode/file \
  -F "file=@asset/CCCD_1.jpg"

# 3. Load test 100 concurrent (cần install hey/wrk)
hey -n 100 -c 100 -m POST \
  -F "file=@asset/CCCD_1.jpg" \
  http://localhost:8000/decode/file
```

---

## Scale khi cần thêm

```bash
# Tăng số Celery workers (mỗi worker có --concurrency=4 processes)
docker compose up --scale detectqrcccd-worker=3
# → 3 workers × 4 concurrency = 12 images xử lý song song
```

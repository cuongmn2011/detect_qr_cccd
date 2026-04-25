# Master Plan: Speed Optimization + Celery + Redis

## Mục Tiêu
1. **Tốc độ detect mỗi ảnh** nhanh hơn (tối ưu nội bộ main.py)
2. **Xử lý 100+ concurrent users** không block (Celery + Redis)

---

## Tổng Quan Kiến Trúc

```
100 clients gửi ảnh đồng thời
        │
        ▼ HTTP POST /decode/file
┌──────────────────────────┐
│   FastAPI  (service.py)  │  ← HTTP gateway, KHÔNG xử lý ảnh
│  ① lưu image → Redis     │
│  ② submit task → Queue   │
│  ③ await result (async)  │
└──────────────────────────┘
        │ Redis Queue (broker)
        ▼
┌──────────────────────────┐
│   Celery Workers         │  ← Scale theo nhu cầu (1-N workers)
│   detect_qr_task()       │
│     ① đọc image từ Redis │
│     ② detect_cccd_from_  │
│        image()  ← FAST   │  ← Tier 1, 2, 3 tối ưu ở đây
│     ③ store result       │
└──────────────────────────┘
        │ Redis Backend (results)
        ▼
    FastAPI trả HTTP response cho client
```

**Hai lớp tối ưu độc lập và bổ sung nhau:**
- **Celery + Redis**: xử lý concurrent users (scale horizontal)
- **main.py optimization**: mỗi task chạy nhanh hơn (scale vertical)

---

## Phase 1: Tối Ưu main.py (Tier 1 → 3)

> Thực hiện trước khi refactor service, để sau khi đưa vào Celery thì mỗi task đã nhanh sẵn.

### Tier 1 - Zero-Risk Cleanups (~15-25% speedup)

**File sửa:** `main.py`

1. **Xóa `resize_3x_enhanced`** — trùng y hệt `resize_3x` (line ~476)

2. **Cache CLAHE objects ở module level** — tạo 1 lần khi import, không tạo lại mỗi crop:
   ```python
   # Thêm vào top of main.py (sau các import)
   _CLAHE_30 = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
   _CLAHE_50 = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(8, 8))
   _CLAHE_80 = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(8, 8))
   ```
   Trong `preprocess_variants()`: dùng `_CLAHE_30.apply(gray)` thay vì tạo mới.

3. **Cache GaussianBlur + adaptiveThreshold** — tính 1 lần trong `find_qr_candidates()`, truyền vào `extract_qr_focused_regions()` và `find_finder_patterns()` thay vì tính lại 3-4 lần.

### Tier 2 - Smart Ordering (~30-50% speedup trên ảnh dễ)

**File sửa:** `main.py`

1. **Reorder preprocessing variants** — đưa winning variants lên đầu để early exit kick in sớm:
   ```
   Thứ tự cũ:  otsu, otsu_aggressive, ..., resize_3x (idx 6), ...
   Thứ tự mới: resize_3x, resize_3x_adapt, resize_4x, resize_3x_otsu, ... (rest)
   ```
   *(resize_3x và resize_3x_adapt là 2 trong 3 winning variants)*

2. **Reorder crops trong detection loop** — ưu tiên vùng đã xác định QR:
   ```
   Thứ tự mới: qr_focused → finder_pattern → contours → grid → full
   ```

3. **Defer bilateralFilter** — chuyển xuống cuối variant list (O(d²) per pixel, ít khi win)

### Tier 3 - Parallel Decode với Early-Cancel (~2-4x speedup trên ảnh khó)

**File sửa:** `main.py`

Tách ~683 decode attempts thành N chunks, mỗi chunk 1 thread. Thread nào tìm ra kết quả → set `Event` → các threads còn lại tự dừng sau attempt hiện tại.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
import math

def _decode_chunk(chunk: list, stop_event: Event) -> str | None:
    for img in chunk:
        if stop_event.is_set():
            return None
        result = try_decode_qr_only(img)
        if result:
            return result
    return None

def try_decode_parallel(all_variants: list, n_threads: int = 3) -> str | None:
    if not all_variants:
        return None
    stop_event = Event()
    chunk_size = math.ceil(len(all_variants) / n_threads)
    chunks = [all_variants[i:i + chunk_size] for i in range(0, len(all_variants), chunk_size)]

    with ThreadPoolExecutor(max_workers=n_threads) as executor:
        futures = [executor.submit(_decode_chunk, chunk, stop_event) for chunk in chunks]
        for future in as_completed(futures):
            result = future.result()
            if result:
                stop_event.set()
                executor.shutdown(wait=False, cancel_futures=True)
                return result
    return None
```

**Ví dụ với 600 attempts, n_threads=3:**
```
Thread 1: [  0 → 199]  ─┐
Thread 2: [200 → 399]  ──┼─ chạy song song
Thread 3: [400 → 599]  ─┘

Nếu Thread 1 tìm thấy ở attempt #50:
  → set stop_event → Thread 2, 3 dừng sau attempt hiện tại
  → Total time ≈ 50 attempts thay vì 600
```

> **Tại sao thread thực sự song song:** zxingcpp là C extension → GIL release trong C code → 3 threads decode cùng lúc thật sự.

**Không cần thêm dependency** — `ThreadPoolExecutor` và `threading.Event` là stdlib.

---

## Phase 2: Celery + Redis Architecture

> Thực hiện sau Phase 1, khi main.py đã được tối ưu.

### Files Tạo Mới

**`celery_app.py`** — Celery configuration:
```python
from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery("detect_qr", broker=REDIS_URL, backend=REDIS_URL, include=["tasks"])
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
)
```

**`tasks.py`** — Celery task:
```python
import os
import cv2, numpy as np
from PIL import Image
from io import BytesIO
import redis as redis_lib
from celery_app import celery
from main import detect_cccd_from_image

_redis = redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

@celery.task(bind=True, name="detect_qr")
def detect_qr_task(self, image_key: str) -> dict:
    raw = _redis.get(image_key)
    _redis.delete(image_key)          # cleanup ngay sau khi đọc
    if raw is None:
        raise ValueError("Image key expired or not found")
    pil_img = Image.open(BytesIO(raw)).convert("RGB")
    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return detect_cccd_from_image(img)  # ← đã được tối ưu ở Phase 1
```

### Files Sửa

**`service.py`** — Refactor endpoints qua Celery:
```python
import asyncio, uuid, os
import redis as redis_lib
from tasks import detect_qr_task

_redis = redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
IMAGE_TTL = 300  # 5 phút TTL cho image bytes trong Redis

@app.post("/decode/file")
async def decode_from_upload(file: UploadFile = File(...)):
    raw = await file.read()
    image_key = f"img:{uuid.uuid4()}"
    _redis.setex(image_key, IMAGE_TTL, raw)       # ① lưu image vào Redis
    task = detect_qr_task.delay(image_key)         # ② submit task
    result = await asyncio.to_thread(task.get, timeout=60)  # ③ chờ (non-blocking)
    return {"filename": file.filename, **result}
```

**`docker-compose.yml`** — Thêm Redis + Worker:
```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped

  detectqrcccd-worker:
    build: .
    command: celery -A celery_app worker --loglevel=info --concurrency=4
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on: [redis]
    restart: unless-stopped

  detectqrcccd-api:
    build: .
    command: python -m uvicorn service:app --host 0.0.0.0 --port 8000
    ports:
      - "${HOST_PORT:-8000}:8000"
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on: [redis, detectqrcccd-worker]
    restart: unless-stopped
```

**`requirements.docker.txt` và `requirements.txt`** — Thêm:
```
celery[redis]>=5.3
redis>=5.0
```

**`.env.example`** — Thêm:
```
REDIS_URL=redis://localhost:6379/0
```

---

## Tổng Hợp Files Thay Đổi

| File | Action | Phase |
|------|--------|-------|
| `main.py` | Tier 1: cache CLAHE, xóa duplicate | Phase 1 |
| `main.py` | Tier 2: reorder variants + crops | Phase 1 |
| `main.py` | Tier 3: thêm `try_decode_parallel()` | Phase 1 |
| `celery_app.py` | Tạo mới | Phase 2 |
| `tasks.py` | Tạo mới | Phase 2 |
| `service.py` | Refactor endpoints qua Celery | Phase 2 |
| `docker-compose.yml` | Thêm redis + worker services | Phase 2 |
| `requirements.docker.txt` | Thêm celery[redis], redis | Phase 2 |
| `requirements.txt` | Thêm celery[redis], redis | Phase 2 |
| `.env.example` | Thêm REDIS_URL | Phase 2 |

---

## Verification

```bash
# Phase 1: Kiểm tra accuracy + speedup
time python main.py --test_dir asset/

# Phase 2: Test full stack
docker compose up --build
curl -X POST http://localhost:8000/decode/file -F "file=@asset/CCCD_1.jpg"

# Load test 100 concurrent
hey -n 100 -c 100 -m POST -F "file=@asset/CCCD_1.jpg" http://localhost:8000/decode/file
```

**Expected:**
- Accuracy: 3/8 (37.5%) không đổi
- Per-image time: giảm ~60-70% (Phase 1)
- 100 concurrent users: xử lý được với `--scale detectqrcccd-worker=3`

---

## Scale khi cần

```bash
# Tăng số workers (mỗi worker 4 processes = 4 ảnh song song)
docker compose up --scale detectqrcccd-worker=3
# → 3 workers × 4 = 12 ảnh xử lý đồng thời
```

# Error Handling Strategy

## Overview

This document describes the comprehensive error handling implemented across the detect_qr_cccd service. The system is designed to **never crash**, **gracefully degrade**, and **log all errors** for debugging.

---

## Architecture Layers

### Layer 1: HTTP Endpoints (service.py)

All endpoints wrapped in try-except blocks:

```python
@app.post("/decode/file")
async def decode_from_upload(file: UploadFile = File(...)):
    try:
        # Main logic
        ...
    except HTTPException:
        raise  # Re-raise HTTP errors
    except Exception as exc:
        logger.error(..., exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
```

**Strategy**: Catch and convert all exceptions to proper HTTP responses.

---

### Layer 2: Helper Functions (service.py)

#### Image Loading (`_load_image_from_bytes`, `_load_image_from_path`)

**Risks**: 
- PIL raises `IOError`, `OSError` on corrupted files
- `cv2.cvtColor()` fails on invalid image shapes

**Solution**:
```python
def _load_image_from_bytes(data: bytes):
    try:
        pil_img = Image.open(BytesIO(data)).convert("RGB")
        img = np.array(pil_img)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    except (IOError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot process image: {str(e)}")
```

**Result**: Returns 400 Bad Request instead of crashing.

#### Redis Operations (`_save_preview_to_redis`)

**Risks**:
- Redis connection down
- Network timeout
- Memory full

**Solution**:
```python
def _save_preview_to_redis(img: np.ndarray, request_id: str) -> str:
    ...
    try:
        _redis.setex(preview_key, PREVIEW_TTL, encoded.tobytes())
    except Exception as e:
        logger.warning(f"Failed to save preview to Redis: {str(e)}")
    return f"/current-detect-image/{request_id}"  # Graceful fallback
```

**Result**: Preview save fails silently, request still succeeds.

---

### Layer 3: Celery Task (tasks.py)

**Risks**:
- Redis unavailable when loading image
- Corrupted image bytes in Redis
- Detection function crashes

**Solution**:
```python
@celery.task(bind=True, name="detect_qr")
def detect_qr_task(self, image_key: str) -> dict:
    try:
        try:
            raw = _redis.get(image_key)
        except Exception as e:
            raise RuntimeError(f"Failed to retrieve image from Redis: {str(e)}")

        if raw is None:
            raise ValueError("Image key expired or not found")

        try:
            pil_img = Image.open(BytesIO(raw)).convert("RGB")
            ...
        except (IOError, OSError) as e:
            raise ValueError(f"Invalid image format: {str(e)}")

        result = detect_cccd_from_image(img)
        return result
    except Exception as exc:
        logger.error(f"[detect_qr] task failed | error={str(exc)}", exc_info=True)
        raise  # Celery will retry or mark as failed
```

**Result**: Exceptions logged with full traceback, task marked as failed.

---

### Layer 4: Core Detection (main.py)

**Risks**:
- Deskew fails on edge cases
- QR candidate finding returns empty
- Preprocessing variants crash
- Parallel decoding timeout

**Solution**: Multi-layer try-catch:

```python
def detect_cccd_from_image(img: np.ndarray, debug_dir: Path | None = None) -> dict:
    try:
        # Layer 1: Deskew
        try:
            img = deskew(img)
        except Exception as e:
            logger.error(f"Deskew failed: {str(e)}", exc_info=True)
            return {"detected": False, ...}

        # Layer 2: WeChat QRCode (optional)
        if WECHAT_AVAILABLE:
            try:
                qr_results = try_decode_qr_wechat(img)
                if qr_results:
                    return {
                        "detected": True,
                        ...
                    }
            except Exception as e:
                logger.warning(f"WeChat QRCode detection failed: {str(e)}")

        # Layer 3: Find candidates
        try:
            crops = find_qr_candidates(img)
        except Exception as e:
            logger.error(f"Finding QR candidates failed: {str(e)}", exc_info=True)
            return {"detected": False, ...}

        # Layer 4: Process variants (per-crop error handling)
        all_variants = []
        try:
            for crop_name, cropped in crops.items():
                try:
                    variants = preprocess_variants(cropped)
                except Exception as e:
                    logger.warning(f"Preprocessing for {crop_name} failed: {str(e)}")
                    continue  # Skip this crop, try next

                all_variants.append((crop_name, variant_name, variant_img))
        except Exception as e:
            logger.error(f"Processing variants failed: {str(e)}", exc_info=True)

        # Layer 5: Parallel decode
        try:
            parallel_result = try_decode_parallel(all_variants, n_threads=3)
            if parallel_result:
                return {"detected": True, ...}
        except Exception as e:
            logger.error(f"Parallel decoding failed: {str(e)}", exc_info=True)

        return {"detected": False, ...}
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {"detected": False, ...}
```

**Result**: 
- Each step has independent error handling
- Failures don't stop other steps
- Graceful fallback to "not detected"
- Full logging for debugging

---

## Error Types & Responses

### Client Errors (400-499)

| Error | Cause | Response |
|-------|-------|----------|
| Empty file upload | No file data | 400 Bad Request |
| Invalid image format | Corrupted JPEG/PNG | 400 Bad Request |
| Invalid image path | File not found | 404 Not Found |
| Invalid JSON | Malformed request | 422 Unprocessable Entity |

### Server Errors (500)

| Error | Cause | Response |
|-------|-------|----------|
| Redis unavailable | Connection failed | 500 Service Unavailable |
| Celery broker down | Task queue unavailable | 500 Service Unavailable |
| Task timeout | Detection took >60s | 500 Internal Server Error |
| Unexpected crash | Unhandled exception | 500 Internal Server Error |

---

## Logging Strategy

### Log Levels

```python
logger.debug()    # Detailed info (deskew angle, variant count, etc.)
logger.info()     # Key events (request received, task started, task completed)
logger.warning()  # Non-fatal issues (WeChat failed, preprocessing skipped)
logger.error()    # Fatal issues (Redis unavailable, detection crashed)
```

### Example Log Output

```
[2026-04-26 22:25:33,091: INFO/MainProcess] POST /decode/file | file=CCCD_5.jpg | size=335214 bytes | request_id=abc-123
[2026-04-26 22:25:33,102: INFO/MainProcess] [detect_qr] task started | image_key=img:abc-123
[2026-04-26 22:25:35,234: DEBUG/MainProcess] Deskew rotation: 15.32 degrees
[2026-04-26 22:25:40,456: WARNING/MainProcess] WeChat QRCode detection failed: could not find detector
[2026-04-26 22:25:45,123: DEBUG/MainProcess] Loaded image: /path/to/image | shape=(1080, 1920, 3)
[2026-04-26 22:25:47,501: INFO/MainProcess] [detect_qr] task completed | detected=True | duration=14.40s | region=qr_focused_region_0
```

---

## Testing Error Handling

### 1. Test Corrupted Image

```bash
# Create invalid JPEG
echo "not a real jpeg" > invalid.jpg

# Upload
curl -X POST http://localhost:8000/decode/file -F "file=@invalid.jpg"
# Expected: 400 Bad Request - "Invalid image format"
```

### 2. Test Empty File

```bash
touch empty.jpg
curl -X POST http://localhost:8000/decode/file -F "file=@empty.jpg"
# Expected: 400 Bad Request - "Empty file"
```

### 3. Test Invalid Path

```bash
curl -X POST http://localhost:8000/decode/path \
  -H "Content-Type: application/json" \
  -d '{"image_path": "/nonexistent/path.jpg"}'
# Expected: 404 Not Found - "Image not found"
```

### 4. Test Redis Unavailable

```bash
# Stop Redis
redis-cli shutdown

# Try to upload image
curl -X POST http://localhost:8000/decode/file -F "file=@test.jpg"
# Expected: 500 Service Unavailable - "failed to process request"

# Restart Redis
redis-server
```

### 5. Test Slow Image

```bash
# Use very large or complex image
# Upload and wait 60+ seconds
# Expected: 500 Internal Server Error - "Task timeout after 60s"
```

---

## Monitoring & Alerting

### Critical Logs to Monitor

```bash
# Redis connection errors
grep "Failed to retrieve image from Redis" .temp/celery_*.log

# Celery task failures
grep "task failed" .temp/celery_*.log

# Processing errors
grep "ERROR" .temp/celery_*.log
```

### Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status": "ok"}
```

### Metrics to Track

1. **Error rate**: Errors / Total requests
2. **Task success rate**: Successful tasks / Total tasks
3. **Redis connection errors**: Count per hour
4. **Detection accuracy**: Detected / Total attempts
5. **Response time**: p50, p95, p99 latency

---

## Future Improvements

1. **Retry Logic**: Implement exponential backoff for Redis failures
2. **Circuit Breaker**: Disable Redis operations if too many failures
3. **Error Tracking**: Integrate with Sentry/DataDog for error reporting
4. **Custom Exceptions**: Create specific exception types for different failure modes
5. **Error Metrics**: Add Prometheus metrics for error tracking
6. **Dead Letter Queue**: Store failed tasks for later analysis

---

## Related Files

- [LOGGING_SYSTEM.md](LOGGING_SYSTEM.md) - Logging architecture
- [../README.md](../README.md) - User documentation
- [../service.py](../service.py) - HTTP endpoints with error handling
- [../tasks.py](../tasks.py) - Celery task with error handling
- [../main.py](../main.py) - Core detection with multi-layer error handling

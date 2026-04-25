# Solutions: concurrent requests + current_detect.jpg

## Problem
```
Request A: POST /decode/file (ảnh A)  ──┐
Request B: POST /decode/file (ảnh B)  ──┼─→ Cùng ghi: ./runtime/detect/current_detect.jpg
Request C: POST /decode/file (ảnh C)  ──┘

❌ Race condition: File bị overwrite, web UI hiển thị ảnh sai
```

---

## 🎯 Solution 1: Per-Request File (Simple, Disk Heavy)

### Approach
Mỗi request lưu vào file riêng theo UUID:
```
./runtime/detect/
├── current_{request_id_A}.jpg
├── current_{request_id_B}.jpg
└── current_{request_id_C}.jpg
```

### Implementation
```python
# service.py - Line 85-110 (decode_from_upload)

async def decode_from_upload(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty file")

        # Generate unique file per request
        request_id = str(uuid.uuid4())
        image_key = f"img:{request_id}"
        
        _redis.setex(image_key, IMAGE_TTL, raw)
        task = detect_qr_task.delay(image_key)
        result = await asyncio.to_thread(task.get, timeout=60)
        
        img = _load_image_from_bytes(raw)
        
        # Save with request_id
        current_file = RUNTIME_DIR.joinpath(f"current_{request_id}.jpg")
        success, encoded = cv2.imencode(".jpg", img)
        if not success:
            raise RuntimeError("Cannot encode image for preview")
        current_file.write_bytes(encoded.tobytes())
        
        image_url = f"/current-detect-image/{request_id}"
        
        return {
            "filename": file.filename,
            "current_image_url": image_url,
            "request_id": request_id,
            **result,
        }
```

### Update endpoint
```python
# service.py - Thêm endpoint lấy riêng per request

@app.get("/current-detect-image/{request_id}")
def current_detect_image(request_id: str):
    current_file = RUNTIME_DIR.joinpath(f"current_{request_id}.jpg")
    if not current_file.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(current_file)
```

### Cleanup strategy
```python
# Option A: TTL cleanup (chạy background task)
import asyncio
from datetime import datetime, timedelta

async def cleanup_old_images(max_age_minutes=30):
    """Xóa files cũ hơn 30 phút"""
    while True:
        await asyncio.sleep(300)  # Check mỗi 5 phút
        now = datetime.now()
        for file in RUNTIME_DIR.glob("current_*.jpg"):
            file_age = now - datetime.fromtimestamp(file.stat().st_mtime)
            if file_age > timedelta(minutes=max_age_minutes):
                file.unlink()
                print(f"Deleted old image: {file}")

# startup event
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_old_images())
```

### Pros & Cons
✅ Simple, không cần Redis  
✅ Mỗi request có ảnh riêng  
❌ Disk accumulation (need cleanup)  
❌ Nếu có 1000 concurrent → 1000 files  

---

## 🎯 Solution 2: Redis-based Preview (Recommended for Concurrent)

### Approach
Lưu ảnh encoded vào Redis thay vì disk:
```
Request A: ảnh A → Redis key: preview:{request_id_A} (TTL 5 min)
Request B: ảnh B → Redis key: preview:{request_id_B} (TTL 5 min)
Request C: ảnh C → Redis key: preview:{request_id_C} (TTL 5 min)
```

### Implementation
```python
# service.py - Line 85-110

async def decode_from_upload(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty file")
        
        request_id = str(uuid.uuid4())
        image_key = f"img:{request_id}"
        
        _redis.setex(image_key, IMAGE_TTL, raw)
        task = detect_qr_task.delay(image_key)
        result = await asyncio.to_thread(task.get, timeout=60)
        
        # Encode and store in Redis (not disk)
        img = _load_image_from_bytes(raw)
        success, encoded = cv2.imencode(".jpg", img)
        if not success:
            raise RuntimeError("Cannot encode image")
        
        preview_key = f"preview:{request_id}"
        _redis.setex(preview_key, 300, encoded.tobytes())  # 5 min TTL
        
        image_url = f"/current-detect-image/{request_id}"
        
        return {
            "filename": file.filename,
            "current_image_url": image_url,
            "request_id": request_id,
            **result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# Update endpoint
@app.get("/current-detect-image/{request_id}")
def current_detect_image(request_id: str):
    preview_key = f"preview:{request_id}"
    image_bytes = _redis.get(preview_key)
    if not image_bytes:
        raise HTTPException(status_code=404, detail="Image not found or expired")
    
    return Response(content=image_bytes, media_type="image/jpeg")
```

### Pros & Cons
✅ No disk needed (scalable)  
✅ Auto cleanup (TTL 5 min)  
✅ Concurrent-friendly  
❌ Uses Redis memory (~100-500KB per image)  
❌ If Redis restarts, images lost  

---

## 🎯 Solution 3: Inline Response (No Preview Storage)

### Approach
Không lưu preview, gửi ảnh trực tiếp trong response:
```python
return {
    "filename": file.filename,
    "image_base64": base64.b64encode(encoded).decode(),  # Inline ảnh
    "detected": ...,
    ...
}
```

### Pros & Cons
✅ Không dùng disk/Redis  
✅ Simple  
✅ Scalable  
❌ Response size lớn hơn (~200-500KB)  
❌ Client phải decode base64  

---

## Recommendation

| Scenario | Best Solution |
|----------|---------------|
| **Single user** | Solution 1 (Per-Request File) |
| **10-50 concurrent users** | Solution 1 (File) + TTL cleanup |
| **100+ concurrent users** | Solution 2 (Redis-based) |
| **Resource constrained** | Solution 3 (Inline response) |
| **High throughput** | Solution 2 (Redis) |

---

## 🔄 Hybrid Approach (Best Overall)

Combine Solutions 1 + 2:
```python
SAVE_PREVIEW_TO_DISK = os.getenv("SAVE_PREVIEW_TO_DISK", "false").lower() == "true"

async def decode_from_upload(file: UploadFile = File(...)):
    # ... existing code ...
    
    request_id = str(uuid.uuid4())
    
    # Always save to Redis (scalable)
    preview_key = f"preview:{request_id}"
    _redis.setex(preview_key, 300, encoded.tobytes())
    
    # Optionally also save to disk (for debugging)
    if SAVE_PREVIEW_TO_DISK:
        current_file = RUNTIME_DIR.joinpath(f"current_{request_id}.jpg")
        current_file.write_bytes(encoded.tobytes())
    
    return {
        "filename": file.filename,
        "current_image_url": f"/current-detect-image/{request_id}",
        "request_id": request_id,
        **result,
    }
```

### Docker Compose
```yaml
detectqrcccd-api:
  environment:
    SAVE_PREVIEW_TO_DISK: "false"  # Default: use Redis only
    # SAVE_PREVIEW_TO_DISK: "true"  # Optional: for debugging
```

---

## Implementation Steps

### Quick Fix (5 min)
1. Change to Solution 2 (Redis-based)
2. No breaking changes to API
3. Just need to add `request_id` to response

### What to Update
```python
# service.py
- Remove: RUNTIME_DIR, CURRENT_DETECT_FILE, _clear_detect_cache(), _save_current_detect_image()
- Add: Redis key for preview: preview:{request_id}
- Update: Both /decode/file and /decode/path endpoints
- Update: /current-detect-image endpoint to read from Redis
```

### Testing
```bash
# Terminal 1: API logs
docker compose logs -f detectqrcccd-api

# Terminal 2: Test multiple concurrent requests
for i in {1..5}; do
  curl -X POST http://localhost:8000/decode/file \
    -F "file=@test.jpg" &
done
wait

# Check Redis keys
docker exec detectqrcccd-redis redis-cli KEYS "preview:*"
```

---

## Database Comparison

| Solution | Disk | Redis | TTL Cleanup | Concurrent Safe |
|----------|------|-------|------------|-----------------|
| Current | ❌ 1 shared file | - | Manual | ❌ Race condition |
| Solution 1 | ✅ Per-request | - | Background task | ✅ Yes |
| Solution 2 | - | ✅ Per-request | Auto (TTL) | ✅ Yes |
| Solution 3 | - | - | N/A | ✅ Yes |
| Hybrid | Optional | ✅ Always | Auto + Optional | ✅ Yes |

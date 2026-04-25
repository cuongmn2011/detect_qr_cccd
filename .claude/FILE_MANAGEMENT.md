# File Management Flow - QR Detection Pipeline

## 📊 Overview

| Giai đoạn | Nơi lưu | TTL | Xóa khi nào | Dùng để |
|----------|---------|-----|-----------|---------|
| 1. Upload | Redis memory | 5 phút | Manual (task xóa) | Celery worker read |
| 2. Crops/Variants | Memory only* | - | Auto (end of request) | Processing |
| 3. Result preview | `./runtime/detect/` | ∞ | Next request | Web UI display |
| 4. Task result | Redis memory | 1 giờ | Auto expire | API response |

*Chỉ debug mode mới save crops/variants ra disk

---

## 🔄 Chi Tiết Flow

### Phase 1: API Gateway (service.py)

#### Endpoint: `POST /decode/file` (Upload File)
```
1. Nhận file từ client
   ↓
2. Lưu bytes vào Redis với key: img:{uuid}
   - TTL: 300 giây (5 phút)
   - Dùng để: Worker lấy image
   ↓
3. Submit task detect_qr_task.delay(image_key)
   ↓
4. Chờ worker xử lý (timeout 60s)
   ↓
5. Lấy result từ task
   ↓
6. Load lại original image từ bytes
   ↓
7. Lưu vào ./runtime/detect/current_detect.jpg
   - Trước khi lưu: xóa tất cả file cũ (_clear_detect_cache())
   ↓
8. Trả response + current_image_url
```

**Redis key sau API:**
- `img:{uuid}` bị xóa bởi **tasks.py** (line ~20)
- Task result lưu ở `celery-task-meta-{task_id}` (TTL: 3600s)

---

### Phase 2: Celery Worker (tasks.py)

#### Task: `detect_qr_task(image_key)`
```
1. Retrieve ảnh từ Redis: _redis.get(image_key)
   ↓
2. Gọi detect_cccd_from_image(img, debug_dir=None)
   ↓
3. Xử lý QR detection:
   - Deskew
   - Tìm candidates
   - Sinh variants (TÍNH TOÁN TRONG MEMORY)
   - Decode song song
   ↓
4. **XÓA** image từ Redis: _redis.delete(image_key)
   ↓
5. Trả result vào Redis task queue
   - Key: celery-task-meta-{task_id}
   - TTL: 3600 giây (từ celery_app.py)
```

**Lưu ý:** Không có file nào được lưu trên disk trong worker (ngoài debug mode)

---

### Phase 3: Web UI Display (service.py)

#### Endpoint: `GET /current-detect-image`
```
Trả file: ./runtime/detect/current_detect.jpg
- Là ảnh ORIGINAL được load lại từ bytes (không phải ảnh debug)
- Được cập nhật mỗi khi có request thành công
- File cũ bị xóa trước khi lưu file mới
```

**Cấu trúc thư mục:**
```
project-root/
├── runtime/
│   └── detect/
│       └── current_detect.jpg    (1 file, update mỗi request)
├── asset/                        (Mount read-only vào container)
├── web/
│   └── index.html
└── ...
```

---

## 🐛 Debug Mode (Chỉ khi chạy test)

### Command
```bash
python main.py --test_dir ./test_images --debug_dir ./debug_output
```

### Hành vi
Khi `debug_dir` được pass:
```
1. Sinh từng variant
   ↓
2. **LƯU** vào: {debug_dir}/{crop_name}_{variant_name}.jpg
   ↓
3. Đưa vào all_variants list
   ↓
4. Decode song song
```

**Output example:**
```
debug_output/
├── qr_focused_region_0_gray.jpg
├── qr_focused_region_0_enhanced.jpg
├── qr_focused_region_0_resize_3x.jpg
├── contour_region_1_gray.jpg
├── contour_region_1_otsu.jpg
├── ...
```

**Không tự động xóa** → User phải `rm -rf debug_output` sau khi xem

---

## 💾 File Lifecycle Summary

### `./runtime/detect/current_detect.jpg`
```
Status:     PERSISTENT (lưu lại)
Lifetime:   Đến khi có request mới
Usage:      Web UI hiển thị ảnh đang detect
Size:       ~100-500 KB (tùy ảnh)
```

### Redis Keys
```
img:{uuid}
├─ Status: TEMPORARY
├─ Lifetime: 5 phút (được xóa bởi worker)
├─ Usage: Communicate bytes giữa API ↔ Worker
└─ Size: Tùy upload file

celery-task-meta-{task_id}
├─ Status: TEMPORARY
├─ Lifetime: 1 giờ (auto expire)
├─ Usage: Store task result
└─ Size: ~1-5 KB
```

### Crop/Variant Images (Memory)
```
Status:     TEMPORARY
Lifetime:   Chỉ tồn tại trong khi task running
Usage:      Processing pipeline
Size:       ~10-100 MB (sau khi preprocessed)
```

---

## 🎯 Recommendations

### Current Setup ✅
Tốt cho:
- Single request: File auto cleanup
- Web UI preview: Lưu current_detect.jpg
- Multiple requests: Mỗi request overwrite file cũ (không accumulate)

### Potential Issues ⚠️

1. **Disk space accumulation trong debug mode**
   ```
   ❌ Không xóa debug output
   ✅ Thêm: python cleanup_debug.py hoặc manual rm
   ```

2. **`./runtime/` directory có thể bị permission error**
   ```
   ✅ Docker: Sử dụng volume mount
   ⚠️ Local dev: Ensure ./runtime tồn tại + writable
   ```

3. **Redis memory (nếu có 1000+ concurrent requests)**
   ```
   ❌ img:{uuid} accumulate nếu worker crash
   ✅ Thêm Redis eviction policy: `maxmemory-policy allkeys-lru`
   ```

### Suggested Enhancements

#### Option 1: Configurable File Persistence
```python
# service.py
KEEP_CURRENT_IMAGE = os.getenv("KEEP_CURRENT_IMAGE", "true").lower() == "true"

def _save_current_detect_image(img: np.ndarray) -> str:
    if KEEP_CURRENT_IMAGE:
        _clear_detect_cache()
        # ... save file
        return f"/current-detect-image?t={int(time.time() * 1000)}"
    else:
        return None  # Không lưu, tiết kiệm disk
```

#### Option 2: Add Cache Cleanup Endpoint
```python
@app.delete("/cache/clear")
def clear_runtime_cache():
    """Clear current_detect.jpg để giải phóng disk space"""
    _clear_detect_cache()
    return {"status": "cleared"}
```

#### Option 3: Add Timestamp-based File Rotation
```python
# service.py
def _save_current_detect_image(img: np.ndarray) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    detect_file = RUNTIME_DIR.joinpath(f"detect_{timestamp}.jpg")
    # ... lưu file với timestamp
    # Keep only last 10 files
```

---

## 🔍 Kiểm Tra Disk Usage

```bash
# Xem size của runtime directory
du -sh ./runtime/

# Xem chi tiết files
ls -lh ./runtime/detect/

# Xem Redis memory
docker exec detectqrcccd-redis redis-cli INFO memory
```

---

## 📝 Summary

**Hiện tại:**
- ✅ Upload bytes → Redis (TTL 5m, worker xóa)
- ✅ Processing → Memory only (auto cleanup)
- ✅ Result preview → `./runtime/detect/current_detect.jpg` (persistent, 1 file)
- ✅ Task result → Redis (TTL 1h, auto expire)

**Không lưu file crops/variants** trên disk (trừ debug mode)

**Disk usage:** Minimal (~1 file, ~200KB max)

**Memory usage:** ~50-200MB per concurrent request (tùy image size)

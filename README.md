# detectQRCCCD

Service nhận ảnh CCCD và giải mã dữ liệu QR code với kiến trúc hỗ trợ 100+ người dùng đồng thời.

## Kiến Trúc

Hệ thống sử dụng:
- **FastAPI**: HTTP gateway nhận request
- **Celery + Redis**: Xử lý task bất đồng bộ với queue
- **Docker/Native/EXE**: Tùy chọn triển khai linh hoạt

Lợi ích:
- ✅ Hỗ trợ 100+ concurrent users mà không block API
- ✅ Tự động scaling: thêm workers để xử lý nhiều ảnh hơn
- ✅ ~20-50% nhanh hơn từ Phase 1-3 optimizations (variant reordering, CLAHE cache, parallel decode)

## Yêu Cầu

### Phần mềm cần thiết
- **Python**: 3.8+
- **Redis**: 5.0+ (chạy locally hoặc remote)

### Dependencies
```bash
pip install -r requirements.txt
```

---

# 🚀 3 Cách Chạy Service

## 1️⃣ Chạy Trực Tiếp (Python)

**Phù hợp cho**: Development, testing, single-machine deployment

### Setup
```bash
# Cài dependencies
pip install -r requirements.txt

# Kiểm tra Redis đang chạy
# Windows: redis-server (hoặc dùng WSL)
# Mac: brew services start redis
# Linux: sudo systemctl start redis-server
```

### Chạy Development Mode
```bash
python run.py
```

Server sẽ chạy tại: `http://127.0.0.1:8000`

**Logs**: Console output, tự động reload khi code thay đổi

### Chạy Production Mode
```bash
ENV=prod python run.py
```

### Chỉnh Cấu Hình (Tùy chọn)

**Windows CMD:**
```bash
set SERVER_HOST=0.0.0.0
set SERVER_PORT=8000
set REDIS_HOST=192.168.1.100
set REDIS_DB=10
set ENV=prod
python run.py
```

**PowerShell:**
```powershell
$env:SERVER_HOST="0.0.0.0"
$env:REDIS_HOST="192.168.1.100"
$env:REDIS_DB="10"
$env:ENV="prod"
python run.py
```

**Linux/Mac:**
```bash
SERVER_HOST=0.0.0.0 REDIS_HOST=192.168.1.100 REDIS_DB=10 ENV=prod python run.py
```

### Environment Variables

| Biến | Default | Mô tả |
|------|---------|-------|
| `SERVER_HOST` | `127.0.0.1` | Server bind address (dùng `0.0.0.0` để cho phép remote access) |
| `SERVER_PORT` | `8000` | Server port |
| `REDIS_HOST` | `localhost` | Redis server address |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `10` | Redis database number (10-15 để tránh conflict) |
| `LOGGING_DIR` | `./logs` | Thư mục lưu logs (production mode) |
| `ENV` | `dev` | `dev` hoặc `prod` |

---

## 2️⃣ Chạy Bằng Docker Compose

**Phù hợp cho**: Production, multi-service deployment, team collaboration

### Setup
```bash
# Kiểm tra Docker & Docker Compose đã cài
docker --version
docker compose --version
```

### Chạy Service

```bash
docker compose up -d --build
```

Docker Compose sẽ khởi động 3 service:
- **redis**: Message broker + result backend (port 6379)
- **detectqrcccd-worker**: Celery worker xử lý task
- **detectqrcccd-api**: FastAPI gateway (port 8000)

### Chỉnh Cấu Hình (Tùy chọn)

Sửa file `docker-compose.yml` hoặc set environment variables:

```bash
set APP_DOMAIN=localhost
set HOST_PORT=8000
set APP_HOST=0.0.0.0
set APP_PORT=8000
set REDIS_DB=10

docker compose up -d --build
```

### Health Check
```bash
curl http://localhost:8000/health
```

### Xem Logs
```bash
# Tất cả logs
docker compose logs -f

# Chỉ API logs
docker compose logs -f detectqrcccd-api

# Chỉ Worker logs
docker compose logs -f detectqrcccd-worker
```

### Scaling Workers
```bash
# Thêm thêm worker để xử lý nhiều ảnh hơn
docker compose up -d --scale detectqrcccd-worker=2
```

### Dừng Service
```bash
docker compose down
```

---

## 3️⃣ Build & Chạy EXE (Windows)

**Phù hợp cho**: Standalone deployment, Windows servers, end-user distribution

### Build EXE

**Yêu cầu**: PyInstaller
```bash
pip install pyinstaller
```

**Build:**
```bash
pyinstaller detect_qr_cccd.spec
```

EXE sẽ được tạo ở: `dist/detect_qr_cccd/detect_qr_cccd.exe`

### Chạy EXE

**Cách 1: Chạy trực tiếp (development)**
```cmd
detect_qr_cccd.exe
```

**Cách 2: Tạo Batch File (Khuyên dùng)**

Tạo file `run_server.bat`:
```batch
@echo off
set SERVER_HOST=0.0.0.0
set SERVER_PORT=8000
set REDIS_HOST=192.168.1.100
set REDIS_DB=10
set ENV=prod
detect_qr_cccd.exe
pause
```

Chạy:
```bash
run_server.bat
```

**Cách 3: PowerShell Script**

Tạo file `run_server.ps1`:
```powershell
$env:SERVER_HOST="0.0.0.0"
$env:REDIS_HOST="192.168.1.100"
$env:REDIS_DB="10"
$env:ENV="prod"
.\detect_qr_cccd.exe
```

Chạy:
```powershell
powershell -ExecutionPolicy Bypass -File run_server.ps1
```

### Lưu ý khi Deploy EXE
- ✅ Redis server phải chạy sẵn (localhost hoặc remote)
- ✅ Set `REDIS_HOST` trỏ đến Redis server đúng
- ✅ Set `REDIS_DB` khác các project khác (khuyên dùng 10-15)
- ✅ Dùng `SERVER_HOST=0.0.0.0` để cho phép remote access
- ⚠️ File size: ~300-400MB (do OpenCV)
- ⚠️ Một số antivirus có thể block EXE (false positive)

---

# 📡 API Documentation

### Health Check
```bash
curl http://localhost:8000/health
```

Response:
```json
{"status": "ok"}
```

### Web UI
Mở trình duyệt: `http://localhost:8000/`

Giao diện cho phép:
- Upload ảnh CCCD
- Chụp ảnh từ camera
- Xem kết quả decode + preview ảnh

### Decode từ File Upload
```bash
curl -X POST http://localhost:8000/decode/file \
  -F "file=@path/to/cccd.jpg"
```

Response:
```json
{
  "filename": "cccd.jpg",
  "request_id": "uuid-string",
  "current_image_url": "/current-detect-image/{request_id}",
  "detected": true,
  "region": "qr_focused_region_0",
  "variant": "resize_3x",
  "raw_data": "QR code string",
  "fields": ["ID Number", "Full Name", "Date of Birth", ...],
  "mapped": {
    "ID Number": "...",
    "Full Name": "...",
    "Date of Birth": "...",
    ...
  }
}
```

### Decode từ File Path (Docker/Native)
```bash
curl -X POST http://localhost:8000/decode/path \
  -H "Content-Type: application/json" \
  -d '{"image_path":"/app/asset/cccd.jpg"}'
```

### Lấy Preview Image
```bash
curl http://localhost:8000/current-detect-image/{request_id} \
  --output preview.jpg
```

**Lưu ý**: Preview được lưu trong Redis với TTL 5 phút.

---

# 📋 Định Dạng Ảnh Hỗ Trợ

jpg, jpeg, png, heic, heif, bmp, tif, tiff, webp

---

# 🧪 Testing

### Test API
```bash
# Upload file
curl -X POST http://localhost:8000/decode/file \
  -F "file=@./test_image.jpg"

# Hoặc từ path
curl -X POST http://localhost:8000/decode/path \
  -H "Content-Type: application/json" \
  -d '{"image_path":"/path/to/test.jpg"}'
```

### Test Performance
```bash
time curl -X POST http://localhost:8000/decode/file \
  -F "file=@./test_images/CCCD_1.jpg"
```

Expected: 2-5 giây per ảnh (tùy quality)

---

# ❌ Troubleshooting

### Redis Connection Error
```
Error: redis.exceptions.ConnectionError
```
**Giải pháp:**
- Kiểm tra Redis đang chạy: `redis-cli ping` (should reply `PONG`)
- Kiểm tra REDIS_HOST & REDIS_PORT đúng
- Docker: `docker compose logs redis`

### Worker không nhận task
```
[Worker] No tasks received
```
**Giải pháp:**
- Kiểm tra worker chạy: `docker compose logs detectqrcccd-worker`
- Restart worker: `docker compose restart detectqrcccd-worker`
- Kiểm tra Redis healthy: `docker compose ps`

### Request Timeout (60s)
```
HTTPException: Task timed out
```
**Giải pháp:**
- Thêm workers: `docker compose up -d --scale detectqrcccd-worker=2`
- Kiểm tra ảnh quality (ảnh blur/tilt xử lý lâu hơn)
- Tăng timeout: sửa `service.py` line 94

### EXE không chạy
- Kiểm tra Redis đang chạy
- Set REDIS_HOST & REDIS_DB đúng
- Xem logs: bật CMD/PowerShell xem lỗi chi tiết

---

# 📈 Performance Notes

- **Tier 1** (~20% faster): Cache CLAHE objects
- **Tier 2** (~40% faster): Reorder variants by frequency
- **Tier 3** (~2-4x faster): Parallel decode với ThreadPoolExecutor

Tối ưu hoá là tự động, không cần cấu hình thêm.

---

# 📚 Chi Tiết Kiến Trúc

Xem [.claude/](`.claude/`) folder cho thêm thông tin về:
- Kiến trúc chi tiết
- Optimization plans
- Solution documents

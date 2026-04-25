# detectQRCCCD

Service nhận ảnh CCCD và giải mã dữ liệu QR code.

## Build Và Chạy Bằng Docker Compose

Bạn có thể tùy biến domain và port bằng biến môi trường:

```bash
set APP_DOMAIN=cccd.local
set HOST_PORT=8088
set APP_HOST=0.0.0.0
set APP_PORT=8000
```

Hoặc copy từ file mẫu:

```bash
copy .env.example .env
```

Nếu không set, mặc định sẽ là:

- `APP_DOMAIN=localhost`
- `HOST_PORT=8000`
- `APP_HOST=0.0.0.0`
- `APP_PORT=8000`

### 1. Build và chạy service

```bash
docker compose up -d --build
```

### 2. Health check

```bash
curl http://%APP_DOMAIN%:%HOST_PORT%/health
```

### 3. Gọi API bằng upload file

```bash
curl -X POST http://%APP_DOMAIN%:%HOST_PORT%/decode/file \
  -F "file=@/path/to/cccd-image.png"
```

### Giao diện web đơn giản

Sau khi service chạy, mở trình duyệt tại:

```text
http://<APP_DOMAIN>:<HOST_PORT>/
```

Tại đây bạn có thể chọn ảnh, bấm Decode Image, và xem:

- Mapped fields (thông tin đã parse)
- Current detect image (ảnh đang được xử lý)
- Raw JSON response

Ngoài chọn file, giao diện cũng hỗ trợ chụp ảnh trực tiếp:

- Bấm `Start Camera` -> `Capture Photo` -> `Decode Image`.
- Trình duyệt cần cấp quyền camera (nên chạy qua `localhost` hoặc `https`).

Lưu ý:

- Mỗi lần upload file mới, hệ thống sẽ xóa ảnh detect cũ và chỉ giữ lại ảnh mới nhất.

### 4. (Tùy chọn) Gọi API bằng đường dẫn file trong container

Theo file compose hiện tại, thư mục `./asset` được mount vào `/app/asset` trong container.

Gọi endpoint `/decode/path` với đường dẫn trong container:

```bash
curl -X POST http://%APP_DOMAIN%:%HOST_PORT%/decode/path \
  -H "Content-Type: application/json" \
   -d '{"image_path":"/app/asset/IMG_4310.png"}'
```

## Đổi Domain Local (Windows)

Nếu bạn muốn truy cập bằng domain riêng thay vì `127.0.0.1`:

1. Mở file `C:\Windows\System32\drivers\etc\hosts` bằng quyền Administrator.
2. Thêm một dòng, ví dụ:

```text
127.0.0.1 cccd.local
```

3. Mở terminal mới và set biến:

```bash
set APP_DOMAIN=cccd.local
set HOST_PORT=8088
```

4. Chạy lại:

```bash
docker compose up -d --build
```

5. Truy cập:

```text
http://cccd.local:8088/
```

### 5. Xem logs

```bash
docker compose logs -f
```

### 6. Dừng service

```bash
docker compose down
```

## Workflow Chức Năng Upload Ảnh

Khi gọi endpoint `POST /decode/file`, hệ thống xử lý theo pipeline sau:

1. Receive upload:
   Nhận file ảnh từ request `multipart/form-data`.
2. Validate input:
   Nếu file rỗng, API trả về `400 Bad Request`.
3. Decode image bytes:
   Chuyển bytes ảnh thành OpenCV BGR ndarray để đưa vào pipeline xử lý.
4. Normalize orientation:
   Thực hiện deskew để giảm tình trạng ảnh bị nghiêng.
5. Generate QR candidate regions:
   Tạo nhiều vùng nghi ngờ chứa QR bằng 3 chiến lược:
   - Contour-based square detection.
   - Finder-pattern based proposal.
   - Grid split toàn ảnh để tăng recall.
6. Build preprocessing variants:
   Với từng candidate region, sinh các biến thể: `gray`, `enhanced`, `sharpened`, `otsu`, `denoise`, `resize_2x`, `resize_3x`.
7. Attempt QR decoding:
   Thử decode tuần tự trên từng biến thể bằng `zxingcpp` và chỉ lấy kết quả QR.
8. Parse and map CCCD fields (on success):
   Khi decode thành công, dữ liệu được:
   - Tách theo ký tự `|`.
   - Map sang các trường chuẩn (ID Number, Full Name, Date of Birth, ...).
   - Trả về response với `detected=true`, kèm `region`, `variant`, `raw_data`, `fields`, `mapped`.
9. Return fallback result (on failure):
   Nếu không decode được ở mọi vùng và mọi biến thể, trả về response với `detected=false`.

## Cấu Trúc Response JSON

- `detected`: true/false
- `region`: tên vùng crop decode thành công (hoặc null)
- `variant`: tên biến thể preprocessing decode thành công (hoặc null)
- `raw_data`: chuỗi QR gốc (hoặc null)
- `fields`: danh sách tách theo `|`
- `mapped`: object map field name -> value

## Định Dạng Ảnh Hỗ Trợ

- jpg
- jpeg
- png
- heic
- heif
- bmp
- tif
- tiff
- webp

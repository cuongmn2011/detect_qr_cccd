# API Endpoints

## Overview
FastAPI service running on `service.py` with endpoints for CCCD QR code detection and decoding.

## Endpoints

### 1. Health Check
**GET** `/health`

Check service status.

**Response:**
```json
{
  "status": "ok"
}
```

---

### 2. Web UI
**GET** `/`

Serve the web interface (index.html) for interactive CCCD scanning.

**Response:** HTML file with responsive layout, camera support, and decode functionality.

---

### 3. Get Current Detect Image
**GET** `/current-detect-image`

Retrieve the last processed image (JPG format).

**Query Parameters:**
- `t` (optional): Timestamp to bypass cache (e.g., `?t=1234567890000`)

**Response:** 
- JPG image file if available
- 404 if no image has been processed yet

---

### 4. Decode from File Upload
**POST** `/decode/file`

Upload an image file and decode CCCD QR data.

**Request:**
- Content-Type: `multipart/form-data`
- Field: `file` (required) - Image file (jpg, jpeg, png, heic, heif, bmp, tif, tiff, webp)

**Response:**
```json
{
  "filename": "string",
  "current_image_url": "/current-detect-image?t=1234567890000",
  "detected": true/false,
  "region": "string or null",
  "variant": "string or null",
  "raw_data": "string or null",
  "fields": ["field1", "field2", ...],
  "mapped": {
    "ID Number": "value",
    "Old ID Number": "value",
    "Full Name": "value",
    "Date of Birth": "value",
    "Sex": "value",
    "Address": "value",
    "Issue Date": "value"
  }
}
```

**Status Codes:**
- `200`: Success (detected may be true or false)
- `400`: Empty file
- `500`: Processing error

---

### 5. Decode from File Path
**POST** `/decode/path`

Decode from an image path accessible within the container.

**Request:**
```json
{
  "image_path": "/app/asset/image.png"
}
```

**Response:**
```json
{
  "image_path": "/full/path/to/image.png",
  "detected": true/false,
  "region": "string or null",
  "variant": "string or null",
  "raw_data": "string or null",
  "fields": [],
  "mapped": {}
}
```

**Status Codes:**
- `200`: Success
- `404`: Image file not found
- `500`: Processing error

---

## Field Mapping

CCCD QR data is pipe-separated (|) with the following order:
1. **ID Number** - National ID number
2. **Old ID Number** - Legacy ID if applicable
3. **Full Name** - Person's full name
4. **Date of Birth** - DOB format varies (typically DD/MM/YYYY)
5. **Sex** - Gender (M/F)
6. **Address** - Residential address
7. **Issue Date** - Date QR was issued

---

## Example Usage

### Upload file via curl
```bash
curl -X POST http://localhost:8000/decode/file \
  -F "file=@/path/to/cccd.png"
```

### Decode from container path
```bash
curl -X POST http://localhost:8000/decode/path \
  -H "Content-Type: application/json" \
  -d '{"image_path":"/app/asset/image.png"}'
```

### Get current image
```bash
curl http://localhost:8000/current-detect-image
```

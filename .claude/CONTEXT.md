# Project Context

## Project Overview
**detectQRCCCD** is a Vietnamese national ID (Căn cước công dân - CCCD) QR code detector and decoder service.

**Purpose:** Extract structured data from CCCD QR codes embedded in Vietnamese ID cards via image processing and computer vision.

**Tech Stack:**
- **Backend:** Python 3.11 with FastAPI + Uvicorn
- **Computer Vision:** OpenCV (cv2), PIL/Pillow, Pillow-HEIF
- **QR Decoding:** zxing-cpp
- **Frontend:** HTML5 with responsive CSS and vanilla JavaScript
- **Deployment:** Docker Compose

---

## Architecture

### Core Components

1. **main.py** - Core QR detection pipeline
   - Image loading and preprocessing
   - QR candidate region detection
   - Image variant generation (8 variants per region)
   - QR decoding and field parsing
   - CLI interface for batch processing

2. **service.py** - FastAPI REST API
   - HTTP endpoints for file upload and path-based decoding
   - Web UI serving
   - Image cache management
   - Error handling and validation

3. **web/index.html** - Frontend UI
   - Responsive layout (mobile/desktop)
   - File upload interface
   - Camera capture support
   - Real-time image preview
   - Decoded data display (raw JSON + formatted fields)

---

## Processing Pipeline

### Detection Workflow (detect_cccd_from_image)

```
1. Deskew Image
   └─ Correct image rotation using Hough line detection

2. Find QR Candidates (3 strategies)
   ├─ Contour-based square detection
   │  └─ Adaptive threshold + morphology at 3 block sizes (11, 21, 31)
   ├─ Finder-pattern detection
   │  └─ QR-like nested square structures (hierarchy depth = 2)
   └─ Grid split (3x3)
      └─ Brute force all 9 regions

3. Preprocess Variants (8 per region)
   ├─ color (original)
   ├─ gray (grayscale)
   ├─ enhanced (CLAHE)
   ├─ sharpened (custom kernel)
   ├─ otsu (thresholded)
   ├─ denoise (FastNLMeans)
   ├─ resize_2x (upscaled)
   └─ resize_3x (upscaled)

4. Attempt QR Decode
   └─ For each (region, variant) pair:
      └─ Try zxingcpp.read_barcodes() filtering QR only
      └─ Return on first success

5. Parse CCCD Fields
   └─ Split raw_data by '|' delimiter
   └─ Map to standardized field names
```

---

## Data Flow

### File Upload Flow
```
User Upload
    ↓
/decode/file endpoint
    ↓
Load image from bytes (PIL → OpenCV BGR)
    ↓
detect_cccd_from_image()
    ↓
Save to runtime/detect/current_detect.jpg (for preview)
    ↓
Return JSON response
```

### Path Decode Flow
```
POST /decode/path with image_path
    ↓
Load image from container filesystem
    ↓
detect_cccd_from_image()
    ↓
Return JSON response (no image save)
```

---

## Key Algorithms

### 1. Deskew (main.py:40-89)
- Detects near-horizontal line segments via Hough transform
- Computes median angle across lines
- Rotates image via affine transform

### 2. QR Candidate Finding (main.py:128-218)
- **Contour-based:** Adaptive threshold → morphology → contour filtering by aspect ratio
- **Finder-pattern:** Detects nested-square structures in contour hierarchy
- **Grid:** Simple 3x3 split as fallback for off-center QR

### 3. Preprocessing (main.py:221-253)
- **CLAHE:** Contrast-limited adaptive histogram equalization
- **Sharpening:** Custom 3×3 kernel
- **Otsu:** Binary thresholding
- **Denoise:** FastNLMeans
- **Upscaling:** 2× and 3× bicubic for small QR codes

---

## Environment Configuration

### Required Variables (docker-compose.yml)
- `APP_HOST` (default: `0.0.0.0`) - Bind address
- `APP_PORT` (default: `8000`) - Container port
- `HOST_PORT` (default: `8000`) - Host-exposed port
- `APP_DOMAIN` (default: `localhost`) - For local DNS/hosts

### Volume Mounts
- `./asset:/app/asset:ro` - Read-only asset directory for `/decode/path`

### Runtime Directory
- `./runtime/detect/` - Stores `current_detect.jpg` (cache of last processed image)

---

## Supported Image Formats
- JPG, JPEG
- PNG
- HEIC, HEIF
- BMP
- TIF, TIFF
- WebP

---

## Error Handling

| Scenario | Response |
|----------|----------|
| Empty file upload | 400 Bad Request |
| Image file not found | 404 Not Found |
| QR not detected | 200 OK with `detected=false` |
| Processing error | 500 Internal Server Error |
| Missing web UI | 404 Not Found |

---

## Performance Considerations

- **Region count:** ~15-20 candidate regions per image (contour + finder + grid)
- **Variant count:** 8 preprocessing variants per region
- **Total attempts:** ~120-160 decode attempts per image worst-case
- **Success factors:** Lighting, focus, QR size (≥1/4 of frame), aspect ratio

---

## Dependencies

### Core
- `numpy` - Array operations
- `opencv-python` - Image processing
- `Pillow` + `pillow-heif` - Image I/O (including HEIC/HEIF)
- `zxing-cpp<3` - QR barcode reading

### API
- `fastapi` - REST framework
- `uvicorn[standard]` - ASGI server
- `python-multipart` - Multipart form parsing

---

## Related Files
- `Dockerfile` - Container image (Python 3.11-slim + OpenCV libs)
- `docker-compose.yml` - Service orchestration
- `requirements.txt` / `requirements.docker.txt` - Dependencies
- `.env.example` - Environment template

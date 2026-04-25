# Data Models & Structures

## Core Python Classes

### CCCD Field Names Constant
**File:** `main.py:13-21`

```python
CCCD_FIELD_NAMES = [
    "ID Number",
    "Old ID Number",
    "Full Name",
    "Date of Birth",
    "Sex",
    "Address",
    "Issue Date",
]
```

**Purpose:** Define standard field labels for QR payload mapping.
**Order:** Matches pipe-separated order in QR data.

---

## Pydantic Models (FastAPI)

### PathRequest
**File:** `service.py:21-22`

```python
class PathRequest(BaseModel):
    image_path: str
```

**Used by:** POST `/decode/path`

**Fields:**
- `image_path` (str, required) - Absolute or relative path to image in container

**Example:**
```json
{
  "image_path": "/app/asset/cccd.png"
}
```

---

## Return Type Structures

### Detection Result Dictionary
**Returned by:** `detect_cccd_from_image()` (main.py:313-359)

```python
{
    "detected": bool,
    "region": str | None,
    "variant": str | None,
    "raw_data": str | None,
    "fields": list[str],
    "mapped": dict[str, str],
}
```

**Field Details:**

| Key | Type | Description |
|-----|------|-------------|
| `detected` | `bool` | True if QR successfully decoded |
| `region` | `str \| None` | Candidate region name (e.g., "contour_21_100_200") |
| `variant` | `str \| None` | Preprocessing variant name (e.g., "enhanced") |
| `raw_data` | `str \| None` | Original pipe-separated QR payload |
| `fields` | `list[str]` | Split fields by '\|' delimiter |
| `mapped` | `dict[str, str]` | Field label → value mapping |

**Example (success):**
```python
{
    "detected": True,
    "region": "finder_pattern_11",
    "variant": "resize_2x",
    "raw_data": "001234567890|ABC123|Nguyen Van A|01/01/1990|M|123 Nguyen Hue|01/01/2020",
    "fields": [
        "001234567890",
        "ABC123",
        "Nguyen Van A",
        "01/01/1990",
        "M",
        "123 Nguyen Hue",
        "01/01/2020"
    ],
    "mapped": {
        "ID Number": "001234567890",
        "Old ID Number": "ABC123",
        "Full Name": "Nguyen Van A",
        "Date of Birth": "01/01/1990",
        "Sex": "M",
        "Address": "123 Nguyen Hue",
        "Issue Date": "01/01/2020"
    }
}
```

**Example (failure):**
```python
{
    "detected": False,
    "region": None,
    "variant": None,
    "raw_data": None,
    "fields": [],
    "mapped": {}
}
```

---

### Parsed CCCD Fields Dictionary
**Returned by:** `parse_cccd_fields()` (main.py:269-293)

```python
{
    "raw_data": str,
    "fields": list[str],
    "mapped": dict[str, str],
}
```

**Field Details:**

| Key | Type | Description |
|-----|------|-------------|
| `raw_data` | `str` | Original pipe-separated string |
| `fields` | `list[str]` | Split by '\|' |
| `mapped` | `dict[str, str]` | Labeled field mapping |

---

### Candidate Crops Dictionary
**Returned by:** `find_qr_candidates()` (main.py:128-218)

```python
dict[str, np.ndarray]
```

**Keys:** Region names (string)
**Values:** Cropped image regions (NumPy BGR arrays)

**Region name format:**
- `contour_{block_size}_{x}_{y}` - Contour-based regions
- `finder_pattern_{block_size}` - Finder-pattern regions
- `grid_{row}_{col}` - Grid-split regions (0-2 for row/col)
- `full` - Full image (no crop)

**Example keys:**
```python
{
    "contour_11_50_100": np.ndarray,
    "contour_11_200_300": np.ndarray,
    "finder_pattern_11": np.ndarray,
    "grid_0_0": np.ndarray,
    "grid_1_1": np.ndarray,
    "full": np.ndarray,
}
```

---

### Preprocessing Variants Dictionary
**Returned by:** `preprocess_variants()` (main.py:221-253)

```python
dict[str, np.ndarray]
```

**Keys:** Variant names (string)
**Values:** Preprocessed images (NumPy arrays, grayscale or BGR)

**Variant details:**

| Key | Shape | Description |
|-----|-------|-------------|
| `color` | (H, W, 3) BGR | Original image (if input was color) |
| `gray` | (H, W) | Grayscale |
| `enhanced` | (H, W) | CLAHE enhanced |
| `sharpened` | (H, W) | Sharpening kernel applied |
| `otsu` | (H, W) | Binary threshold (Otsu) |
| `denoise` | (H, W) | FastNLMeans denoised |
| `resize_2x` | (2H, 2W) | 2× upscaled |
| `resize_3x` | (3H, 3W) | 3× upscaled |

**Example:**
```python
{
    "color": array(1080, 1440, 3),
    "gray": array(1080, 1440),
    "enhanced": array(1080, 1440),
    "sharpened": array(1080, 1440),
    "otsu": array(1080, 1440),
    "denoise": array(1080, 1440),
    "resize_2x": array(2160, 2880),
    "resize_3x": array(3240, 4320),
}
```

---

### QR Decode Result (zxingcpp)
**Returned by:** `zxingcpp.read_barcodes()`

**Type:** List of barcode objects

**Filtered by:** `try_decode_qr_only()` (main.py:256-266)

**Attributes:**
- `.format` - Barcode format (e.g., "QR_CODE")
- `.text` - Decoded payload string
- `.position` - Bounding box coordinates

**Example:**
```python
# Before filtering:
results = [
    BarcodeResult(format="QR_CODE", text="...|...|...", ...),
    BarcodeResult(format="CODE_128", text="...", ...),
]

# After filtering (QR only):
qr_results = [
    BarcodeResult(format="QR_CODE", text="...|...|...", ...),
]
```

---

## NumPy Image Arrays

### Shape Conventions
- **BGR (OpenCV):** `(height, width, 3)` - uint8, range 0-255
- **Grayscale:** `(height, width)` - uint8, range 0-255
- **Binary (Otsu):** `(height, width)` - uint8, values 0 or 255

### Channel Order
- **Input formats:** JPEG, PNG, etc. use RGB
- **Conversion:** RGB → BGR via `cv2.cvtColor(img, cv2.COLOR_RGB2BGR)`
- **Storage:** Always BGR internally (OpenCV convention)

---

## API Request/Response Models

### File Upload Request
**Endpoint:** POST `/decode/file`

```
Content-Type: multipart/form-data
form data:
  file: <binary image bytes>
```

### File Upload Response (JSON)
```python
{
    "filename": str,
    "current_image_url": str,
    "detected": bool,
    "region": str | None,
    "variant": str | None,
    "raw_data": str | None,
    "fields": list[str],
    "mapped": dict[str, str],
}
```

### Path Decode Request
**Endpoint:** POST `/decode/path`

```json
{
    "image_path": "/app/asset/image.png"
}
```

### Path Decode Response (JSON)
```python
{
    "image_path": str,
    "detected": bool,
    "region": str | None,
    "variant": str | None,
    "raw_data": str | None,
    "fields": list[str],
    "mapped": dict[str, str],
}
```

### Health Check Response
**Endpoint:** GET `/health`

```json
{
    "status": "ok"
}
```

---

## File I/O Types

### Supported Image Formats
- **Input:** JPG, JPEG, PNG, HEIC, HEIF, BMP, TIF, TIFF, WebP
- **Output:** JPG (cached preview via `/current-detect-image`)
- **Codec:** PIL (Pillow) for loading; OpenCV for processing; cv2.imencode for JPG output

### Path Handling
- **CLI:** Uses `pathlib.Path` with `expanduser().resolve()`
- **API:** Accepts relative/absolute paths, resolves to absolute
- **Container:** Mount point is `/app/asset:ro` (read-only)

---

## Type Hints (main.py)

```python
from typing import Any
from pathlib import Path
import numpy as np

# Core type signatures
def load_image(image_path: Path) -> np.ndarray: ...
def deskew(img: np.ndarray) -> np.ndarray: ...
def find_finder_patterns(binary_img: np.ndarray) -> list[tuple[int, int, int, int]]: ...
def find_qr_candidates(img: np.ndarray) -> dict[str, np.ndarray]: ...
def preprocess_variants(img: np.ndarray) -> dict[str, np.ndarray]: ...
def try_decode_qr_only(img: np.ndarray) -> list[Any]: ...
def parse_cccd_fields(raw_data: str) -> dict[str, Any]: ...
def detect_cccd_from_image(img: np.ndarray) -> dict[str, Any]: ...
def read_qr_from_cccd(image_path: Path) -> bool: ...
def gather_image_paths(inputs: list[str]) -> list[Path]: ...
```

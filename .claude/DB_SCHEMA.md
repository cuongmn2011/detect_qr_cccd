# Data Schema & Structures

## CCCD Field Structure

### Input: Raw QR Payload
Pipe-separated string from QR code:
```
<id_number>|<old_id_number>|<full_name>|<dob>|<sex>|<address>|<issue_date>
```

**Example:**
```
001234567890|ABC123|Nguyen Van A|01/01/1990|M|123 Nguyen Hue, HCMC|01/01/2020
```

---

## Response Schema

### Detection Result (JSON)

**Base Structure:**
```json
{
  "detected": boolean,
  "region": string | null,
  "variant": string | null,
  "raw_data": string | null,
  "fields": [string],
  "mapped": object
}
```

**Field Descriptions:**

| Field | Type | Description |
|-------|------|-------------|
| `detected` | boolean | Whether QR was successfully decoded |
| `region` | string \| null | Name of crop region where QR was found (e.g., "contour_21_100_200", "finder_pattern_11", "grid_1_1", "full") |
| `variant` | string \| null | Name of preprocessing variant used (e.g., "enhanced", "otsu", "resize_3x") |
| `raw_data` | string \| null | Original pipe-separated QR payload |
| `fields` | array | Split field values by '\|' delimiter |
| `mapped` | object | Named field mapping (see below) |

---

### Mapped Fields Object

When QR is detected (`detected=true`), `mapped` contains:

```json
{
  "ID Number": "string",
  "Old ID Number": "string",
  "Full Name": "string",
  "Date of Birth": "string",
  "Sex": "string",
  "Address": "string",
  "Issue Date": "string"
}
```

**Field Order (index in `fields` array):**
- Index 0 → "ID Number"
- Index 1 → "Old ID Number"
- Index 2 → "Full Name"
- Index 3 → "Date of Birth"
- Index 4 → "Sex"
- Index 5 → "Address"
- Index 6 → "Issue Date"

Extra fields (index ≥ 7) are mapped as "Field {i+1}".

---

## API Request/Response Examples

### POST /decode/file

**Request:**
```
Content-Type: multipart/form-data
file: <binary image data>
```

**Response 200 (Success):**
```json
{
  "filename": "cccd-scan.png",
  "current_image_url": "/current-detect-image?t=1713974400000",
  "detected": true,
  "region": "contour_21_150_200",
  "variant": "enhanced",
  "raw_data": "001234567890|ABC123|Nguyen Van A|01/01/1990|M|123 Nguyen Hue, HCMC|01/01/2020",
  "fields": [
    "001234567890",
    "ABC123",
    "Nguyen Van A",
    "01/01/1990",
    "M",
    "123 Nguyen Hue, HCMC",
    "01/01/2020"
  ],
  "mapped": {
    "ID Number": "001234567890",
    "Old ID Number": "ABC123",
    "Full Name": "Nguyen Van A",
    "Date of Birth": "01/01/1990",
    "Sex": "M",
    "Address": "123 Nguyen Hue, HCMC",
    "Issue Date": "01/01/2020"
  }
}
```

**Response 200 (Not Detected):**
```json
{
  "filename": "bad-image.png",
  "current_image_url": "/current-detect-image?t=1713974500000",
  "detected": false,
  "region": null,
  "variant": null,
  "raw_data": null,
  "fields": [],
  "mapped": {}
}
```

---

### POST /decode/path

**Request:**
```json
{
  "image_path": "/app/asset/cccd.png"
}
```

**Response 200:**
```json
{
  "image_path": "/app/asset/cccd.png",
  "detected": true,
  "region": "grid_1_1",
  "variant": "resize_2x",
  "raw_data": "...",
  "fields": [...],
  "mapped": {...}
}
```

---

## CLI Output Schema

### Python Script (main.py)

**Stdout (on success):**
```
[OK] Loaded image: /path/to/image.jpg | shape=(1080, 1440, 3)

[1/3] Deskew image...
  -> Deskew rotation: -2.34 degrees

[2/3] Find QR candidate regions...
  -> Finder-pattern region: (100,150) -> (800,900)
  -> Total candidate regions: 17

[3/3] Decode candidates...

[SUCCESS] QR detected (region=contour_21_150_200, variant=enhanced)

Raw data: 001234567890|ABC123|Nguyen Van A|01/01/1990|M|123 Nguyen Hue, HCMC|01/01/2020

CCCD data:
----------------------------------------
  ID Number: 001234567890
  Old ID Number: ABC123
  Full Name: Nguyen Van A
  Date of Birth: 01/01/1990
  Sex: M
  Address: 123 Nguyen Hue, HCMC
  Issue Date: 01/01/2020
----------------------------------------
```

**Stdout (on failure):**
```
[OK] Loaded image: /path/to/image.jpg | shape=(1080, 1440, 3)

[1/3] Deskew image...

[2/3] Find QR candidate regions...
  -> Total candidate regions: 9

[3/3] Decode candidates...

[FAILED] QR code not found.
Hint: Ensure enough light, avoid blur, and keep QR at least 1/4 of frame.
```

---

## Image Processing Metadata

### Region Names (detection sources)

**Contour-based:**
- Format: `contour_{block_size}_{x}_{y}`
- Examples: `contour_11_50_100`, `contour_21_300_400`, `contour_31_0_0`
- Block sizes: 11, 21, 31 (adaptive threshold parameters)

**Finder-pattern:**
- Format: `finder_pattern_{block_size}`
- Examples: `finder_pattern_11`, `finder_pattern_21`
- Size: Bounding box of all 3 nested squares + 20% padding

**Grid:**
- Format: `grid_{row}_{col}`
- Examples: `grid_0_0` (top-left), `grid_1_1` (center), `grid_2_2` (bottom-right)
- Count: Always 9 regions (3×3)

**Full image:**
- Format: `full`
- No cropping, full resolution

### Variant Names (preprocessing methods)

| Name | Description |
|------|-------------|
| `color` | Original BGR image |
| `gray` | Grayscale conversion |
| `enhanced` | CLAHE (contrast-limited adaptive histogram equalization) |
| `sharpened` | Sharpening kernel applied to enhanced |
| `otsu` | Binary thresholding with Otsu's method |
| `denoise` | FastNLMeans denoising |
| `resize_2x` | 2× upscaling via bicubic interpolation |
| `resize_3x` | 3× upscaling via bicubic interpolation |

---

## Image Caching

### Runtime Directory Structure
```
./runtime/detect/
└── current_detect.jpg
    ├── Created on first upload
    ├── Replaced on each new upload
    ├── Served via /current-detect-image endpoint
    └── Timestamp in URL (?t=...) bypasses browser cache
```

---

## Error Response Schema

**HTTP 400 (Bad Request):**
```json
{
  "detail": "Empty file"
}
```

**HTTP 404 (Not Found):**
```json
{
  "detail": "Image not found: /path/to/missing.jpg"
}
```

**HTTP 500 (Internal Server Error):**
```json
{
  "detail": "Cannot encode image for preview"
}
```

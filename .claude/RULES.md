# Development Rules & Guidelines

## Code Style & Conventions

### Python Version
- **Target:** Python 3.11+ (f-strings, type hints, match statements allowed)
- **Minimum:** 3.11-slim Docker image
- **Convention:** Follow PEP 8 with these adjustments:
  - Line length: 100 chars (project uses longer lines in some places)
  - Type hints: Required for function signatures
  - Docstrings: Include for public functions, use triple quotes

### Imports
- **Order:** Standard library → Third-party → Local
- **Grouping:** Use blank lines between groups
- **Unused imports:** Remove immediately

```python
# Good
from pathlib import Path
import cv2
import numpy as np
from fastapi import FastAPI

from main import detect_cccd_from_image
```

### Function Documentation
- **Style:** Docstrings with Args, Returns sections
- **Length:** Keep to 2-3 lines for simple functions
- **Example from codebase:**

```python
def load_image(image_path: Path) -> np.ndarray:
    """Load an image from disk and convert it to OpenCV BGR format.

    Args:
        image_path: Absolute or relative path to an image file.

    Returns:
        A NumPy ndarray in BGR channel order with shape (H, W, 3).
    """
```

---

## Image Processing Rules

### Array Conventions
- **Always use OpenCV BGR format** internally (not RGB)
- **Shape:** (height, width, 3) for color, (height, width) for grayscale
- **Data type:** uint8 (8-bit unsigned integer, range 0-255)
- **Conversion:** Use `cv2.cvtColor()` for color space changes

**Example:**
```python
pil_img = Image.open(path).convert("RGB")
img = np.array(pil_img)
img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)  # ← Always convert to BGR
```

### Threshold & Binary Operations
- **Binary images:** Use 255 for white, 0 for black
- **Otsu thresholding:** Use `cv2.THRESH_OTSU` for automatic threshold selection
- **Morphological operations:** Use `cv2.MORPH_CLOSE` for noise reduction

---

## API Design Rules

### Response Structure
- **Always include:** `detected`, `region`, `variant`, `raw_data`, `fields`, `mapped`
- **On failure:** Use `detected=false` with null/empty values (NOT error response)
- **On error:** Use appropriate HTTP status code (400, 404, 500)

```python
# Good - detection failure
{
    "detected": False,
    "region": None,
    "variant": None,
    "raw_data": None,
    "fields": [],
    "mapped": {}
}

# Good - HTTP error
raise HTTPException(status_code=400, detail="Empty file")
```

### HTTP Status Codes
| Code | Scenario |
|------|----------|
| 200 | Success (detected=true or false) |
| 400 | Bad Request (empty file, invalid params) |
| 404 | Not Found (missing image, missing web UI) |
| 500 | Server Error (processing failure) |

### Error Handling
- **Catch HTTPException separately** to re-raise as-is
- **Catch generic Exception** to wrap as 500 error
- **Always include detail message** for debugging

```python
try:
    # Processing
except HTTPException:
    raise  # Re-raise HTTP errors unchanged
except Exception as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc
```

---

## QR Decoding Rules

### Field Parsing
- **Delimiter:** Pipe character `|` (U+007C)
- **Standard count:** 7 fields (CCCD specification)
- **Order:** ID Number, Old ID, Full Name, DOB, Sex, Address, Issue Date
- **Extra fields:** Map to "Field N" if count > 7

### Variant Selection
- **Try all variants** before declaring failure
- **Order doesn't matter** (any working variant is acceptable)
- **Success criteria:** At least one QR code detected, format is QR_CODE

**Current implementation (main.py:334-350):**
```python
for crop_name, cropped in crops.items():
    variants = preprocess_variants(cropped)
    for variant_name, variant_img in variants.items():
        qr_results = try_decode_qr_only(variant_img)
        if qr_results:
            # Return immediately on first success
            result = qr_results[0]
            parsed = parse_cccd_fields(result.text)
            return {
                "detected": True,
                "region": crop_name,
                "variant": variant_name,
                ...
            }
```

### Region Prioritization (current)
- **No explicit priority** - try regions in order they're generated
- **Contour-based:** Generated first
- **Finder-pattern:** Generated next
- **Grid:** Generated last
- **Full image:** Fallback at end

---

## Docker & Deployment Rules

### Image Dependencies
- **Base:** `python:3.11-slim` (minimal runtime)
- **Required system libraries:** libglib2.0-0, libgomp1, libgl1 (OpenCV dependencies)
- **Do NOT use:** ubuntu/debian base (too large)

### Environment Variables
- **APP_HOST:** Default 0.0.0.0 (bind all interfaces)
- **APP_PORT:** Default 8000 (internal port)
- **HOST_PORT:** Default 8000 (exposed port)
- **APP_DOMAIN:** Default localhost (for documentation)

### Volume Mounts
- **./asset:/app/asset:ro** - Read-only asset directory for `/decode/path`
- **Never mount as read-write** - prevents accidental modification
- **Runtime dir:** ./runtime/detect/ (auto-created if missing)

---

## Performance Targets

### Detection Latency
- **Target:** < 5 seconds per image (on typical hardware)
- **Typical:** 2-3 seconds
- **Worst-case:** 10+ seconds (many candidate regions)

### Memory Usage
- **Per image:** ~100-200 MB (including OpenCV buffers)
- **Cache:** 1 JPG file (~200 KB)
- **No memory leaks expected** (garbage collection handles)

### Optimization Opportunities (future)
- Profile slow phases (deskew, candidate finding, preprocessing)
- Consider removing redundant preprocessing variants
- Early termination if high-confidence region found

---

## Testing Rules

### Edge Cases to Test
- ✓ Empty file upload (should return 400)
- ✓ Missing image path (should return 404)
- ✓ Corrupted image data (should return 500)
- ✓ QR with fewer than 7 fields (should still parse)
- ✓ QR with more than 7 fields (should map extra fields)
- ✓ Rotated images (deskew should handle)
- ✓ Low contrast images (preprocessing should help)
- ✓ Multiple consecutive uploads (image cache should update)

### Supported Formats to Verify
- [ ] JPEG (common)
- [ ] PNG (common)
- [ ] WebP (modern)
- [ ] HEIC/HEIF (iOS)
- [ ] BMP (legacy)
- [ ] TIFF (professional)

---

## Logging & Debugging Rules

### CLI Output (main.py)
- Use `print()` for user-facing messages
- Prefix with `[OK]`, `[ERROR]`, `[SUCCESS]`, `[FAILED]`
- Include numeric status indicators `[1/3]`
- Print progress even if it seems verbose

**Good examples from codebase:**
```python
print(f"[OK] Loaded image: {image_path} | shape={img.shape}")
print(f"  -> Deskew rotation: {median_angle:.2f} degrees")
print(f"  -> Total candidate regions: {len(crops)}")
print("[FAILED] QR code not found.")
```

### API Logging (service.py)
- No logging currently (room for improvement)
- Future: Add request ID, method, path, status code
- Consider using Python `logging` module instead of print

---

## Dependency Management Rules

### Version Pinning
- **zxingcpp:** Pinned to `<3` (breaking API change in v3)
- **Other dependencies:** No upper bounds (use latest)
- **Docker:** Explicitly upgrade pip: `pip install --upgrade pip setuptools wheel`

### Removing Dependencies
- Never remove without justification (reduces complexity)
- Deprecated libraries should be replaced, not removed
- Document in commit message why dependency was removed

---

## Security Rules

### Input Validation
- ✓ Check empty file before processing
- ✓ Validate file path exists before reading
- ✓ Use `Path().expanduser().resolve()` to prevent path traversal
- ✓ Mount asset dir as read-only (prevents writes)
- ✓ Should add: File size limits, magic byte validation

### Error Messages
- ✓ Don't expose internal paths in API errors (use generic messages)
- ✓ Do log full errors server-side for debugging
- ✓ Should add: Rate limiting, authentication (for production)

### No HTTPS/TLS Handling
- Current design: Assumes reverse proxy handles HTTPS
- Web UI camera requires HTTPS or localhost
- Docker service binds to HTTP only (correct design)

---

## Documentation Rules

### Code Comments
- Avoid redundant comments (code should be self-documenting)
- Document WHY, not WHAT
- Comment complex algorithms (e.g., Hough line detection, contour hierarchy)

### Markdown Documentation
- Use `.md` files in `.claude/` directory
- Separate concerns (API, schema, issues, context, models, rules)
- Include code examples where helpful
- Keep up-to-date as code changes

### README.md
- Audience: End users and operators
- Include: Setup, usage examples, troubleshooting
- Currently in Vietnamese (acceptable for local audience)

---

## Change Management

### Adding Features
- Discuss approach first (performance, complexity, breaking changes)
- Update relevant documentation before/after
- Test edge cases thoroughly
- Verify no regressions in other features

### Bug Fixes
- Reproduce issue first
- Write test case (if applicable)
- Fix root cause (not symptoms)
- Document in KNOWN_ISSUES.md before fixing

### Deprecation
- Warn users with documentation
- Provide migration path
- Set removal timeline
- Document in INVESTIGATION_LOG.md

---

## Related Documentation
- See [API_ENDPOINTS.md](API_ENDPOINTS.md) for endpoint specifications
- See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for current bugs/limitations
- See [CONTEXT.md](CONTEXT.md) for architecture overview

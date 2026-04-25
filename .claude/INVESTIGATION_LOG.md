# Investigation Log

## Areas to Monitor / Investigate

### 1. QR Detection Success Rate
**Status:** Investigate  
**Priority:** High

**Questions:**
- What is the baseline success rate across different lighting conditions?
- Which preprocessing variants are most effective?
- Are contour-based, finder-pattern, or grid-split strategies dominant?

**Metrics to track:**
- Success rate by image quality (good lighting, poor lighting, blur, rotation)
- Average region count per image
- Region type distribution (contour vs finder vs grid)
- Preprocessing variant success distribution

**Implementation notes:**
- Add metrics logging to `detect_cccd_from_image()` return
- Track which (region, variant) combinations succeed
- Consider performance vs accuracy tradeoffs

---

### 2. Performance Bottlenecks
**Status:** Investigate  
**Priority:** Medium

**Observations:**
- Currently attempts ~120-160 decode iterations per image (worst-case)
- Candidate region detection involves 3 different thresholding strategies with 3 block sizes

**Questions:**
- How much time is spent in each phase (deskew, candidate finding, preprocessing, decoding)?
- Can early termination reduce latency without hurting accuracy?
- Is the 3×3 grid necessary if contour + finder patterns are sufficient?

**Candidates for optimization:**
- Profile main processing phases
- Consider removing redundant block size iterations
- Evaluate early termination (stop after first success in high-confidence regions)

---

### 3. Image Format Compatibility
**Status:** Investigate  
**Priority:** Medium

**Current support:**
- JPG, JPEG, PNG, HEIC, HEIF, BMP, TIF, TIFF, WebP (via PIL + Pillow-HEIF)

**Questions:**
- Are HEIC/HEIF files being properly decoded to BGR?
- Are there edge cases in format handling (color space, orientation metadata)?
- Should EXIF orientation be auto-corrected?

**Testing needed:**
- Real HEIC/HEIF files from iPhones
- Rotated images with EXIF metadata
- Corrupted/partial image data

---

### 4. QR Parsing Robustness
**Status:** Investigate  
**Priority:** Medium

**Current implementation (main.py:269-293):**
```python
fields = raw_data.strip().split("|")
mapped = {}
for i, value in enumerate(fields):
    label = CCCD_FIELD_NAMES[i] if i < len(CCCD_FIELD_NAMES) else f"Field {i + 1}"
    mapped[label] = value
```

**Edge cases not yet tested:**
- QR with missing fields (fewer than 7 fields)
- QR with extra fields (more than 7)
- Fields containing pipes or special characters
- Empty fields (e.g., `...||...` resulting in empty strings)
- Non-UTF-8 encoded QR data

**Recommendations:**
- Add validation for minimum field count
- Test with malformed QR data
- Define expected data types per field (e.g., ID should be numeric)

---

### 5. Camera Support in Web UI
**Status:** Investigate  
**Priority:** Low

**Current implementation:**
- JavaScript `getUserMedia()` for camera access
- Photo capture → canvas → form submission
- Requires HTTPS or localhost

**Questions:**
- Does camera work reliably across browsers (Chrome, Firefox, Safari)?
- Mobile vs desktop capture differences?
- Permissions handling on iOS/Android?

**Browser compatibility:**
- Chrome/Edge: Full support
- Firefox: Full support
- Safari: May require HTTPS
- Mobile Safari (iOS): May require HTTPS

---

### 6. Docker Environment
**Status:** Investigate  
**Priority:** Medium

**Current setup (Dockerfile):**
- Python 3.11-slim base
- OpenCV runtime dependencies (libgl1, libglib2.0-0, libgomp1)
- Mounts `./asset` as read-only

**Questions:**
- Are all OpenCV dependencies installed correctly?
- Does the image size need optimization?
- Should requirements.txt and requirements.docker.txt be identical?

**Observations:**
- `requirements.docker.txt` is referenced in Dockerfile but not shown in current repo
- May be missing or identical to `requirements.txt`

---

### 7. Image Rotation & Orientation
**Status:** Investigate  
**Priority:** Medium

**Current deskew implementation (main.py:40-89):**
- Detects near-horizontal line segments (Hough transform)
- Computes median angle
- Rotates if |angle| > 0.5°

**Limitations:**
- Only handles in-plane rotation (skew)
- Doesn't handle EXIF orientation metadata
- May fail if QR area has few horizontal lines
- Doesn't correct perspective distortion

**Edge cases:**
- Highly skewed images (>45° rotation) might not be corrected
- Images with QR at corners (perspective) won't be deskewed
- EXIF rotation metadata ignored (PIL should handle auto-rotation)

---

### 8. Web UI Responsiveness
**Status:** Investigate  
**Priority:** Low

**Observations:**
- CSS uses responsive breakpoints (760px)
- Mobile-first design with grid layout
- Camera modal overlay

**Questions:**
- Does layout work on very small screens (<320px)?
- Are touch targets large enough (≥44px) for mobile?
- Is text readable without zoom?

---

## Completed Investigations

### ✓ Endpoint Routing
- Verified all 5 endpoints are functional
- `/decode/file` handles multipart uploads
- `/decode/path` handles container paths
- `/current-detect-image` serves cached JPG
- `/health` for monitoring

### ✓ Preprocessing Variants
- Confirmed 8 variants generated per region
- CLAHE parameters: clipLimit=3.0, tileGridSize=(8,8)
- Sharpening kernel: 3×3 with center=5
- Denoise: FastNLMeans with h=10

### ✓ Dependency Compatibility
- All imports resolve correctly (cv2, PIL, zxingcpp)
- zxingcpp version pinned to <3 (breaking API change in v3)
- Pillow-HEIF properly registers HEIC opener

---

## Next Steps

1. **Profile execution time** - instrument detect_cccd_from_image() with timestamps
2. **Log variant success rates** - track which preprocessing variants yield detections
3. **Test edge cases** - empty fields, truncated QR, low contrast images
4. **Verify mobile camera** - test camera capture on iOS/Android
5. **Monitor Docker** - check image size, startup time, memory usage

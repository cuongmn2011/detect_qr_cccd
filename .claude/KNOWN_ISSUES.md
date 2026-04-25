# Known Issues

## Critical Issues

### None documented yet
Current codebase appears stable for primary use cases.

---

## High Priority Issues

### 1. Missing `requirements.docker.txt`
**Severity:** High  
**Status:** Unresolved

**Description:**
- `Dockerfile` references `requirements.docker.txt` but file is not in repository
- Currently would cause Docker build failure

**Impact:**
- `docker compose up` will fail immediately

**Solution Options:**
1. Create `requirements.docker.txt` (copy from `requirements.txt`)
2. Update Dockerfile to use `requirements.txt` instead
3. Use separate file if Docker needs different dependencies

**Recommended fix:**
```bash
cp requirements.txt requirements.docker.txt
```

---

## Medium Priority Issues

### 2. No Validation on QR Field Count
**Severity:** Medium  
**Status:** Unresolved

**Description:**
- `parse_cccd_fields()` assumes 7 fields (current CCCD spec)
- If QR contains fewer fields, missing ones won't appear in `mapped` dict
- If QR contains extra fields, they're generic-named "Field N"

**Current behavior:**
```python
fields = raw_data.strip().split("|")  # Could be 5, 7, 10, etc.
mapped = {}
for i, value in enumerate(fields):
    label = CCCD_FIELD_NAMES[i] if i < len(CCCD_FIELD_NAMES) else f"Field {i + 1}"
    mapped[label] = value
```

**Issue:**
- If QR has only 5 fields: `mapped` will only have 5 keys (correct behavior, but silent)
- No warning or error raised
- Frontend won't know if data is incomplete

**Recommendation:**
- Add field count validation
- Warn if field count != 7
- Consider raising error for < 7 fields (invalid CCCD)

---

### 3. EXIF Orientation Not Handled
**Severity:** Medium  
**Status:** Unresolved

**Description:**
- Images from phones often have EXIF rotation metadata
- PIL's `Image.open()` in `main.py:33` doesn't auto-correct orientation
- Only in-plane skew is corrected via Hough line detection

**Current code (main.py:33):**
```python
pil_img = Image.open(image_path).convert("RGB")
img = np.array(pil_img)
img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
# EXIF rotation metadata is ignored here
```

**Impact:**
- Images rotated 90°/180°/270° won't be auto-corrected
- Detection may fail for rotated photos

**Workaround:**
- PIL.Image.Exif().transpose() can handle EXIF orientation
- Should apply before converting to BGR

**Recommended fix:**
```python
from PIL import ImageOps
pil_img = Image.open(image_path).convert("RGB")
pil_img = ImageOps.exif_transpose(pil_img)  # Auto-correct rotation
img = np.array(pil_img)
```

---

### 4. No Error Recovery for Partial Image Upload
**Severity:** Medium  
**Status:** Unresolved

**Description:**
- If multipart upload is interrupted, service may receive partial/corrupt image
- `Image.open()` in `service.py:26` will raise exception
- Exception is caught and returns 500, but no graceful degradation

**Current behavior:**
```python
try:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    img = _load_image_from_bytes(raw)  # Can fail here
    ...
except HTTPException:
    raise
except Exception as exc:
    raise HTTPException(status_code=500, detail=str(exc))
```

**Improvement:**
- Validate image bytes before processing (magic bytes check)
- Return 400 (Bad Request) instead of 500 for invalid image data
- Log detailed error for debugging

---

## Low Priority Issues

### 5. Runtime Directory Not Cleaned on Startup
**Severity:** Low  
**Status:** Unresolved

**Description:**
- `./runtime/detect/` directory persists between service restarts
- Old `current_detect.jpg` files might accumulate
- Currently `_clear_detect_cache()` only clears on upload, not on startup

**Impact:**
- Minor: Storage accumulation (one JPG file = ~100-500 KB)
- Could be problematic on long-running services with thousands of uploads

**Recommendation:**
- Clear runtime cache on app startup (in FastAPI `@app.on_event("startup")`)
- Or implement auto-expiration (delete files older than N hours)

---

### 6. No Rate Limiting
**Severity:** Low  
**Status:** Unresolved

**Description:**
- API has no rate limiting on `/decode/*` endpoints
- Service could be abused with high-volume requests
- No authentication/authorization

**Current behavior:**
- Anyone with network access can call endpoints unlimited times
- No throttling or quota system

**Recommendation for production:**
- Add rate limiting (e.g., 10 requests/minute per IP)
- Require API key or authentication
- Implement request size limits (max file upload size)

---

### 7. Web UI Image Preview Caching
**Severity:** Low  
**Status:** Unresolved

**Description:**
- Browser aggressively caches image responses (despite `?t=timestamp` parameter)
- Multiple uploads in quick succession might show old preview

**Current code (service.py:53):**
```python
return f"/current-detect-image?t={int(time.time() * 1000)}"
```

**Issue:**
- Timestamp is in milliseconds but might not invalidate all caches
- Some proxies/CDNs might ignore query parameters

**Improvement:**
- Add Cache-Control headers in response
- Or use ETags with file modification time

---

### 8. Incorrect Field Mapping for Extra Fields
**Severity:** Low  
**Status:** Unresolved

**Description:**
- If QR has > 7 fields, extra fields are named "Field 8", "Field 9", etc.
- No way to know what those fields represent
- Likely won't happen with standard CCCD, but should document

**Recommendation:**
- Document expected field count (always 7 for CCCD v1)
- Warn if field count deviates

---

### 9. No Logging for Debug
**Severity:** Low  
**Status:** Unresolved

**Description:**
- `main.py` uses `print()` for output (CLI-focused)
- `service.py` has no logging at all
- Makes debugging production issues difficult

**Recommendation:**
- Add proper logging module (stdlib `logging` or `loguru`)
- Log request IDs, detection attempts, failures
- Different log levels (DEBUG, INFO, WARNING, ERROR)

---

### 10. Web UI Doesn't Show Processing Progress
**Severity:** Low  
**Status:** Unresolved

**Description:**
- File upload → decode can take 5-10 seconds
- Frontend shows no progress bar or status
- User might think it's frozen

**Recommendation:**
- Show loading spinner during processing
- Could add `/decode/status/{task_id}` for async progress tracking

---

## Closed Issues

### None yet

---

## Issue Tracking

**To report a new issue:**
1. Document in this file with Severity, Status, Description, Impact, Recommendation
2. Provide code examples where relevant
3. Link to related code locations (file:line)
4. Update status as investigation/fixes progress

**Severity levels:**
- **Critical** - Service breaking, security risk, data loss
- **High** - Major feature broken, workaround difficult
- **Medium** - Feature partially broken, edge case issue
- **Low** - Minor UX issue, optimization opportunity

**Status levels:**
- **Unresolved** - Acknowledged, not yet fixed
- **In Progress** - Being worked on
- **Fixed** - Resolved, PR merged
- **Won't Fix** - Intentional decision to leave as-is

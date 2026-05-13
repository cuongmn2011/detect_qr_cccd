# Plan: Upgrade WeChat QRCode Detection with ML Model Files

## Context

Notebook `OpenCV_QRChat.ipynb` demonstrates that initializing `cv2.wechat_qrcode.WeChatQRCode()` WITH 4 model files (detect.prototxt, detect.caffemodel, sr.prototxt, sr.caffemodel) boosts accuracy from 37.5% → 58.3% (7/12 images).

The current `main.py:20` uses a bare `WeChatQRCode()` call with no model files, which disables ML-based detection and super-resolution upsampling. This plan wires in the model files properly while keeping Strategy 2 (zxingcpp) as the fallback.

---

## Critical Files

| File | Change |
|------|--------|
| `main.py` | Add `import os`, replace WeChat init block, add `detect_mode` parameter to `detect_cccd_from_image()` |
| `run.py` | Insert model download + env var before module imports |
| `service.py` | Add `detect_mode` param to API endpoints, add UI buttons |
| `tasks.py` | Add `detect_mode` param to Celery task |
| `web/index.html` | Add "Fast-Detect" / "Deep-Detect" buttons |
| `model_loader.py` | **New file** — download helper |
| `.gitignore` | Add `models/` |

---

## Step 1 — Download and store model files NOW

Run this script once to download all 4 model files:

```bash
python -c "
import urllib.request
from pathlib import Path

BASE_URL = 'https://raw.githubusercontent.com/WeChatCV/opencv_3rdparty/wechat_qrcode/'
FILES = ['detect.prototxt', 'detect.caffemodel', 'sr.prototxt', 'sr.caffemodel']
MODEL_DIR = Path('models/wechat_qrcode')
MODEL_DIR.mkdir(parents=True, exist_ok=True)

for filename in FILES:
    dest = MODEL_DIR / filename
    if dest.exists():
        print(f'[skip] {filename} already exists')
        continue
    url = BASE_URL + filename
    print(f'[download] {filename} ...', end=' ')
    urllib.request.urlretrieve(url, dest)
    size_kb = dest.stat().st_size // 1024
    print(f'OK ({size_kb} KB)')

print('Done. Models are ready.')
"
```

Or manually:
1. Create folder: `mkdir models/wechat_qrcode`
2. Download 4 files from https://github.com/WeChatCV/opencv_3rdparty/tree/wechat_qrcode
3. Save to `models/wechat_qrcode/`

Models will be committed to git and bundled with the project.

---

## Step 2 — Create `model_loader.py` (simplified - just loads existing models)

Simplified module that only loads models (no download logic):

```python
"""Load WeChat QRCode model files from local storage."""
import os
import sys
from pathlib import Path

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):   # PyInstaller EXE
        return Path(sys.executable).parent
    return Path(__file__).parent        # source mode

def get_model_dir() -> Path:
    """Return path to models/wechat_qrcode directory."""
    return _base_dir() / "models" / "wechat_qrcode"

def models_available() -> bool:
    """Check if all 4 model files exist."""
    model_dir = get_model_dir()
    files = ["detect.prototxt", "detect.caffemodel", "sr.prototxt", "sr.caffemodel"]
    return all((model_dir / f).exists() for f in files)

def get_model_paths() -> dict:
    """Return dict of {filename: full_path} for all 4 models."""
    model_dir = get_model_dir()
    return {
        "detect_proto": str(model_dir / "detect.prototxt"),
        "detect_model": str(model_dir / "detect.caffemodel"),
        "sr_proto": str(model_dir / "sr.prototxt"),
        "sr_model": str(model_dir / "sr.caffemodel"),
    }
```

---

## Step 3 — Modify `run.py` to pass model dir via env var

Insert this **before** importing modules:

```python
# After line 17: os.environ["REDIS_URL"] = REDIS_URL
# BEFORE line 20: import uvicorn

# ============================================================================
# Set WeChat QRCode model directory (models are already checked in to git)
# ============================================================================
from model_loader import get_model_dir
os.environ["WECHAT_MODEL_DIR"] = str(get_model_dir())
# Now proceed with module imports ↓
import uvicorn
```

Why env var? `main.py` initializes WeChat at module-level (line 19), before any function call. An env var is the only way to pass config into that block without changing import order.

---

## Step 3 — Modify `main.py`

**Line 1** — add `import os` (currently missing):
```python
import os          # add this line
import argparse
import logging
```

**Lines 19–25** — replace bare WeChat init with model-aware init:

```python
# Initialize WeChat QRCode detector (Deep Learning based)
def _init_wechat():
    try:
        model_dir = os.environ.get("WECHAT_MODEL_DIR", "")
        if model_dir:
            from pathlib import Path as _P
            md = _P(model_dir)
            paths = [str(md / f) for f in ["detect.prototxt", "detect.caffemodel", "sr.prototxt", "sr.caffemodel"]]
            if all(os.path.isfile(p) for p in paths):
                det = cv2.wechat_qrcode.WeChatQRCode(*paths)
                logger.info("[WeChat] Initialized WITH model files (ML mode)")
                return det, True
        det = cv2.wechat_qrcode.WeChatQRCode()
        logger.info("[WeChat] Initialized WITHOUT model files (basic mode)")
        return det, True
    except (AttributeError, cv2.error) as e:
        logger.warning(f"[WeChat] Not available: {e}")
        return None, False

detector, WECHAT_AVAILABLE = _init_wechat()
```

**`detect_cccd_from_image()` function** — add `detect_mode` parameter:
```python
def detect_cccd_from_image(img: np.ndarray, debug_dir: Path | None = None, detect_mode: str = "deep") -> dict[str, Any]:
    """
    Detect QR code from CCCD image.
    
    Args:
        img: Input image (numpy array)
        debug_dir: Optional directory to save debug variant images
        detect_mode: "fast" (Strategy 1 only) or "deep" (Strategy 1 + Strategy 2)
                     Default: "deep" for backward compatibility
    
    Returns: dict with keys {detected, region, variant, raw_data, fields, mapped}
    """
    # ... existing deskew code ...
    
    # Strategy 1: WeChat QRCode detector (fast, high accuracy)
    if WECHAT_AVAILABLE:
        result = try_decode_qr_wechat(img)
        if result:
            return {...success dict...}
    
    # Strategy 2: Region-based detection with zxingcpp (only if detect_mode == "deep")
    if detect_mode == "fast":
        return {"detected": False, "region": None, "variant": None, "raw_data": "", "fields": [], "mapped": {}}
    
    # Proceed with Strategy 2 (existing code)
    find_qr_candidates(img)
    # ... rest of existing code ...
```

---

## Step 4 — Update `requirements.txt`

Add a note that model files must be present:

```
# ... existing dependencies ...
opencv-contrib-python>=4.5.0    # required for cv2.wechat_qrcode
# Note: WeChat QRCode model files are pre-downloaded and stored in models/wechat_qrcode/
# If models are missing, run: python -c "..." (see PLAN_OPENCV_QRCHAT.md Step 1)
```

(No new packages needed - models are just binary files, not Python packages)

---

## Step 5 — Modify `tasks.py`

Add `detect_mode` parameter to Celery task:

```python
@celery.task(bind=True, name='detect_qr_task')
def detect_qr_task(self, image_key: str, detect_mode: str = "deep") -> dict:
    """
    Celery task to detect QR from image.
    
    Args:
        image_key: Redis key for image bytes
        detect_mode: "fast" or "deep" detection mode
    """
    # ... existing Redis retrieval code ...
    
    # Pass detect_mode to detection function
    return detect_cccd_from_image(img, detect_mode=detect_mode)
```

---

## Step 5 — Modify `service.py` API endpoints

Add `detect_mode` query parameter to both endpoints:

```python
@app.post("/decode/file")
async def decode_file(file: UploadFile, detect_mode: str = Query("deep", regex="^(fast|deep)$")):
    """
    Upload image file for QR detection.
    
    Query params:
        detect_mode: "fast" (Strategy 1 only) or "deep" (Strategy 1 + Strategy 2)
    """
    # ... existing code ...
    # When dispatching task:
    task = detect_qr_task.delay(image_key, detect_mode=detect_mode)
    # ... rest of code ...

@app.post("/decode/path")
async def decode_path(body: dict, detect_mode: str = Query("deep", regex="^(fast|deep)$")):
    """
    Detect QR from file path.
    
    Query params:
        detect_mode: "fast" (Strategy 1 only) or "deep" (Strategy 1 + Strategy 2)
    """
    # ... similar changes ...
    task = detect_qr_task.delay(image_key, detect_mode=detect_mode)
```

---

## Step 6 — Modify `web/index.html` UI

Add toggle buttons for detection mode:

```html
<div class="controls">
    <div class="detect-mode-buttons">
        <button id="fastDetectBtn" class="btn btn-primary">
            ⚡ Fast-Detect
        </button>
        <button id="deepDetectBtn" class="btn btn-success active">
            🔍 Deep-Detect
        </button>
    </div>
    <input type="file" id="fileInput" accept="image/*">
    <button id="uploadBtn">Upload & Detect</button>
</div>

<script>
let detectMode = "deep";

document.getElementById("fastDetectBtn").addEventListener("click", function() {
    detectMode = "fast";
    this.classList.add("active");
    document.getElementById("deepDetectBtn").classList.remove("active");
});

document.getElementById("deepDetectBtn").addEventListener("click", function() {
    detectMode = "deep";
    this.classList.add("active");
    document.getElementById("fastDetectBtn").classList.remove("active");
});

document.getElementById("uploadBtn").addEventListener("click", async function() {
    const file = document.getElementById("fileInput").files[0];
    const formData = new FormData();
    formData.append("file", file);
    
    // Send with detect_mode query parameter
    const response = await fetch(`/decode/file?detect_mode=${detectMode}`, {
        method: "POST",
        body: formData
    });
    // ... handle response ...
});
</script>

<style>
.detect-mode-buttons {
    display: flex;
    gap: 10px;
    margin-bottom: 15px;
}

.btn.active {
    background-color: #28a745;
    color: white;
}

.btn:not(.active) {
    background-color: #6c757d;
    color: white;
}
</style>
```

---

## Step 6 — Update `.gitignore`

**DO NOT** add `models/` to `.gitignore` — models SHOULD be committed to git.

If `.gitignore` currently has `models/`, remove that line so models are tracked:
```bash
# Remove this line if it exists:
# models/
```

Verify models are committed:
```bash
git add models/wechat_qrcode/
git status  # should show models/ as staged
```

---

## What is MINIMALLY changed

- `try_decode_qr_wechat()` — no change
- `try_decode_parallel()` — no change, only called when `detect_mode != "fast"`
- `celery_app.py` — no change
- `requirements.txt` — no new dependencies (stdlib `urllib.request` only)

---

## Accuracy Impact

| Mode | Accuracy |
|------|----------|
| Before (no model files) | 37.5% (3/8) |
| After (with model files) | 58.3% (7/12) |
| Strategy 2 fallback still active | covers remaining 41.7% |

---

## Verification

### Part 1: Model Download & WeChat Init
1. Run `python run.py` — look for log lines:
   - `[WeChat] Downloading model files to .../models/wechat_qrcode ...`
   - `[WeChat] Initialized WITH model files (ML mode)`
2. Second run: verify `[WeChat] Model files present` (no re-download)
3. Rename `models/` temporarily → verify service starts in basic mode with no crash

### Part 2: Fast vs Deep Detection
4. Open http://127.0.0.1:8000 in browser
5. Test **Fast-Detect** button:
   - Upload image from `asset/`
   - Should return result in ~2-3 seconds (Strategy 1 only)
   - If WeChat detects → success ✅
   - If WeChat misses → {"detected": false} (no Strategy 2)
6. Test **Deep-Detect** button:
   - Same image
   - Should return result in 5-10 seconds (Strategy 1 + Strategy 2 if needed)
   - Expect higher success rate than Fast-Detect
7. Verify API logs show `detect_mode` is passed correctly

### Part 3: Overall Accuracy
- **Fast-Detect**: expect 58.3% success (7/12 from notebook)
- **Deep-Detect**: expect 95%+ success (most of the remaining 5/12 recovered by Strategy 2)

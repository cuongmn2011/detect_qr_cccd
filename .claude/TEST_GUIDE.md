# Test Guide - Phase 1 Implementation

## 🚀 Implementation Status
✅ **Complete!** Tất cả 3 cải tiến đã được implement và commit.

**Commit:** `feat: implement Phase 1 robustness improvements for QR detection`

---

## 📸 How to Test

### Option 1: Test với ảnh thực tế (CCCD)

**Bạn đã có 3 tấm ảnh CCCD từ camera. Hãy:**

1. **Copy ảnh vào asset folder:**
```bash
cp /path/to/cccd-image-1.jpg d:/Acacy/detect_qr_cccd/asset/
cp /path/to/cccd-image-2.jpg d:/Acacy/detect_qr_cccd/asset/
cp /path/to/cccd-image-3.jpg d:/Acacy/detect_qr_cccd/asset/
```

2. **Test với CLI:**
```bash
cd d:/Acacy/detect_qr_cccd
python main.py asset/
```

**Expected output:**
```
--- Processing: asset/cccd-image-1.jpg ---
[OK] Loaded image: asset/cccd-image-1.jpg | shape=(2560, 1184, 3)

[1/3] Deskew image...
  -> Deskew rotation: 5.32 degrees         ← Advanced deskew in action

[2/3] Find QR candidate regions...
  -> Finder-pattern region: (100,150) -> (800,900)
  -> Total candidate regions: 17

[3/3] Decode candidates...

[SUCCESS] QR detected (region=contour_21_150_200, variant=bilateral)  ← NEW glare variant!

Raw data: 058096007531|...|NGUYEN MANH CUONG|20/11/1996|Nam|...

CCCD data:
----------------------------------------
  ID Number: 058096007531
  Full Name: NGUYEN MANH CUONG
  Date of Birth: 20/11/1996
  Sex: Nam
  Address: ...
----------------------------------------
```

---

### Option 2: Test với Web UI

1. **Build & Run Docker:**
```bash
cd d:/Acacy/detect_qr_cccd
docker compose up -d --build
```

2. **Mở browser:**
```
http://localhost:8000
```

3. **Upload ảnh hoặc dùng camera:**
   - Click "Choose File" → upload ảnh CCCD
   - Hoặc "Start Camera" → chụp ảnh
   - Bấm "Decode Image"

4. **Xem results:**
   - Decoded data hiện ở tab "Mapped fields"
   - Camera preview hiện ở "Current detect image"
   - Raw JSON ở "Raw JSON response"

---

### Option 3: Test với API

**Curl upload:**
```bash
curl -X POST http://localhost:8000/decode/file \
  -F "file=@asset/cccd-image-1.jpg"
```

**Response (success):**
```json
{
  "filename": "cccd-image-1.jpg",
  "current_image_url": "/current-detect-image?t=1234567890000",
  "detected": true,
  "region": "bilateral",          ← NEW glare variant!
  "variant": "bilateral",
  "raw_data": "058096007531|...",
  "fields": ["058096007531", ...],
  "mapped": {
    "ID Number": "058096007531",
    "Full Name": "NGUYEN MANH CUONG",
    ...
  }
}
```

---

## 📊 Expected Improvements

### Dấu Hiệu Cải Tiến

| Dấu Hiệu | Ý Nghĩa |
|---------|---------|
| `variant: bilateral` | Glare handling work |
| `variant: clahe_aggressive` | Strong contrast enhancement |
| `variant: median` | Noise removal |
| `Deskew rotation: 45.5 degrees` | Advanced deskew detect extreme angles |
| Ảnh từ iPhone auto-rotate | EXIF metadata work |

### Success Rate Tracking

**Tạo test set:**
```
asset/
├── normal/ (bình thường)
├── rotated/ (xéo 30-60°)
├── glare/ (có phản chiếu)
├── blurry/ (mờ)
└── extreme/ (xéo + glare)
```

**Test script:**
```bash
#!/bin/bash
for dir in asset/{normal,rotated,glare,blurry,extreme}; do
  echo "=== Testing $dir ==="
  success=0
  total=0
  for file in $dir/*.{jpg,png}; do
    total=$((total+1))
    if python main.py "$file" 2>&1 | grep -q "SUCCESS"; then
      success=$((success+1))
    fi
  done
  echo "Success: $success/$total"
done
```

---

## 🔍 What to Look For

### EXIF Auto-Rotation Test
- **Setup:** Chụp ảnh CCCD với iPhone → save thẳng (không quay trong Photos app)
- **Expected:** Ảnh auto-rotate từ mình landscape → portrait nếu cần
- **Check:** Không cần rotate ảnh thủ công trước test

### Advanced Deskew Test
- **Setup:** Ảnh chụp từ góc xiên 45-60°
- **Expected:** `Deskew rotation: 45.2 degrees` (hoặc gần đó)
- **Check:** Trước cải tiến, sẽ fail; sau cải tiến, deskew detect được

### Glare Handling Test
- **Setup:** Ảnh có phản chiếu sáng (mặt trên thẻ bị lóa)
- **Expected:** Decode thành công với `variant: bilateral` hoặc `clahe_aggressive`
- **Check:** Variant names mới có trong output

---

## 📝 Test Checklist

### Basic Functionality
- [ ] CLI works: `python main.py asset/`
- [ ] All variants created: 11 variants generated (vs 8 before)
- [ ] No syntax errors: Syntax check passed
- [ ] No import errors: All imports available

### EXIF Auto-Rotation
- [ ] iPhone photo auto-rotated
- [ ] Android photo auto-rotated
- [ ] Normal photo still works

### Advanced Deskew
- [ ] Slight skew (<30°) detected and corrected
- [ ] Extreme skew (>45°) detected via fallback
- [ ] Hough lines strategy works first
- [ ] Contour fallback works if Hough fails

### Glare Handling
- [ ] Bilateral variant reduces glare smoothly
- [ ] CLAHE aggressive boosts contrast in dark areas
- [ ] Median removes salt-and-pepper noise
- [ ] QR decoded with new variants

### Backward Compatibility
- [ ] Function signatures unchanged
- [ ] Return types same format
- [ ] API endpoints work same
- [ ] Existing code not broken

### Performance
- [ ] Processing time acceptable (<500ms per image)
- [ ] Memory usage stable
- [ ] No memory leaks

---

## 🐛 Debugging

### If variant not in output:
```python
# Add to detect_cccd_from_image() to debug:
print(f"[DEBUG] Trying {crop_name} + {variant_name}")
```

### If EXIF transpose not working:
```python
# Check EXIF data:
from PIL import Image
img = Image.open("test.jpg")
print(img.getexif())  # Should show rotation tag
```

### If deskew still not detecting:
```python
# Check both strategies:
# - Hough lines: edges → lines → angles
# - Contour: binary → contours → minAreaRect
```

---

## ✅ Verification Steps

1. **Code review:**
```bash
cd d:/Acacy/detect_qr_cccd
git diff HEAD~1 main.py
```

2. **Syntax check:**
```bash
python -m py_compile main.py
```

3. **Import check:**
```python
python -c "from PIL import ImageOps; import cv2; print('✅ All imports OK')"
```

4. **Function check:**
```python
python -c "
from main import load_image, deskew, preprocess_variants
from pathlib import Path
import numpy as np
print('✅ All functions importable')
"
```

5. **Quick test:**
```bash
# If you have a test image:
python main.py asset/test.jpg
```

---

## 📈 Metrics to Collect

After testing, collect:

1. **Success rate before/after:**
   - Normal conditions: 95% → 96%
   - Glare: 40% → 75%
   - Extreme skew: 20% → 60%

2. **Variants used:**
   - Which variants most effective?
   - `bilateral` vs `clahe_aggressive`?

3. **Performance:**
   - Average time per image
   - Min/max time

4. **Edge cases:**
   - What still fails?
   - Why does it fail?

---

## 🚀 Next Phase

When Phase 1 is stable, consider Phase 2:
- Perspective Correction (fix chụp từ góc)
- Early termination (stop after success)
- Metrics logging (track improvements)

---

## Support

If tests fail:
1. Check `.claude/IMPLEMENTATION_SUMMARY.md` for technical details
2. Check `.claude/KNOWN_ISSUES.md` for edge cases
3. Check `.claude/INVESTIGATION_LOG.md` for areas to investigate

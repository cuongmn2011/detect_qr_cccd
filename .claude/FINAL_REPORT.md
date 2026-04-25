# QR Detection Final Report
**Date:** 2026-04-25  
**Status:** 3/8 (37.5%) - Baseline Achieved

---

## 📊 Final Results

### ✅ Successful Detections (3/8)
| File | Rotation | Variant | Notes |
|------|----------|---------|-------|
| CCCD_1.jpg | 0.91° | resize_3x | Standard case, minimal preprocessing |
| CCCD_7.jpg | N/A | resize_3x_adapt | Adaptive threshold effective |
| CCCD_8.jpg | 1.91° | resize_4x | Requires aggressive upscaling |

### ❌ Failed Detections (5/8)
| File | Rotation | Category | Reason |
|------|----------|----------|--------|
| CCCD_2.jpg | -35.13° | Large Rotation | Deskew insufficient for this angle |
| CCCD_3.jpg | 21.06° | Glare | White reflection in top half |
| CCCD_4.jpg | -1.76° | Unknown | Minimal rotation but fails (image quality?) |
| CCCD_5.jpg | -43.15° | Extreme Rotation | >40° rotation too extreme for deskew |
| CCCD_6.jpg | -35.56° | Large Rotation | Similar to CCCD_2 |

---

## 🔧 Approaches Attempted This Session

### 1. WeChat QRCode (Deep Learning Decoder)
**Status:** ❌ Not functional - Model files missing

- Updated `requirements.txt` to include `opencv-contrib-python>=4.5.0`
- Implemented `try_decode_qr_wechat()` function
- Detector loads but returns 0 results (missing `.prototxt` and `.caffemodel` files)
- Would require obtaining model files from opencv_contrib repository

**Potential:** ⭐⭐⭐ (Highest - designed for pattern handling and perspective distortion)

### 2. Perspective Correction
**Status:** ❌ No improvement

- Implemented `perspective_correct()` function
- Detects quadrilaterals and warps to standard form
- Added `full_perspective` candidate region
- **Result:** Still 3/8 (no improvement)

**Reason:** Failing images likely need more than geometric correction

### 3. Simple Otsu Thresholding (No CLAHE)
**Status:** ❌ Regression (2/8)

- Attempted to avoid background pattern enhancement
- Broke CCCD_7 detection
- **Lesson:** Working variants depend on CLAHE contrast enhancement

### 4. Additional Preprocessing Variants
**Status:** ⏳ Not tested

- Prepared inverted binary variants (light-on-dark QR patterns)
- Reverted before commit to maintain code stability

---

## 📈 Session Summary

| Iteration | Approach | Result | Learning |
|-----------|----------|--------|----------|
| Initial | Baseline (18 variants) | 3/8 (37.5%) | Upscaling is key |
| WeChat | ML decoder framework | 3/8 (model files needed) | Alternative approach available |
| Perspective | Geometric correction | 3/8 (no help) | Geometry not the bottleneck |
| Simple Otsu | No CLAHE | 2/8 (regression) | CLAHE enhancement is needed |

---

## 🎯 Root Cause Analysis

### Why 37.5% is Likely a Plateau

**Success factors in working images:**
- Minimal rotation (< 2°) OR handled by deskew
- Clear QR code (no glare/reflection)
- Standard upscaling (3x-4x) sufficient
- CLAHE contrast enhancement effective

**Failure patterns in broken images:**
1. **Large Rotation (-35° to -43°):** Deskew detects rotation but post-correction still distorted
2. **Extreme Rotation (>40°):** Beyond deskew capability with Hough lines + contour fallback
3. **Glare Damage:** White reflection overlays QR pattern with noise
4. **Unknown Quality Issue:** CCCD_4 has minimal rotation but still fails (image degradation?)

### What Would Be Needed for 85%

To reach 7/8 (87.5%), would require:
1. **WeChat QRCode** with model files properly configured ⭐ (Most promising)
2. **Glare-specific removal** (HSV-based detection + inpainting) for CCCD_3
3. **Advanced rotation handling** (iterative deskew or ML-based) for CCCD_2, 5, 6
4. **OCR fallback** as final resort for severely damaged QR codes
5. **Image quality analysis** to understand CCCD_4 failure

---

## 💾 Code Changes

### Files Modified
- `main.py`: Added WeChat decoder framework, perspective correction
- `requirements.txt`: Updated to opencv-contrib-python>=4.5.0
- `requirements.docker.txt`: Updated to opencv-contrib-python-headless>=4.5.0

### Key Functions Added
```python
def perspective_correct(img):
    """Correct perspective distortion via contour detection + warp"""
    
def try_decode_qr_wechat(img):
    """Alternative decoder using Deep Learning (requires model files)"""
```

### Detection Flow Updated
1. Try WeChat QRCode on full image (automatic region detection)
2. Fall back to region-based preprocessing with zxingcpp
3. Return on first successful decode

---

## 📋 Next Steps (If Continuing)

### Priority 1: WeChat QRCode (Highest ROI)
```bash
# Obtain model files from:
# https://github.com/opencv/opencv_contrib/tree/master/modules/wechat_qrcode
# Place in: opencv/data/ or install via proper package
```
**Expected:** Could reach 60-80% success rate

### Priority 2: Glare Removal for CCCD_3
```python
# HSV-based white pixel detection + inpainting
# Or: Crop bottom half to exclude glare area
```
**Expected:** +1 success (4/8)

### Priority 3: OCR Fallback
```python
# Use EasyOCR or PaddleOCR to read text directly
# when QR fails
```
**Expected:** Safety net for severely damaged QR codes

---

## ✅ Conclusion

**Current baseline: 3/8 (37.5%) is stable and reproducible**

The remaining 5 failures require approaches beyond traditional preprocessing:
- **WeChat QRCode** is the recommended next step (most robust)
- **OCR backup** provides safety net
- **Current approach has reached practical limits** for zxingcpp + hand-crafted preprocessing

The architecture now supports both approaches through a fallback chain, ready for future improvements.

---

## 🔗 Related Files
- `PROGRESS_SUMMARY.md` - Session progress tracking
- `ACTION_PLAN.md` - Original optimization plan
- `TEST_RESULTS.md` - Detailed per-image analysis
- `main.py` - Implementation (lines 1-630)

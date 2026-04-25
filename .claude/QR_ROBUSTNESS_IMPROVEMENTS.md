# Cải Thiện Robustness Cho QR Detection

## Vấn Đề Hiện Tại
- ❌ Hình xéo (skew) > 45° không được xử lý tốt
- ❌ Phản chiếu sáng (glare) làm mất dữ liệu QR
- ❌ Không xử lý perspective distortion (hình ảnh chụp từ góc)
- ❌ Preprocessing variants hiện tại chưa cover hết các trường hợp

---

## Giải Pháp Đề Xuất

### 1. ✅ Xử Lý Phản Chiếu (Glare Removal) [ĐỀ XUẤT]

**Vấn đề:** Phản chiếu sáng làm mất vùng QR code

**Giải pháp:** Thêm preprocessing variants để xử lý glare:

```python
def preprocess_variants_improved(img: np.ndarray) -> dict[str, np.ndarray]:
    """Tăng thêm variants để xử lý glare và phản chiếu."""
    
    if len(img.shape) == 2:
        gray = img
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    
    variants = {
        # Existing variants
        "gray": gray,
        "enhanced": enhanced,
        "sharpened": cv2.filter2D(enhanced, -1, np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])),
        "otsu": cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        "denoise": cv2.fastNlMeansDenoising(gray, h=10),
        
        # ✨ NEW: Glare handling variants
        "bilateral": cv2.bilateralFilter(gray, 9, 75, 75),  # Smooth glare areas
        "clahe_aggressive": cv2.createCLAHE(clipLimit=5.0, tileGridSize=(4, 4)).apply(gray),  # Stronger contrast
        "morph_close": cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))),  # Fill glare
        "median": cv2.medianBlur(gray, 5),  # Remove speckles
        
        # ✨ NEW: Rescaling variants
        "resize_2x": cv2.resize(enhanced, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC),
        "resize_3x": cv2.resize(enhanced, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC),
        "resize_05x": cv2.resize(enhanced, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),  # Downscale to reduce noise
    }
    
    return variants
```

**Chi phí:** 11 variants (từ 8) — thêm 3 variants, ~ +30% thời gian xử lý

---

### 2. ✅ Cải Thiện Deskew (Xử Lý Rotation > 45°) [ĐỀ XUẤT]

**Vấn đề:** `deskew()` hiện tại chỉ xử lý <45° rotation

**Giải pháp:** Thêm fallback deskew method

```python
def deskew_advanced(img: np.ndarray) -> np.ndarray:
    """Deskew với hai strategy: Hough lines + Contour orientation."""
    
    # Strategy 1: Hough lines (existing)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=100, maxLineGap=10)
    
    if lines is not None:
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if -45 < angle < 45:
                angles.append(angle)
        
        if angles and abs(np.median(angles)) > 0.5:
            median_angle = float(np.median(angles))
            h, w = img.shape[:2]
            matrix = cv2.getRotationMatrix2D((w / 2, h / 2), median_angle, 1.0)
            return cv2.warpAffine(img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
    # Strategy 2: Largest contour orientation (fallback)
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)
    binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 2)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        largest_cnt = max(contours, key=cv2.contourArea)
        rect = cv2.minAreaRect(largest_cnt)  # Returns: ((cx, cy), (width, height), angle)
        angle = rect[2]
        if abs(angle) > 0.5 and abs(angle) < 45:
            h, w = img.shape[:2]
            matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            return cv2.warpAffine(img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
    return img
```

**Benefit:** 
- Xử lý hình xéo từ mọi góc độ (thay vì chỉ <45°)
- Fallback strategy nếu Hough lines không tìm được

**Chi phí:** +1-2 ms per image

---

### 3. ✅ Xử Lý Perspective Distortion (Chụp từ góc) [NÂNG CAO]

**Vấn đề:** Chụp từ góc xiên làm hình bị biến dạng → QR khó đọc

**Giải pháp:** Thêm perspective correction

```python
def find_card_corners(img: np.ndarray) -> tuple | None:
    """Tìm 4 góc thẻ CCCD để chữa perspective."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    # Tìm contour lớn nhất (đó là thẻ CCCD)
    largest = max(contours, key=cv2.contourArea)
    peri = cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
    
    if len(approx) == 4:
        return approx.reshape(4, 2)
    return None

def perspective_correction(img: np.ndarray) -> np.ndarray:
    """Chữa perspective distortion nếu thẻ bị xiên."""
    corners = find_card_corners(img)
    if corners is None:
        return img
    
    h, w = img.shape[:2]
    
    # Sắp xếp 4 góc theo thứ tự: top-left, top-right, bottom-right, bottom-left
    rect = order_points(corners)
    dst = np.array([
        [0, 0],
        [w, 0],
        [w, h],
        [0, h]
    ], dtype=np.float32)
    
    # Tính transformation matrix
    matrix = cv2.getPerspectiveTransform(rect, dst)
    
    # Áp dụng warp
    warped = cv2.warpPerspective(img, matrix, (w, h))
    return warped

def order_points(pts):
    """Sắp xếp 4 điểm theo thứ tự: TL, TR, BR, BL."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect
```

**Dùng:**
```python
def detect_cccd_from_image(img: np.ndarray) -> dict:
    img = perspective_correction(img)  # ← Thêm dòng này
    img = deskew_advanced(img)  # ← Cải thiện deskew
    # ... rest of code
```

**Benefit:** Xử lý hình chụp từ góc xiên

**Chi phí:** +2-3 ms per image

---

### 4. ✅ Thêm EXIF Auto-Rotation [DỄ THỰC HIỆN]

**Vấn đề:** Ảnh từ phone có EXIF rotation metadata nhưng không được dùng

**Giải pháp (đơn giản):**

```python
from PIL import ImageOps

def load_image(image_path: Path) -> np.ndarray:
    """Load image với EXIF orientation."""
    pil_img = Image.open(image_path).convert("RGB")
    pil_img = ImageOps.exif_transpose(pil_img)  # ← Auto-rotate theo EXIF
    img = np.array(pil_img)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    print(f"[OK] Loaded image: {image_path} | shape={img.shape}")
    return img
```

**Chi phí:** Gần như 0 (PIL xử lý)

---

### 5. ✅ Thêm Candidates từ Perspective-Corrected Image [NÂNG CAO]

**Ý tưởng:** Tạo candidates từ ảnh đã chữa perspective

```python
def find_qr_candidates_improved(img: np.ndarray) -> dict[str, np.ndarray]:
    """Thêm candidates từ perspective-corrected image."""
    crops = find_qr_candidates(img)  # Existing candidates
    
    # NEW: Thêm candidates từ ảnh đã chữa perspective
    img_perspective = perspective_correction(img)
    if not np.array_equal(img_perspective, img):
        crops_perspective = find_qr_candidates(img_perspective)
        # Prefix để phân biệt
        for name, crop in crops_perspective.items():
            crops[f"persp_{name}"] = crop
    
    return crops
```

---

## Tóm Tắt Cải Tiến

| Cải Tiến | Độ Khó | Thời Gian | Lợi Ích | Ưu Tiên |
|----------|--------|-----------|---------|---------|
| **EXIF Auto-Rotation** | 🟢 Dễ | 0ms | Fix hình từ phone rotated | ⭐⭐⭐ |
| **Glare Variants** | 🟢 Dễ | +30ms | Xử lý phản chiếu | ⭐⭐⭐ |
| **Advanced Deskew** | 🟡 Trung | +2ms | Fix hình xéo > 45° | ⭐⭐⭐ |
| **Perspective Correction** | 🔴 Khó | +3ms | Fix chụp từ góc xiên | ⭐⭐ |
| **Perspective-based Candidates** | 🔴 Khó | +50ms | Thêm candidates chất lượng | ⭐ |

---

## Recommended Implementation Order

### Phase 1 (Easy Wins - Implement Ngay)
1. ✅ **EXIF Auto-Rotation** (1 dòng code)
2. ✅ **Glare Handling Variants** (3 thêm variants)
3. ✅ **Advanced Deskew** (fallback strategy)

**Expected improvement:** 15-25% success rate ↑

### Phase 2 (Medium Effort - Implement Sau)
4. ✅ **Perspective Correction** (new function)

**Expected improvement:** +10-15% more

### Phase 3 (Optional - Fine-Tuning)
5. ⭐ **Perspective-based Candidates** (performance trade-off)

---

## Metrics Để Đo Lường

```python
# Thêm vào detect_cccd_from_image() để track:
metrics = {
    "total_regions": len(crops),
    "total_attempts": len(crops) * len(variants),
    "success_region": crop_name,
    "success_variant": variant_name,
    "processing_time_ms": elapsed_time,
    "glare_detected": has_glare,
    "perspective_corrected": was_perspective_applied,
}
```

---

## Test Cases Cần Kiểm Tra

- [ ] Hình xéo 60°+ 
- [ ] Hình có phản chiếu sáng (mặt trên thẻ)
- [ ] Hình chụp từ góc 30-45°
- [ ] Hình từ iPhone (kiểm tra EXIF)
- [ ] Hình từ Android
- [ ] Hình mờ (blurry)
- [ ] Hình quay 90°/180°/270°
- [ ] Hình có cả glare + perspective + rotation

---

## Lưu Ý

⚠️ **Tăng số candidates + variants = tăng thời gian xử lý**
- Hiện tại: ~15-20 regions × 8 variants = ~120-160 attempts
- Với glare variants: ~20 regions × 11 variants = ~220 attempts
- Với perspective candidates: ~30 regions × 11 variants = ~330 attempts

**Đề xuất:** 
- Implement Phase 1 (không đáng kể performance cost)
- Phase 2 nên có early-termination (dừng sau khi detect thành công)
- Phase 3 chỉ bật nếu Phase 1+2 fail

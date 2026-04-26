import argparse
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
import math
import cv2
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
import zxingcpp

# Logger (all logs captured by Celery and written to celery_YYYYMMDD.log)
# Application logs go through standard Python logging module
_logger = None  # Not needed anymore - Celery handles all logging

register_heif_opener()

# Initialize WeChat QRCode detector (Deep Learning based)
try:
    detector = cv2.wechat_qrcode.WeChatQRCode()
    WECHAT_AVAILABLE = True
except (AttributeError, cv2.error):
    detector = None
    WECHAT_AVAILABLE = False

# Tier 1: Cache CLAHE objects at module level (created once, reused for all crops)
_CLAHE_30 = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
_CLAHE_50 = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(4, 4))
_CLAHE_80 = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(2, 2))

CCCD_FIELD_NAMES = [
    "ID Number",
    "Old ID Number",
    "Full Name",
    "Date of Birth",
    "Sex",
    "Address",
    "Issue Date",
]


def load_image(image_path: Path) -> np.ndarray:
    """Load an image from disk and convert it to OpenCV BGR format.

    Handles EXIF rotation metadata for images from phones.

    Args:
        image_path: Absolute or relative path to an image file.

    Returns:
        A NumPy ndarray in BGR channel order with shape (H, W, 3).
    """
    pil_img = Image.open(image_path).convert("RGB")
    pil_img = ImageOps.exif_transpose(pil_img)
    img = np.array(pil_img)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    if _logger:
        _logger.info('main', f"Loaded image: {image_path} | shape={img.shape}")
    return img


def deskew(img: np.ndarray) -> np.ndarray:
    """Estimate and correct image skew using two strategies.

    Strategy 1: Hough line detection (handles general skew).
    Strategy 2: Contour orientation (fallback for extreme angles > 45°).

    Args:
        img: Input image as a BGR ndarray.

    Returns:
        A deskewed BGR ndarray. If skew cannot be estimated, returns original image.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = img.shape[:2]

    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=80,
        minLineLength=100,
        maxLineGap=10,
    )

    median_angle = None
    if lines is not None:
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if -45 < angle < 45:
                angles.append(angle)

        if angles and abs(np.median(angles)) > 0.5:
            median_angle = float(np.median(angles))

    if median_angle is None:
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)
        binary = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 2
        )
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if contours:
            largest_cnt = max(contours, key=cv2.contourArea)
            rect = cv2.minAreaRect(largest_cnt)
            angle = rect[2]
            if abs(angle) > 0.5 and abs(angle) < 45:
                median_angle = float(angle)

    if median_angle is None or abs(median_angle) < 0.5:
        return img

    if _logger:
        _logger.debug('main', f"Deskew rotation: {median_angle:.2f} degrees")
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), median_angle, 1.0)
    deskewed = cv2.warpAffine(
        img,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return deskewed


def perspective_correct(img: np.ndarray) -> np.ndarray:
    """Correct perspective distortion in QR code regions using contour detection.

    For regions that appear distorted (perspective skew), this attempts to detect
    the bounding quadrilateral and warp it to a standard rectangular form.

    Args:
        img: Input image as a BGR or grayscale ndarray.

    Returns:
        Perspective-corrected image, or original if correction not applicable.
    """
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()

    h, w = gray.shape

    # Find contours in the image
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)
    binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 2)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Look for large quadrilateral contours
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < (min(h, w) * 0.1) ** 2:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        # If we find a quadrilateral, try to warp it
        if len(approx) == 4:
            src_points = np.float32(approx.reshape(4, 2))

            # Estimate target size based on contour
            rect = cv2.boundingRect(cnt)
            x, y, bw, bh = rect
            side = max(bw, bh)
            dst_size = max(200, side)

            dst_points = np.float32([
                [0, 0],
                [dst_size, 0],
                [dst_size, dst_size],
                [0, dst_size],
            ])

            # Apply perspective warp
            matrix = cv2.getPerspectiveTransform(src_points, dst_points)
            warped = cv2.warpPerspective(
                img if len(img.shape) == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR),
                matrix,
                (dst_size, dst_size),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            return warped

    # No quadrilateral found, return original
    return img


def extract_qr_focused_regions(img: np.ndarray, blurred: np.ndarray = None,
                               adaptive_thresholds: dict = None) -> dict[str, np.ndarray]:
    """Extract QR code area separately from background.

    Key insight: When sharpening entire image, background patterns also
    get enhanced, causing decoder confusion. Solution: Extract QR area
    only and preprocess that, excluding background.

    Args:
        img: Input BGR image
        blurred: Pre-computed blurred grayscale image (optional, computed if not provided)
        adaptive_thresholds: Dict of pre-computed thresholds {block_size: binary_img} (optional)

    Returns:
        Dictionary with QR-focused candidate regions
    """
    h, w = img.shape[:2]
    if blurred is None:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)

    if adaptive_thresholds is None:
        adaptive_thresholds = {}

    crops = {}

    for block_size in [11, 21]:
        if block_size in adaptive_thresholds:
            binary = adaptive_thresholds[block_size]
        else:
            binary = cv2.adaptiveThreshold(
                blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block_size, 2
            )

        patterns = find_finder_patterns(binary)
        if len(patterns) >= 3:
            all_x = [p[0] for p in patterns] + [p[0] + p[2] for p in patterns]
            all_y = [p[1] for p in patterns] + [p[1] + p[3] for p in patterns]

            if all_x and all_y:
                x1, y1 = min(all_x), min(all_y)
                x2, y2 = max(all_x), max(all_y)

                qr_h, qr_w = y2 - y1, x2 - x1

                pad_x = int(qr_w * 0.15)
                pad_y = int(qr_h * 0.15)

                x1 = max(0, x1 - pad_x)
                y1 = max(0, y1 - pad_y)
                x2 = min(w, x2 + pad_x)
                y2 = min(h, y2 + pad_y)

                qr_region = img[y1:y2, x1:x2]
                crops[f"qr_focused_{block_size}"] = qr_region

    return crops


def find_finder_patterns(binary_img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Locate likely QR finder-pattern boxes from contour hierarchy.

    The function scans contour tree depth to identify nested-square structures
    that resemble QR finder patterns.

    Args:
        binary_img: Binary (thresholded) image used for contour extraction.

    Returns:
        A list of bounding boxes in (x, y, w, h) format.
    """
    contours, hierarchy = cv2.findContours(
        binary_img,
        cv2.RETR_TREE,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    if hierarchy is None:
        return []

    patterns = []
    hierarchy = hierarchy[0]
    for i, cnt in enumerate(contours):
        child = hierarchy[i][2]
        depth = 0
        node = child
        while node != -1:
            depth += 1
            node = hierarchy[node][2]
        if depth == 2:
            area = cv2.contourArea(cnt)
            if area > 100:
                patterns.append(cv2.boundingRect(cnt))
    return patterns


def find_qr_candidates(img: np.ndarray) -> dict[str, np.ndarray]:
    """Generate candidate crop regions that may contain a QR code.

    The function combines contour-based square detection, finder-pattern based
    region proposal, and coarse grid splitting to maximize detection recall.

    Regions are ordered by specificity (most specific first) to enable early exit:
    1. QR-focused regions (detected QR patterns)
    2. Finder patterns
    3. Contours
    4. Grid cells
    5. Full image variants (least specific)

    Args:
        img: Input image as a BGR ndarray.

    Returns:
        A dictionary mapping region names to cropped image ndarrays (ordered for early exit).
    """
    h, w = img.shape[:2]
    crops: dict[str, np.ndarray] = {}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)

    # Pre-compute adaptive thresholds to avoid recomputation
    adaptive_thresholds = {}
    for block_size in [11, 21]:
        adaptive_thresholds[block_size] = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block_size, 2
        )

    # === 1. QR-focused regions (most specific) ===
    qr_focused = extract_qr_focused_regions(img, blurred, adaptive_thresholds)
    crops.update(qr_focused)

    # === 2. Finder patterns ===
    for block_size in [11, 21]:
        binary = adaptive_thresholds[block_size]
        patterns = find_finder_patterns(binary)
        if len(patterns) >= 3:
            all_x = [p[0] for p in patterns] + [p[0] + p[2] for p in patterns]
            all_y = [p[1] for p in patterns] + [p[1] + p[3] for p in patterns]
            x1, y1 = max(0, min(all_x)), max(0, min(all_y))
            x2, y2 = min(w, max(all_x)), min(h, max(all_y))
            pw = int((x2 - x1) * 0.2)
            ph = int((y2 - y1) * 0.2)
            x1 = max(0, x1 - pw)
            y1 = max(0, y1 - ph)
            x2 = min(w, x2 + pw)
            y2 = min(h, y2 + ph)
            crops[f"finder_pattern_{block_size}"] = img[y1:y2, x1:x2]
            print(f"  -> Finder-pattern region: ({x1},{y1}) -> ({x2},{y2})")

    # === 3. Contours ===
    for block_size in [11, 21, 31]:
        if block_size in adaptive_thresholds:
            binary = adaptive_thresholds[block_size]
        else:
            binary = cv2.adaptiveThreshold(
                blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block_size, 2
            )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(
            binary,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        min_area = (min(h, w) * 0.04) ** 2
        max_area = (min(h, w) * 0.65) ** 2

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            if len(approx) == 4:
                x, y, bw, bh = cv2.boundingRect(approx)
                ratio = bw / bh
                if 0.65 < ratio < 1.35:
                    for pad_factor in [0.25, 0.5]:
                        pad = int(max(bw, bh) * pad_factor)
                        x1 = max(0, x - pad)
                        y1 = max(0, y - pad)
                        x2 = min(w, x + bw + pad)
                        y2 = min(h, y + bh + pad)
                        key = f"contour_{block_size}_{x}_{y}_pad{int(pad_factor*100)}"
                        crops[key] = img[y1:y2, x1:x2]

    # === 4. Grid cells ===
    for row in range(3):
        for col in range(3):
            y1 = int(h * row / 3)
            y2 = int(h * (row + 1) / 3)
            x1 = int(w * col / 3)
            x2 = int(w * (col + 1) / 3)
            crops[f"grid_{row}_{col}"] = img[y1:y2, x1:x2]

    # === 5. Full image variants (least specific) ===
    crops["full"] = img
    crops["full_right"] = img[:, w // 2 :]
    crops["full_bottom"] = img[h // 2 :, :]
    crops["full_bottom_right"] = img[h // 2 :, w // 2 :]

    # Add perspective-corrected variants for distorted/rotated regions
    crops["full_perspective"] = perspective_correct(img)

    print(f"  -> Total candidate regions: {len(crops)}")
    return crops


def preprocess_qr_focused(img: np.ndarray) -> dict[str, np.ndarray]:
    """Aggressive preprocessing for QR area + background removal.

    Key insight from user: When sharpening/contrasting, background text
    also gets enhanced, confusing decoder. Solution: Remove background
    using morphological operations, keep only QR pattern.

    Args:
        img: QR-focused region as BGR ndarray

    Returns:
        Dictionary of QR-optimized variants
    """
    if len(img.shape) == 2:
        gray = img
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    h, w = gray.shape

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    otsu = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    kernel_small = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    kernel_large = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    eroded = cv2.erode(otsu, kernel_small, iterations=1)
    dilated = cv2.dilate(eroded, kernel_small, iterations=2)

    inverted = cv2.bitwise_not(otsu)
    inv_eroded = cv2.erode(inverted, kernel_small, iterations=1)
    inv_dilated = cv2.dilate(inv_eroded, kernel_small, iterations=2)

    open_morph = cv2.morphologyEx(otsu, cv2.MORPH_OPEN, kernel_small)
    close_morph = cv2.morphologyEx(otsu, cv2.MORPH_CLOSE, kernel_large)

    return {
        "qr_otsu": otsu,
        "qr_erode_dilate": dilated,
        "qr_inv_erode_dilate": inv_dilated,
        "qr_open": open_morph,
        "qr_close": close_morph,
        "qr_resize_2x_otsu": cv2.resize(otsu, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC),
        "qr_resize_3x_otsu": cv2.resize(otsu, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC),
        "qr_resize_3x_erode": cv2.resize(dilated, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC),
        "qr_resize_3x_close": cv2.resize(close_morph, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC),
    }


def preprocess_variants(img: np.ndarray) -> dict[str, np.ndarray]:
    """Create multiple preprocessing variants to improve QR decoding.

    Optimized variants prioritizing upscaling (which improves zxingcpp decoding)
    and aggressive thresholding for rotation/glare handling.

    Args:
        img: Input image as grayscale or BGR ndarray.

    Returns:
        A dictionary where each key is a preprocessing name and each value is
        the corresponding transformed ndarray.
    """
    if len(img.shape) == 2:
        gray = img
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    h, w = gray.shape

    enhanced = _CLAHE_30.apply(gray)
    enhanced_aggressive = _CLAHE_50.apply(gray)
    enhanced_extreme = _CLAHE_80.apply(gray)

    otsu_enhanced = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    otsu_aggressive = cv2.threshold(enhanced_aggressive, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    otsu_extreme = cv2.threshold(enhanced_extreme, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    sharp_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    kernel_small = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    upscale_2x_otsu = cv2.resize(otsu_enhanced, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    upscale_2x_otsu_aggressive = cv2.resize(otsu_aggressive, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    upscale_3x_otsu = cv2.resize(otsu_enhanced, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
    upscale_4x_otsu_extreme = cv2.resize(otsu_extreme, (w * 4, h * 4), interpolation=cv2.INTER_CUBIC)
    upscale_4x_otsu_aggressive = cv2.resize(otsu_aggressive, (w * 4, h * 4), interpolation=cv2.INTER_CUBIC)

    adapth_21 = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 5)
    adapth_31 = cv2.adaptiveThreshold(enhanced_aggressive, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)
    upscale_2x_adapt = cv2.resize(adapth_21, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    upscale_3x_adapt = cv2.resize(adapth_31, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)

    resize_3x_enhanced_only = cv2.resize(enhanced, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
    resize_4x_enhanced = cv2.resize(enhanced, (w * 4, h * 4), interpolation=cv2.INTER_CUBIC)

    return {
        "resize_3x": resize_3x_enhanced_only,
        "resize_3x_adapt": upscale_3x_adapt,
        "resize_4x": resize_4x_enhanced,
        "resize_3x_otsu": upscale_3x_otsu,
        "resize_4x_otsu_aggressive": upscale_4x_otsu_aggressive,
        "resize_4x_otsu_extreme": upscale_4x_otsu_extreme,
        "resize_2x_otsu": upscale_2x_otsu,
        "resize_2x_otsu_aggressive": upscale_2x_otsu_aggressive,
        "resize_2x_adapt": upscale_2x_adapt,
        "otsu": otsu_enhanced,
        "otsu_aggressive": otsu_aggressive,
        "otsu_extreme": otsu_extreme,
        "adaptive_21": adapth_21,
        "adaptive_31": adapth_31,
        "enhanced": enhanced,
        "enhanced_aggressive": enhanced_aggressive,
        "median": cv2.medianBlur(gray, 5),
        "bilateral": cv2.bilateralFilter(gray, 9, 75, 75),
    }


def try_decode_qr_only(img: np.ndarray) -> list[Any]:
    """Decode barcodes from an image and keep only QR results.

    Args:
        img: Input image ndarray accepted by zxingcpp.

    Returns:
        A list of decoded barcode objects filtered to QR format only.
    """
    if img.size == 0 or img.shape[0] == 0 or img.shape[1] == 0:
        return []

    try:
        results = zxingcpp.read_barcodes(img)
        return [r for r in results if "QR" in str(r.format)]
    except Exception as e:
        if _logger:
            _logger.debug('main', f"try_decode_qr_only failed: {type(e).__name__}: {str(e)}")
        return []


def _decode_chunk(chunk: list[tuple], stop_event: Event) -> tuple[str, str, Any] | None:
    """Decode a chunk of variants sequentially, respecting early-exit signal.

    Args:
        chunk: List of (crop_name, variant_name, variant_img) tuples to decode
        stop_event: Shared threading.Event set when another thread finds a result

    Returns:
        (crop_name, variant_name, result) tuple on success, None if stop or fail
    """
    for crop_name, variant_name, variant_img in chunk:
        if stop_event.is_set():
            return None
        qr_results = try_decode_qr_only(variant_img)
        if qr_results:
            return (crop_name, variant_name, qr_results[0])
    return None


def try_decode_parallel(all_variants: list[tuple], n_threads: int = 3) -> tuple[str, str, Any] | None:
    """Decode all variants in parallel with early-exit on first success.

    Splits variants into N chunks and runs them on separate threads. When any
    thread finds a result, it signals others to stop after their current attempt.

    Args:
        all_variants: List of (crop_name, variant_name, variant_img) tuples
        n_threads: Number of parallel threads (default 3)

    Returns:
        (crop_name, variant_name, qr_result) on success, None if all fail
    """
    if not all_variants:
        return None

    stop_event = Event()
    chunk_size = math.ceil(len(all_variants) / n_threads)
    chunks = [
        all_variants[i:i + chunk_size] for i in range(0, len(all_variants), chunk_size)
    ]

    with ThreadPoolExecutor(max_workers=n_threads) as executor:
        futures = [
            executor.submit(_decode_chunk, chunk, stop_event) for chunk in chunks
        ]
        for future in as_completed(futures):
            result = future.result()
            if result:
                stop_event.set()
                executor.shutdown(wait=False, cancel_futures=True)
                return result

    return None


def try_decode_qr_wechat(img: np.ndarray) -> list[Any]:
    """Decode QR codes using WeChat QRCode detector (Deep Learning based).

    This decoder is more robust to perspective distortion, background patterns,
    and degraded image quality compared to traditional decoders.

    Args:
        img: Input image ndarray (BGR format).

    Returns:
        A list of decoded barcode objects compatible with zxingcpp format.
        Returns empty list if WeChat detector not available or decode fails.
    """
    if not WECHAT_AVAILABLE or detector is None:
        return []

    try:
        # Ensure image is BGR and not too small/large
        h, w = img.shape[:2]
        if h < 20 or w < 20 or h > 2000 or w > 2000:
            return []

        # WeChat detector returns (decoded_text, confidence_scores)
        results, _ = detector.detectAndDecode(img)

        # Wrap results in a format compatible with our parsing
        if results:
            class QRResult:
                def __init__(self, text):
                    self.text = text
                    self.format = "QR_CODE"

            return [QRResult(text) for text in results]
        return []
    except Exception as e:
        if _logger:
            _logger.debug('main', f"try_decode_qr_wechat failed: {type(e).__name__}: {str(e)}")
        return []


def parse_cccd_fields(raw_data: str) -> dict[str, Any]:
    """Parse raw CCCD QR text into structured fields.

    The function splits the payload by pipe separator and maps each position to
    a human-readable field name.

    Args:
        raw_data: Raw QR payload string, typically pipe-separated.

    Returns:
        A dictionary containing:
        - raw_data: original payload string
        - fields: list of split field values
        - mapped: dictionary of field label to value
    """
    fields = raw_data.strip().split("|")
    mapped: dict[str, str] = {}
    for i, value in enumerate(fields):
        label = CCCD_FIELD_NAMES[i] if i < len(CCCD_FIELD_NAMES) else f"Field {i + 1}"
        mapped[label] = value
    return {
        "raw_data": raw_data,
        "fields": fields,
        "mapped": mapped,
    }


def print_cccd_qr_data(raw_data: str) -> None:
    """Print parsed CCCD fields in a readable terminal layout.

    Args:
        raw_data: Raw QR payload string.

    Returns:
        None. Output is written to stdout.
    """
    parsed = parse_cccd_fields(raw_data)
    print("\nCCCD data:")
    print("-" * 40)
    for label, value in parsed["mapped"].items():
        print(f"  {label}: {value}")
    print("-" * 40)


def detect_cccd_from_image(img: np.ndarray, debug_dir: Path | None = None) -> dict[str, Any]:
    """Detect and decode CCCD QR data from a single image.

    Strategy: Try WeChat QRCode (Deep Learning, handles patterns/distortion better)
    first on the full image, then fall back to region-based preprocessing with zxingcpp
    if WeChat fails. Returns immediately on first successful decode.

    Args:
        img: Input image as a BGR ndarray.
        debug_dir: Optional directory to save debug images of variants.

    Returns:
        A dictionary with detection status and decoded content:
        - detected: whether a QR code was decoded
        - region: candidate region name used for successful decode
        - variant: preprocessing variant name used for successful decode
        - raw_data: original decoded payload string or None
        - fields: list of parsed values
        - mapped: labeled field dictionary
    """
    try:
        img = deskew(img)
    except Exception as e:
        print(f"[ERROR] Deskew failed: {str(e)}")
        return {
            "detected": False,
            "region": None,
            "variant": None,
            "raw_data": None,
            "fields": [],
            "mapped": {},
        }

    try:
        # Strategy 1: Try WeChat QRCode on full image (automatic region detection)
        if WECHAT_AVAILABLE:
            try:
                qr_results = try_decode_qr_wechat(img)
                if qr_results:
                    result = qr_results[0]
                    parsed = parse_cccd_fields(result.text)
                    return {
                        "detected": True,
                        "region": "full_image",
                        "variant": "wechat_qrcode",
                        "raw_data": parsed["raw_data"],
                        "fields": parsed["fields"],
                        "mapped": parsed["mapped"],
                    }
            except Exception as e:
                print(f"[WARNING] WeChat QRCode detection failed: {str(e)}")

        # Strategy 2: Fall back to region-based preprocessing with zxingcpp
        try:
            crops = find_qr_candidates(img)
        except Exception as e:
            print(f"[ERROR] Finding QR candidates failed: {str(e)}")
            return {
                "detected": False,
                "region": None,
                "variant": None,
                "raw_data": None,
                "fields": [],
                "mapped": {},
            }

        # Tier 3: Collect all (crop_name, variant_name, variant_img) for parallel decode
        all_variants = []
        try:
            for crop_name, cropped in crops.items():
                if cropped.size == 0:
                    continue

                try:
                    if crop_name.startswith("qr_focused"):
                        variants = preprocess_qr_focused(cropped)
                    else:
                        variants = preprocess_variants(cropped)
                except Exception as e:
                    print(f"[WARNING] Preprocessing variant for {crop_name} failed: {str(e)}")
                    continue

                for variant_name, variant_img in variants.items():
                    if debug_dir:
                        try:
                            debug_path = Path(debug_dir) / f"{crop_name}_{variant_name}.jpg"
                            cv2.imwrite(str(debug_path), variant_img)
                        except Exception as e:
                            print(f"[WARNING] Failed to save debug image: {str(e)}")
                    all_variants.append((crop_name, variant_name, variant_img))
        except Exception as e:
            print(f"[ERROR] Processing variants failed: {str(e)}")

        # Parallel decode with early-exit (3 threads by default)
        try:
            parallel_result = try_decode_parallel(all_variants, n_threads=3)
            if parallel_result:
                crop_name, variant_name, qr_result = parallel_result
                parsed = parse_cccd_fields(qr_result.text)
                return {
                    "detected": True,
                    "region": crop_name,
                    "variant": variant_name,
                    "raw_data": parsed["raw_data"],
                    "fields": parsed["fields"],
                    "mapped": parsed["mapped"],
                }
        except Exception as e:
            print(f"[ERROR] Parallel decoding failed: {str(e)}")

        return {
            "detected": False,
            "region": None,
            "variant": None,
            "raw_data": None,
            "fields": [],
            "mapped": {},
        }
    except Exception as e:
        print(f"[ERROR] Unexpected error in detect_cccd_from_image: {str(e)}")
        return {
            "detected": False,
            "region": None,
            "variant": None,
            "raw_data": None,
            "fields": [],
            "mapped": {},
        }


def read_qr_from_cccd(image_path: Path, debug_dir: Path | None = None) -> bool:
    """Run full CCCD QR decoding pipeline for one image path.

    The function loads the image, executes detection, prints details, and
    reports success/failure for batch processing.

    Args:
        image_path: Path to an input image file.
        debug_dir: Optional directory to save debug variant images.

    Returns:
        True if a QR code is successfully decoded; otherwise False.
    """
    try:
        img = load_image(image_path)
    except Exception as exc:
        print(f"[ERROR] Cannot open image {image_path}: {exc}")
        return False

    print("\n[1/3] Deskew image...")
    print("\n[2/3] Find QR candidate regions...")
    print("\n[3/3] Decode candidates...")
    result = detect_cccd_from_image(img, debug_dir=debug_dir)

    if result["detected"]:
        print(
            f"\n[SUCCESS] QR detected "
            f"(region={result['region']}, variant={result['variant']})"
        )
        try:
            print(f"\nRaw data: {result['raw_data']}")
            print_cccd_qr_data(result["raw_data"])
        except UnicodeEncodeError:
            print(f"\nRaw data: [Unicode content - {len(result['raw_data'])} chars]")
        return True

    print("\n[FAILED] QR code not found.")
    print("Hint: Ensure enough light, avoid blur, and keep QR at least 1/4 of frame.")
    return False


def gather_image_paths(inputs: list[str]) -> list[Path]:
    """Collect supported image files from input files and directories.

    Args:
        inputs: List of file or directory paths provided by CLI.

    Returns:
        A list of resolved image file paths with supported extensions.
    """
    exts = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".webp"}
    paths: list[Path] = []
    for raw in inputs:
        p = Path(raw).expanduser().resolve()
        if p.is_file() and p.suffix.lower() in exts:
            paths.append(p)
        elif p.is_dir():
            for file_path in sorted(p.rglob("*")):
                if file_path.is_file() and file_path.suffix.lower() in exts:
                    paths.append(file_path)
    return paths


def main() -> int:
    """Execute CLI flow for detecting CCCD QR data from images.

    The function parses command-line arguments, expands input paths, processes
    each image, and prints a final success summary.

    Args:
        None.

    Returns:
        Process exit code (0 for normal execution, 1 when no valid input files).
    """
    parser = argparse.ArgumentParser(
        description="Detect and decode CCCD QR from images (supports HEIC/HEIF).",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Image files or folders containing images.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save debug images of all preprocessing variants.",
    )
    args = parser.parse_args()

    image_paths = gather_image_paths(args.inputs)
    if not image_paths:
        print("No valid image files found.")
        return 1

    debug_dir = None
    if args.debug:
        debug_dir = Path("debug_variants")
        debug_dir.mkdir(exist_ok=True)
        print(f"[DEBUG] Saving variant images to {debug_dir.absolute()}")

    success_count = 0
    for path in image_paths:
        print(f"\n--- Processing: {path} ---")
        if read_qr_from_cccd(path, debug_dir=debug_dir):
            success_count += 1
        print("--------------------------")

    print(f"\nDone. Success: {success_count}/{len(image_paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

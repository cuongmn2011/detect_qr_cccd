import argparse
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
import zxingcpp

register_heif_opener()

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
    print(f"[OK] Loaded image: {image_path} | shape={img.shape}")
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

    print(f"  -> Deskew rotation: {median_angle:.2f} degrees")
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), median_angle, 1.0)
    deskewed = cv2.warpAffine(
        img,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return deskewed


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

    Args:
        img: Input image as a BGR ndarray.

    Returns:
        A dictionary mapping region names to cropped image ndarrays.
    """
    h, w = img.shape[:2]
    crops: dict[str, np.ndarray] = {}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 0)

    for block_size in [11, 21, 31]:
        binary = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            2,
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
                    pad = int(max(bw, bh) * 0.15)
                    x1 = max(0, x - pad)
                    y1 = max(0, y - pad)
                    x2 = min(w, x + bw + pad)
                    y2 = min(h, y + bh + pad)
                    key = f"contour_{block_size}_{x}_{y}"
                    crops[key] = img[y1:y2, x1:x2]

    for block_size in [11, 21]:
        binary = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            2,
        )
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

    for row in range(3):
        for col in range(3):
            y1 = int(h * row / 3)
            y2 = int(h * (row + 1) / 3)
            x1 = int(w * col / 3)
            x2 = int(w * (col + 1) / 3)
            crops[f"grid_{row}_{col}"] = img[y1:y2, x1:x2]

    crops["full"] = img
    print(f"  -> Total candidate regions: {len(crops)}")
    return crops


def preprocess_variants(img: np.ndarray) -> dict[str, np.ndarray]:
    """Create multiple preprocessing variants to improve QR decoding.

    Includes standard variants, glare handling, and upscaling for robustness.

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

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    clahe_aggressive = cv2.createCLAHE(clipLimit=5.0, tileGridSize=(4, 4))
    enhanced_aggressive = clahe_aggressive.apply(gray)
    sharp_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    h, w = gray.shape

    return {
        "color": img,
        "gray": gray,
        "enhanced": enhanced,
        "sharpened": cv2.filter2D(enhanced, -1, sharp_kernel),
        "otsu": cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        "denoise": cv2.fastNlMeansDenoising(gray, h=10),
        "bilateral": cv2.bilateralFilter(gray, 9, 75, 75),
        "clahe_aggressive": enhanced_aggressive,
        "median": cv2.medianBlur(gray, 5),
        "resize_2x": cv2.resize(enhanced, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC),
        "resize_3x": cv2.resize(enhanced, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC),
    }


def try_decode_qr_only(img: np.ndarray) -> list[Any]:
    """Decode barcodes from an image and keep only QR results.

    Args:
        img: Input image ndarray accepted by zxingcpp.

    Returns:
        A list of decoded barcode objects filtered to QR format only.
    """
    results = zxingcpp.read_barcodes(img)
    return [r for r in results if "QR" in str(r.format)]


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


def detect_cccd_from_image(img: np.ndarray) -> dict[str, Any]:
    """Detect and decode CCCD QR data from a single image.

    The function runs deskew, candidate extraction, preprocessing expansion, and
    QR decoding. It returns immediately on the first successful decode.

    Args:
        img: Input image as a BGR ndarray.

    Returns:
        A dictionary with detection status and decoded content:
        - detected: whether a QR code was decoded
        - region: candidate region name used for successful decode
        - variant: preprocessing variant name used for successful decode
        - raw_data: original decoded payload string or None
        - fields: list of parsed values
        - mapped: labeled field dictionary
    """
    img = deskew(img)
    crops = find_qr_candidates(img)

    for crop_name, cropped in crops.items():
        if cropped.size == 0:
            continue
        variants = preprocess_variants(cropped)
        for variant_name, variant_img in variants.items():
            qr_results = try_decode_qr_only(variant_img)
            if qr_results:
                result = qr_results[0]
                parsed = parse_cccd_fields(result.text)
                return {
                    "detected": True,
                    "region": crop_name,
                    "variant": variant_name,
                    "raw_data": parsed["raw_data"],
                    "fields": parsed["fields"],
                    "mapped": parsed["mapped"],
                }

    return {
        "detected": False,
        "region": None,
        "variant": None,
        "raw_data": None,
        "fields": [],
        "mapped": {},
    }


def read_qr_from_cccd(image_path: Path) -> bool:
    """Run full CCCD QR decoding pipeline for one image path.

    The function loads the image, executes detection, prints details, and
    reports success/failure for batch processing.

    Args:
        image_path: Path to an input image file.

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
    result = detect_cccd_from_image(img)

    if result["detected"]:
        print(
            f"\n[SUCCESS] QR detected "
            f"(region={result['region']}, variant={result['variant']})"
        )
        print(f"\nRaw data: {result['raw_data']}")
        print_cccd_qr_data(result["raw_data"])
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
    args = parser.parse_args()

    image_paths = gather_image_paths(args.inputs)
    if not image_paths:
        print("No valid image files found.")
        return 1

    success_count = 0
    for path in image_paths:
        print(f"\n--- Processing: {path} ---")
        if read_qr_from_cccd(path):
            success_count += 1
        print("--------------------------")

    print(f"\nDone. Success: {success_count}/{len(image_paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

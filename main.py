import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener
import zxingcpp

register_heif_opener()

FIELD_NAMES = [
    "So CCCD",
    "So CMND cu",
    "Ho va ten",
    "Ngay sinh",
    "Gioi tinh",
    "Dia chi",
    "Ngay cap",
]


def load_image(image_path: Path):
    pil_img = Image.open(image_path).convert("RGB")
    img = np.array(pil_img)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    print(f"[OK] Loaded image: {image_path} | shape={img.shape}")
    return img


def deskew(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=80,
        minLineLength=100,
        maxLineGap=10,
    )
    if lines is None:
        return img

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if -45 < angle < 45:
            angles.append(angle)

    if not angles:
        return img

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:
        return img

    print(f"  -> Deskew rotate {median_angle:.2f} degrees")
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), median_angle, 1.0)
    deskewed = cv2.warpAffine(
        img,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return deskewed


def find_qr_candidates(img):
    h, w = img.shape[:2]
    crops = {}

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

    def find_finder_patterns(binary_img):
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
            print(f"  -> Finder pattern area: ({x1},{y1}) -> ({x2},{y2})")

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


def preprocess_variants(img):
    if len(img.shape) == 2:
        gray = img
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    sharp_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    h, w = gray.shape

    return {
        "color": img,
        "gray": gray,
        "enhanced": enhanced,
        "sharpened": cv2.filter2D(enhanced, -1, sharp_kernel),
        "otsu": cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
        "denoise": cv2.fastNlMeansDenoising(gray, h=10),
        "resize_2x": cv2.resize(enhanced, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC),
        "resize_3x": cv2.resize(enhanced, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC),
    }


def try_decode_qr_only(img):
    results = zxingcpp.read_barcodes(img)
    return [r for r in results if "QR" in str(r.format)]


def parse_cccd_fields(raw_data: str):
    fields = raw_data.strip().split("|")
    mapped = {}
    for i, value in enumerate(fields):
        label = FIELD_NAMES[i] if i < len(FIELD_NAMES) else f"Truong {i + 1}"
        mapped[label] = value
    return {
        "raw_data": raw_data,
        "fields": fields,
        "mapped": mapped,
    }


def parse_cccd_qr(raw_data: str):
    parsed = parse_cccd_fields(raw_data)
    print("\nCCCD data:")
    print("-" * 40)
    for label, value in parsed["mapped"].items():
        print(f"  {label}: {value}")
    print("-" * 40)


def detect_cccd_from_image(img):
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


def read_qr_from_cccd(image_path: Path):
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
        parse_cccd_qr(result["raw_data"])
        return True

    print("\n[FAILED] QR code not found.")
    print("Hint: Ensure enough light, avoid blur, and keep QR at least 1/4 of frame.")
    return False


def gather_image_paths(inputs):
    exts = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".webp"}
    paths = []
    for raw in inputs:
        p = Path(raw).expanduser().resolve()
        if p.is_file() and p.suffix.lower() in exts:
            paths.append(p)
        elif p.is_dir():
            for file_path in sorted(p.rglob("*")):
                if file_path.is_file() and file_path.suffix.lower() in exts:
                    paths.append(file_path)
    return paths


def main():
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

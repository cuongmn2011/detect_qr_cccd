"""
Test upscaling with small image (simulate API upload scenario)
"""
import cv2
import logging
from pathlib import Path
from main import detect_cccd_from_image, load_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load a test image and resize to small size (simulate API upload)
original_path = Path("asset/CCCD_1.jpg")
img_large = load_image(original_path)
logger.info(f"Original image: {img_large.shape}")

# Resize to small (like API upload might do)
img_small = cv2.resize(img_large, (300, 200))  # Even smaller than API case
logger.info(f"Resized to: {img_small.shape}")

# Test detection on small image
print("\n=== Testing with small image (300x200) ===")
result = detect_cccd_from_image(img_small, detect_mode="fast")
print(f"Detected: {result['detected']}")
print(f"Region: {result['region']}")
print(f"Variant: {result['variant']}")
if result['detected']:
    print(f"QR Data: {result['raw_data'][:50]}...")

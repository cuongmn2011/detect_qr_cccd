"""
Test script to simulate Celery task detection on all asset images.
This simulates how Celery worker would process images.
"""
import os
import sys
from pathlib import Path
import cv2
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import main detection function (this will trigger _init_wechat)
from main import detect_cccd_from_image, load_image

# Get all images in asset folder
asset_dir = Path(__file__).parent / "asset"
image_files = sorted(asset_dir.glob("*.jpg")) + sorted(asset_dir.glob("*.png"))

logger.info(f"Found {len(image_files)} images in asset folder")
logger.info(f"Testing detection on all images...\n")

success_count = 0
results = []

for image_path in image_files:
    filename = image_path.name
    try:
        # Load image (same as tasks.py would do)
        img = load_image(image_path)

        # Run detection with fast mode (same as API default)
        result = detect_cccd_from_image(img, detect_mode="fast")

        if result['detected']:
            success_count += 1
            region = result.get('region', '?')
            variant = result.get('variant', '?')
            raw = result.get('raw_data', '')[:50]
            results.append({
                'file': filename,
                'status': 'SUCCESS',
                'region': region,
                'variant': variant,
                'data': raw
            })
            print(f"[OK] {filename:25} | region={region:20} | variant={variant:15}")
        else:
            results.append({
                'file': filename,
                'status': 'FAILED',
                'region': None,
                'variant': None,
                'data': None
            })
            print(f"[NO] {filename:25} | No QR detected")

    except Exception as e:
        print(f"[ER] {filename:25} | {str(e)}")
        results.append({
            'file': filename,
            'status': 'ERROR',
            'error': str(e)
        })

print("\n" + "="*80)
print(f"SUMMARY: {success_count}/{len(image_files)} images detected successfully ({100*success_count//len(image_files)}%)")
print("="*80)

for r in results:
    if r['status'] == 'SUCCESS':
        print(f"[OK] {r['file']:25} (via {r['region']:20})")
    else:
        print(f"[NO] {r['file']:25} ({r['status']})")

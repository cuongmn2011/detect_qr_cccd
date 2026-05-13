#!/usr/bin/env python
"""Test detection accuracy across all images in asset/ folder."""
import requests
import json
import time
from pathlib import Path

API_URL = "http://127.0.0.1:8000/decode/path"
ASSET_DIR = Path("asset")

def test_image(image_path: Path, detect_mode: str = "deep") -> bool:
    """Test a single image. Returns True if QR detected."""
    try:
        response = requests.post(
            f"{API_URL}?detect_mode={detect_mode}",
            json={"image_path": str(image_path)},
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            return result.get("detected", False)
    except Exception as e:
        print(f"  Error: {e}")
    return False

def main():
    images = sorted([f for f in ASSET_DIR.glob("*.jpg") if f.is_file()])
    print(f"\n{'='*70}")
    print(f"Testing {len(images)} images (Fast-Detect vs Deep-Detect)")
    print(f"{'='*70}\n")

    fast_results = {}
    deep_results = {}

    for img_path in images:
        print(f"Testing {img_path.name}...", end="", flush=True)

        # Test Fast-Detect
        fast = test_image(img_path, detect_mode="fast")
        time.sleep(0.5)

        # Test Deep-Detect
        deep = test_image(img_path, detect_mode="deep")
        time.sleep(0.5)

        fast_results[img_path.name] = fast
        deep_results[img_path.name] = deep

        print(f" Fast={fast} Deep={deep}")

    # Calculate stats
    fast_success = sum(fast_results.values())
    deep_success = sum(deep_results.values())
    total = len(images)

    print(f"\n{'='*70}")
    print(f"ACCURACY RESULTS")
    print(f"{'='*70}")
    print(f"\nFast-Detect (WeChat only):     {fast_success}/{total} = {fast_success/total*100:.1f}%")
    print(f"Deep-Detect (+ region-based): {deep_success}/{total} = {deep_success/total*100:.1f}%")
    print(f"Improvement:                  +{deep_success-fast_success} images (+{(deep_success-fast_success)/total*100:.1f}%)")

    print(f"\n{'Detailed Results:':^70}")
    print(f"{'-'*70}")
    print(f"{'Image':<30} {'Fast':<10} {'Deep':<10} {'Status':<20}")
    print(f"{'-'*70}")
    for img_name in fast_results:
        fast = 'YES' if fast_results[img_name] else 'NO'
        deep = 'YES' if deep_results[img_name] else 'NO'
        status = 'Recovered' if (not fast_results[img_name] and deep_results[img_name]) else ''
        print(f"{img_name:<30} {fast:<10} {deep:<10} {status:<20}")

    print(f"{'-'*70}\n")

if __name__ == "__main__":
    main()

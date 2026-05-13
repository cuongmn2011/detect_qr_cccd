import os
import cv2
import numpy as np
from io import BytesIO
import logging
import time
from PIL import Image
import redis as redis_lib

from celery_app import celery
from main import detect_cccd_from_image
import logging

logger = logging.getLogger('tasks')

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis = redis_lib.from_url(REDIS_URL)


@celery.task(bind=True, name="detect_qr")
def detect_qr_task(self, image_key: str, detect_mode: str = "deep") -> dict:
    """Celery task: load image from Redis, detect QR, return result.

    Args:
        image_key: Redis key where image bytes are stored (UUID-based)
        detect_mode: "fast" (Strategy 1 only) or "deep" (Strategy 1 + Strategy 2)

    Returns:
        Detection result dict from detect_cccd_from_image()
        Structure: {detected, region, variant, raw_data, fields, mapped}
    """
    start_time = time.time()
    logger.info(f"[detect_qr] task started | image_key={image_key} | detect_mode={detect_mode}")

    try:
        try:
            raw = _redis.get(image_key)
        except Exception as e:
            raise RuntimeError(f"Failed to retrieve image from Redis: {str(e)}")

        _redis.delete(image_key)

        if raw is None:
            raise ValueError("Image key expired or not found")

        try:
            pil_img = Image.open(BytesIO(raw)).convert("RGB")
            img = np.array(pil_img)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            logger.warning(f"[task] Image decoded: {img.shape}")
        except (IOError, OSError) as e:
            raise ValueError(f"Invalid image format: {str(e)}")

        logger.warning(f"[task] Calling detect_cccd_from_image with detect_mode={detect_mode}")
        result = detect_cccd_from_image(img, detect_mode=detect_mode)
        logger.warning(f"[task] detect_cccd_from_image returned: detected={result.get('detected')}")

        duration = time.time() - start_time
        logger.info(f"[detect_qr] task completed | image_key={image_key} | detected={result.get('detected', False)} | duration={duration:.2f}s")

        return result
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(f"[detect_qr] task failed | image_key={image_key} | error={str(exc)} | duration={duration:.2f}s", exc_info=True)
        raise

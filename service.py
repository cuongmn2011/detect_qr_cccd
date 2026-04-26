from io import BytesIO
from pathlib import Path
import asyncio
import os
import time
import uuid
import logging

import cv2
import numpy as np
import redis as redis_lib
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from PIL import Image

from main import detect_cccd_from_image
from tasks import detect_qr_task
import logging

logger = logging.getLogger('service')


app = FastAPI(title="detectQRCCCD Service", version="1.0.0")
WEB_UI_FILE = Path(__file__).with_name("web").joinpath("index.html")

# Redis configuration for Celery task queue
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis = redis_lib.from_url(REDIS_URL)
IMAGE_TTL = 300  # 5 minutes TTL for temporary image storage
PREVIEW_TTL = 300  # 5 minutes TTL for preview image in Redis


class PathRequest(BaseModel):
    image_path: str


def _load_image_from_bytes(data: bytes):
    pil_img = Image.open(BytesIO(data)).convert("RGB")
    img = np.array(pil_img)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def _load_image_from_path(image_path: str):
    path = Path(image_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    pil_img = Image.open(path).convert("RGB")
    img = np.array(pil_img)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def _save_preview_to_redis(img: np.ndarray, request_id: str) -> str:
    """Encode image and save to Redis with TTL, return preview URL."""
    success, encoded = cv2.imencode(".jpg", img)
    if not success:
        raise RuntimeError("Cannot encode image for preview")

    preview_key = f"preview:{request_id}"
    _redis.setex(preview_key, PREVIEW_TTL, encoded.tobytes())
    return f"/current-detect-image/{request_id}"


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/")
def web_ui():
    if not WEB_UI_FILE.exists():
        raise HTTPException(status_code=404, detail="Web UI file not found")
    return FileResponse(WEB_UI_FILE)


@app.get("/current-detect-image/{request_id}")
def current_detect_image(request_id: str):
    """Retrieve preview image from Redis by request ID."""
    preview_key = f"preview:{request_id}"
    image_bytes = _redis.get(preview_key)
    if not image_bytes:
        raise HTTPException(status_code=404, detail="Image not found or expired (TTL 5 minutes)")
    return Response(content=image_bytes, media_type="image/jpeg")


@app.post("/decode/file")
async def decode_from_upload(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty file")

        request_id = str(uuid.uuid4())
        image_key = f"img:{request_id}"
        logger.info(f"POST /decode/file | file={file.filename} | size={len(raw)} bytes | request_id={request_id}")
        _redis.setex(image_key, IMAGE_TTL, raw)

        task = detect_qr_task.delay(image_key)

        # Poll for task result (avoid task.get() which can cause issues)
        start_time = time.time()
        timeout = 60
        while not task.ready():
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task timeout after {timeout}s")
            await asyncio.sleep(0.1)

        if task.failed():
            raise Exception(f"Task failed: {task.info}")

        result = task.result

        img = _load_image_from_bytes(raw)
        image_url = _save_preview_to_redis(img, request_id)

        detected = result.get('detected', False)
        logger.info(f"POST /decode/file | request_id={request_id} | detected={detected} | region={result.get('region', 'N/A')}")

        return {
            "filename": file.filename,
            "request_id": request_id,
            "current_image_url": image_url,
            **result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"POST /decode/file error: {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/decode/path")
async def decode_from_path(payload: PathRequest):
    try:
        img = _load_image_from_path(payload.image_path)
        success, encoded = cv2.imencode(".jpg", img)
        if not success:
            raise RuntimeError("Cannot encode image")
        raw = encoded.tobytes()

        request_id = str(uuid.uuid4())
        image_key = f"img:{request_id}"
        logger.info(f"POST /decode/path | path={payload.image_path} | size={len(raw)} bytes | request_id={request_id}")
        _redis.setex(image_key, IMAGE_TTL, raw)

        task = detect_qr_task.delay(image_key)

        # Poll for task result (avoid task.get() which can cause issues)
        start_time = time.time()
        timeout = 60
        while not task.ready():
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task timeout after {timeout}s")
            await asyncio.sleep(0.1)

        if task.failed():
            raise Exception(f"Task failed: {task.info}")

        result = task.result

        image_url = _save_preview_to_redis(img, request_id)

        detected = result.get('detected', False)
        logger.info(f"POST /decode/path | request_id={request_id} | detected={detected} | region={result.get('region', 'N/A')}")

        return {
            "image_path": str(Path(payload.image_path).expanduser().resolve()),
            "request_id": request_id,
            "current_image_url": image_url,
            **result,
        }
    except FileNotFoundError as exc:
        logger.error(f"POST /decode/path error: file not found - {str(exc)}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"POST /decode/path error: {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

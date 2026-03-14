from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from PIL import Image

from main import detect_cccd_from_image


app = FastAPI(title="detectQRCCCD Service", version="1.0.0")


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


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/decode/file")
async def decode_from_upload(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty file")
        img = _load_image_from_bytes(raw)
        result = detect_cccd_from_image(img)
        return {
            "filename": file.filename,
            **result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/decode/path")
def decode_from_path(payload: PathRequest):
    try:
        img = _load_image_from_path(payload.image_path)
        result = detect_cccd_from_image(img)
        return {
            "image_path": str(Path(payload.image_path).expanduser().resolve()),
            **result,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

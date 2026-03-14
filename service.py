from io import BytesIO
from pathlib import Path
import time

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from PIL import Image

from main import detect_cccd_from_image


app = FastAPI(title="detectQRCCCD Service", version="1.0.0")
WEB_UI_FILE = Path(__file__).with_name("web").joinpath("index.html")
RUNTIME_DIR = Path(__file__).with_name("runtime").joinpath("detect")
CURRENT_DETECT_FILE = RUNTIME_DIR.joinpath("current_detect.jpg")


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


def _clear_detect_cache() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for path in RUNTIME_DIR.glob("*"):
        if path.is_file():
            path.unlink()


def _save_current_detect_image(img: np.ndarray) -> str:
    _clear_detect_cache()
    success, encoded = cv2.imencode(".jpg", img)
    if not success:
        raise RuntimeError("Cannot encode image for preview")
    CURRENT_DETECT_FILE.write_bytes(encoded.tobytes())
    return f"/current-detect-image?t={int(time.time() * 1000)}"


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/")
def web_ui():
    if not WEB_UI_FILE.exists():
        raise HTTPException(status_code=404, detail="Web UI file not found")
    return FileResponse(WEB_UI_FILE)


@app.get("/current-detect-image")
def current_detect_image():
    if not CURRENT_DETECT_FILE.exists():
        raise HTTPException(status_code=404, detail="No current detect image")
    return FileResponse(CURRENT_DETECT_FILE)


@app.post("/decode/file")
async def decode_from_upload(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty file")
        img = _load_image_from_bytes(raw)
        image_url = _save_current_detect_image(img)
        result = detect_cccd_from_image(img)
        return {
            "filename": file.filename,
            "current_image_url": image_url,
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

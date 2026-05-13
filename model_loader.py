"""Load WeChat QRCode model files from local storage."""
import os
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):   # PyInstaller EXE
        return Path(sys.executable).parent
    return Path(__file__).parent        # source mode


def get_model_dir() -> Path:
    """Return path to models/wechat_qrcode directory."""
    path = _base_dir() / "models" / "wechat_qrcode"
    import sys
    if getattr(sys, "frozen", False):
        print(f"[model_loader] EXE mode: base_dir={_base_dir()} -> model_dir={path}")
    return path


def models_available() -> bool:
    """Check if all 4 model files exist."""
    model_dir = get_model_dir()
    files = ["detect.prototxt", "detect.caffemodel", "sr.prototxt", "sr.caffemodel"]
    return all((model_dir / f).exists() for f in files)


def get_model_paths() -> dict:
    """Return dict of {filename: full_path} for all 4 models."""
    model_dir = get_model_dir()
    return {
        "detect_proto": str(model_dir / "detect.prototxt"),
        "detect_model": str(model_dir / "detect.caffemodel"),
        "sr_proto": str(model_dir / "sr.prototxt"),
        "sr_model": str(model_dir / "sr.caffemodel"),
    }

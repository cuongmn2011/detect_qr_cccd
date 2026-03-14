# detectQRCCCD

Python project to detect and decode QR data on Vietnamese Citizen ID cards (CCCD) from images.

## Requirements

- Python 3.9+
- macOS/Linux shell (zsh, bash)
- Dependency is pinned to `zxing-cpp<3` for Python 3.9 compatibility

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt
```

## Run CLI

Run with one or more image files:

```bash
python3 main.py /path/to/image1.jpg /path/to/image2.heic
```

Run with a folder:

```bash
python3 main.py /path/to/image-folder
```

## Run As A Service (for other apps)

Start local API:

```bash
source .venv/bin/activate
python3 -m uvicorn service:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Call API with local file path:

```bash
curl -X POST http://127.0.0.1:8000/decode/path \
  -H "Content-Type: application/json" \
  -d '{"image_path":"/Users/itcuong2011/MyData/detectQRCCCD/asset/IMG_4310.png"}'
```

Call API by uploading file:

```bash
curl -X POST http://127.0.0.1:8000/decode/file \
  -F "file=@/Users/itcuong2011/MyData/detectQRCCCD/asset/IMG_4310.png"
```

API JSON response includes:

- `detected`: true/false
- `region`: successful crop region
- `variant`: successful preprocessing variant
- `raw_data`: raw QR text
- `fields`: list split by `|`
- `mapped`: labeled object (`So CCCD`, `Ho va ten`, etc.)

## Run With Docker

### Option 1: Docker CLI

Build image:

```bash
docker build -t detectqrcccd-api:latest .
```

Run container:

```bash
docker run --rm -p 8000:8000 --name detectqrcccd-api detectqrcccd-api:latest
```

If you want to use `/decode/path` with local images, mount a local folder into the container:

```bash
docker run --rm -p 8000:8000 \
  -v /Users/itcuong2011/MyData/detectQRCCCD/asset:/data:ro \
  --name detectqrcccd-api \
  detectqrcccd-api:latest
```

Then call API:

```bash
curl -X POST http://127.0.0.1:8000/decode/path \
  -H "Content-Type: application/json" \
  -d '{"image_path":"/data/IMG_4310.png"}'
```

### Option 2: Docker Compose

Build and run:

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f
```

Stop service:

```bash
docker compose down
```

## What The Program Does

- Deskews image automatically
- Finds likely QR candidate regions
- Generates multiple preprocessing variants
- Decodes QR only (ignores 1D barcodes)
- Parses CCCD data fields from QR text

## Supported Image Formats

- jpg
- jpeg
- png
- heic
- heif
- bmp
- tif
- tiff
- webp

## Common Issues

1. `zsh: command not found: python`

Use `python3` instead of `python`:

```bash
python3 main.py /path/to/image.png
```

2. `ModuleNotFoundError: No module named 'cv2'`

Dependencies are not installed in the active virtual environment. Run:

```bash
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

3. `zxing-cpp` installation error

Upgrade build tooling and install again:

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install "zxing-cpp<3"
```

## Run In Background On macOS (launchd)

1. Create file `~/Library/LaunchAgents/com.detectqrcccd.api.plist` with the content below (adjust `ProgramArguments` paths for your machine):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.detectqrcccd.api</string>

    <key>ProgramArguments</key>
    <array>
      <string>/Users/itcuong2011/MyData/detectQRCCCD/.venv/bin/python3</string>
      <string>-m</string>
      <string>uvicorn</string>
      <string>service:app</string>
      <string>--host</string>
      <string>127.0.0.1</string>
      <string>--port</string>
      <string>8000</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/itcuong2011/MyData/detectQRCCCD</string>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/itcuong2011/MyData/detectQRCCCD/service.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/itcuong2011/MyData/detectQRCCCD/service.err.log</string>
  </dict>
</plist>
```

2. Load service:

```bash
launchctl load ~/Library/LaunchAgents/com.detectqrcccd.api.plist
```

3. Reload service after code updates:

```bash
launchctl unload ~/Library/LaunchAgents/com.detectqrcccd.api.plist
launchctl load ~/Library/LaunchAgents/com.detectqrcccd.api.plist
```

4. Check logs:

```bash
tail -f /Users/itcuong2011/MyData/detectQRCCCD/service.log
tail -f /Users/itcuong2011/MyData/detectQRCCCD/service.err.log
```

## Quick Example

```bash
cd /Users/itcuong2011/MyData/detectQRCCCD
source .venv/bin/activate
python3 main.py /Users/itcuong2011/MyData/detectQRCCCD/asset/IMG_4310.png
```

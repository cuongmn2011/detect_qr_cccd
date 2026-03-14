# detectQRCCCD

Du an Python de detect va doc QR tren CCCD tu anh.

## Yeu cau

- Python 3.9+
- macOS/Linux shell (zsh, bash)
- Da pin dependency `zxing-cpp<3` de tuong thich Python 3.9

## Cai dat

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt
```

## Cach chay

Chay voi mot hoac nhieu file anh:

```bash
python3 main.py /duong-dan/toi/anh1.jpg /duong-dan/toi/anh2.heic
```

Chay voi thu muc anh:

```bash
python3 main.py /duong-dan/toi/thu-muc-anh
```

## Chay nhu service (de app khac goi)

Khoi dong API local:

```bash
source .venv/bin/activate
python3 -m uvicorn service:app --host 0.0.0.0 --port 8000
```

Kiem tra service:

```bash
curl http://127.0.0.1:8000/health
```

Goi API bang duong dan file local:

```bash
curl -X POST http://127.0.0.1:8000/decode/path \
	-H "Content-Type: application/json" \
	-d '{"image_path":"/Users/itcuong2011/MyData/detectQRCCCD/asset/IMG_4310.png"}'
```

Goi API bang upload file:

```bash
curl -X POST http://127.0.0.1:8000/decode/file \
	-F "file=@/Users/itcuong2011/MyData/detectQRCCCD/asset/IMG_4310.png"
```

API tra JSON gom:

- detected: true/false
- region: vung crop detect thanh cong
- variant: bien the xu ly anh detect thanh cong
- raw_data: chuoi QR goc
- fields: danh sach field tach bang dau `|`
- mapped: object da gan nhan (So CCCD, Ho va ten, ...)

## Chay bang Docker

### Cach 1: Docker CLI

Build image:

```bash
docker build -t detectqrcccd-api:latest .
```

Run container:

```bash
docker run --rm -p 8000:8000 --name detectqrcccd-api detectqrcccd-api:latest
```

Neu muon goi endpoint `/decode/path` voi anh local, mount thu muc anh vao container:

```bash
docker run --rm -p 8000:8000 \
	-v /Users/itcuong2011/MyData/detectQRCCCD/asset:/data:ro \
	--name detectqrcccd-api \
	detectqrcccd-api:latest
```

Khi do goi API:

```bash
curl -X POST http://127.0.0.1:8000/decode/path \
	-H "Content-Type: application/json" \
	-d '{"image_path":"/data/IMG_4310.png"}'
```

### Cach 2: Docker Compose

Build va chay:

```bash
docker compose up -d --build
```

Xem log:

```bash
docker compose logs -f
```

Dung service:

```bash
docker compose down
```

## Chuong trinh se tu dong

- deskew anh
- tim cac vung co kha nang la QR
- tao nhieu bien the xu ly anh
- decode QR (bo qua barcode 1D)
- parse thong tin CCCD tu du lieu QR

## Dinh dang anh ho tro

- jpg
- jpeg
- png
- heic
- heif
- bmp
- tif
- tiff
- webp

## Loi thuong gap

1. `zsh: command not found: python`

Dung `python3` thay vi `python`:

```bash
python3 main.py /duong-dan/toi/anh.png
```

2. `ModuleNotFoundError: No module named 'cv2'`

Ban chua cai dependency trong dung virtual environment. Chay lai:

```bash
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

3. Loi cai `zxing-cpp`

Thu nang cap cong cu build va cai lai:

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install "zxing-cpp<3"
```

## Chay ngầm tren macOS bang launchd

1. Tao file `~/Library/LaunchAgents/com.detectqrcccd.api.plist` voi noi dung sau (doi lai `ProgramArguments` theo duong dan may ban):

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

2. Nap service:

```bash
launchctl load ~/Library/LaunchAgents/com.detectqrcccd.api.plist
```

3. Khoi dong lai service sau khi update code:

```bash
launchctl unload ~/Library/LaunchAgents/com.detectqrcccd.api.plist
launchctl load ~/Library/LaunchAgents/com.detectqrcccd.api.plist
```

4. Kiem tra log:

```bash
tail -f /Users/itcuong2011/MyData/detectQRCCCD/service.log
tail -f /Users/itcuong2011/MyData/detectQRCCCD/service.err.log
```

## Vi du nhanh

```bash
cd /Users/itcuong2011/MyData/detectQRCCCD
source .venv/bin/activate
python3 main.py /Users/itcuong2011/MyData/detectQRCCCD/asset/IMG_4310.png
```

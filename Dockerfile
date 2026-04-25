FROM python:3.11-slim

LABEL maintainer="detectQRCCCD <cuongmn2011@gmail.com>" \
      description="QR detection service for Vietnamese CCCD cards with Celery + Redis support"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime libs required by OpenCV, zxing-cpp, and native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.docker.txt ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r requirements.docker.txt

COPY . .

EXPOSE 8000

# Default command (overridden by docker-compose for different services)
CMD ["python", "-m", "uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]

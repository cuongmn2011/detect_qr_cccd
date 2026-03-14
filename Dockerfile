FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime libs commonly required by OpenCV and native extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.docker.txt ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r requirements.docker.txt

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]

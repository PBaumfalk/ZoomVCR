FROM python:3.15-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Local Whisper is optional (transcription normally runs via the OpenAI-compatible API).
# Build with --build-arg LOCAL_ASR=true to include faster-whisper.
ARG LOCAL_ASR=false
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
 ffmpeg tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng libglib2.0-0 libgl1 \
 fonts-dejavu-core curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-local-asr.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$LOCAL_ASR" = "true" ]; then pip install --no-cache-dir -r requirements-local-asr.txt; fi
COPY zoomvcr ./zoomvcr
ENV PYTHONPATH=/app
RUN useradd -m -u 10001 zoomvcr && mkdir -p /data/recordings /data/hf-cache && chown -R zoomvcr:zoomvcr /data /home/zoomvcr
USER zoomvcr

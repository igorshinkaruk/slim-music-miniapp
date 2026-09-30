FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY bot ./bot

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/tmp/slim_music.db
ENV MEDIA_DIR=/tmp/slim_media
ENV DEV_BYPASS=0

EXPOSE 8001
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8001}

# PhotoDukaan backend for Google Cloud Run.
# IMPORTANT: single gunicorn worker + pin to one instance (min=max=1). The app
# keeps session state in an in-memory dict and serves generated images from
# local disk, so multiple workers/instances would desync state and 404 images.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Cloud Run injects PORT (defaults to 8080). One UvicornWorker = one async event
# loop that still handles concurrent requests (needed for parallel angle gen).
ENV PORT=8080
CMD exec gunicorn main:app \
    -k uvicorn.workers.UvicornWorker \
    --workers 1 \
    --bind 0.0.0.0:$PORT \
    --timeout 300

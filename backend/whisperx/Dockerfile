FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    whisperx \
    fastapi \
    uvicorn \
    python-multipart \
    torch --extra-index-url https://download.pytorch.org/whl/cpu

COPY app.py .

EXPOSE 9000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]

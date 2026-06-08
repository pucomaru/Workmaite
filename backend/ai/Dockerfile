FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg libpq-dev gcc pkg-config \
    libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libcairo2-dev libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev libglib2.0-0 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-cache

COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

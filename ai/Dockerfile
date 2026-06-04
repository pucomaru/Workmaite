# 베이스 이미지: Python 3.11 경량 버전
FROM python:3.11-slim

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# ffmpeg 설치 (openai-whisper 필수 의존성)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# 의존성 파일 먼저 복사 (코드 변경 시 캐시 재사용 가능)
COPY pyproject.toml uv.lock ./

# 가상환경 없이 시스템에 직접 설치 (컨테이너 환경에 적합)
RUN uv sync --frozen --no-dev --no-cache

# 전체 복사
COPY . .

EXPOSE 8000

# uvicorn으로 FastAPI 실행, 0.0.0.0은 외부 접근 허용
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

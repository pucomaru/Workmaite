# 베이스 이미지: Python 3.11 경량 버전
FROM python:3.11-slim

WORKDIR /app

# 의존성 파일 먼저 복사 (코드 변경 시 pip install 캐시 재사용 가능)
COPY requirements.txt .

# --no-cache-dir: 캐시 저장 안 해서 이미지 크기 절약
RUN pip install --no-cache-dir -r requirements.txt

# 전체 복사
COPY . .

EXPOSE 8000

# uvicorn으로 FastAPI 실행, 0.0.0.0은 외부 접근 허용
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
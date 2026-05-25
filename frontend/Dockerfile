# Stage 1: Vue 앱 빌드
FROM node:20-alpine AS build

WORKDIR /app

# 의존성 파일 먼저 복사 (소스코드 변경 시 npm install 캐시 재사용 가능)
COPY package*.json ./

# package-lock.json 기준 정확한 버전 설치 (npm install보다 CI 환경에 적합)
RUN npm ci

# 소스코드 전체 복사
COPY . .

# Vue 앱 빌드 → /app/dist 에 정적 파일 생성
RUN npm run build

# Stage 2: Nginx로 정적 파일 서빙 (Node.js 불필요, 이미지 크기 절약)
FROM nginx:1.27-alpine

# 빌드 결과물만 Nginx 서빙 경로로 복사
COPY --from=build /app/dist /usr/share/nginx/html

# Vue Router history 모드 대응을 위한 Nginx 설정 파일 복사
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
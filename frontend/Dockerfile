# Stage 1: Vue 앱 빌드
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN rm -f package-lock.json && npm install && npm install @rollup/rollup-linux-x64-musl
COPY . .
ARG VITE_API_URL
ARG VITE_AI_URL
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_AI_URL=$VITE_AI_URL
RUN npm run build

# Stage 2: Nginx로 정적 파일 서빙
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
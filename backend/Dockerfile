# Stage 1: Maven으로 jar 빌드
FROM maven:3.9.9-eclipse-temurin-17 AS build

WORKDIR /app

# 의존성 파일 먼저 복사 (소스코드 변경 시 mvn 의존성 다운로드 캐시 재사용 가능)
COPY pom.xml .
COPY src ./src

# 테스트 스킵하고 jar 생성 (테스트는 GitHub Actions에서 별도 step으로 실행)
RUN mvn clean package -DskipTests

# Stage 2: JRE만 있는 가벼운 이미지로 실행 (JDK 불필요, 이미지 크기 절약)
FROM eclipse-temurin:17-jre

WORKDIR /app

# 빌드 결과물인 jar 파일만 복사
COPY --from=build /app/target/*.jar app.jar

EXPOSE 8080

# jar 파일 실행
ENTRYPOINT ["java", "-jar", "app.jar"]
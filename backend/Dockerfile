# Stage 1: Gradle로 jar 빌드
FROM eclipse-temurin:21-jdk AS build
WORKDIR /app
COPY springboot/gradlew .
COPY springboot/gradle gradle
COPY springboot/build.gradle.kts .
COPY springboot/settings.gradle.kts .
COPY springboot/src src
RUN chmod +x gradlew
RUN ./gradlew bootJar -x test

# Stage 2: JRE만 있는 가벼운 이미지로 실행
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/build/libs/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
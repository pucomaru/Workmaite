plugins {
	java
	id("org.springframework.boot") version "3.5.14"
	id("io.spring.dependency-management") version "1.1.7"
}

group = "com.workmaite"
version = "0.0.1-SNAPSHOT"

java {
	toolchain {
		languageVersion = JavaLanguageVersion.of(21)
	}
}

repositories {
	mavenCentral()
}

dependencies {
	implementation("org.springframework.boot:spring-boot-starter-data-jpa")
	implementation("org.springframework.boot:spring-boot-starter-security")
	implementation("org.springframework.boot:spring-boot-starter-validation")
	implementation("org.springframework.boot:spring-boot-starter-web")
	implementation("io.jsonwebtoken:jjwt-api:0.11.5")
	implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.8.8")
	implementation("org.springframework.boot:spring-boot-starter-actuator")
	implementation("io.micrometer:micrometer-registry-prometheus")
	implementation("org.flywaydb:flyway-core")
	runtimeOnly("org.flywaydb:flyway-database-postgresql")
	compileOnly("org.projectlombok:lombok")
	runtimeOnly("org.postgresql:postgresql")
	runtimeOnly("io.jsonwebtoken:jjwt-impl:0.11.5")
	runtimeOnly("io.jsonwebtoken:jjwt-jackson:0.11.5")
	annotationProcessor("org.projectlombok:lombok")
	testImplementation("org.springframework.boot:spring-boot-starter-test")
	testImplementation("org.springframework.security:spring-security-test")
	testCompileOnly("org.projectlombok:lombok")
	testRuntimeOnly("org.junit.platform:junit-platform-launcher")
	testAnnotationProcessor("org.projectlombok:lombok")
}

tasks.withType<Test> {
	useJUnitPlatform()
}

// 로컬 개발 편의: 리포 루트 .env를 bootRun 환경변수로 자동 주입.
// 셸에 이미 export된 변수가 우선하며, .env가 없으면 아무것도 하지 않는다(CI/k8s 영향 없음).
tasks.bootRun {
	val envFile = rootProject.file("../../.env")
	if (envFile.exists()) {
		envFile.readLines(Charsets.UTF_8).forEach { line ->
			val trimmed = line.trim()
			if (trimmed.isEmpty() || trimmed.startsWith("#")) return@forEach
			val idx = trimmed.indexOf('=')
			if (idx <= 0) return@forEach
			val key = trimmed.substring(0, idx).trim()
			if (!Regex("[A-Za-z_][A-Za-z0-9_]*").matches(key)) return@forEach
			var value = trimmed.substring(idx + 1).trim()
			if (value.length >= 2 &&
				((value.first() == '"' && value.last() == '"') ||
					(value.first() == '\'' && value.last() == '\''))
			) {
				value = value.substring(1, value.length - 1)
			}
			if (System.getenv(key) == null) environment(key, value)
		}
	}
}

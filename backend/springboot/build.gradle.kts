plugins {
	java
	id("org.springframework.boot") version "4.1.0"
	id("io.spring.dependency-management") version "1.1.7"
	id("com.diffplug.spotless") version "8.6.0"
	checkstyle
    pmd
    id("com.github.spotbugs") version "6.5.9"
}

spotless {
    encoding("UTF-8") 
    java {
        googleJavaFormat()
		importOrder()
        removeUnusedImports()
        trimTrailingWhitespace()
        endWithNewline()
    }
}

checkstyle {
    toolVersion = "10.12.7"
    // config/checkstyle/checkstyle.xml 에 규칙 파일 둠
}

pmd {
    toolVersion = "6.55.0"
    ruleSetFiles = files("config/pmd/ruleset.xml")  // 커스텀 규칙 쓸 경우
    isIgnoreFailures = false
}

spotbugs {
    ignoreFailures.set(false)
    excludeFilter.set(file("config/spotbugs/exclude.xml"))
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
	implementation("org.springframework.boot:spring-boot-starter-aspectj")
	implementation("org.springframework.boot:spring-boot-starter-data-jpa")
	implementation("org.springframework.boot:spring-boot-starter-security")
	implementation("org.springframework.boot:spring-boot-starter-validation")
	implementation("org.springframework.boot:spring-boot-starter-web")
	implementation("org.springframework.boot:spring-boot-starter-restclient")
	implementation("io.jsonwebtoken:jjwt-api:0.13.0")
	implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:3.0.3")
	implementation("org.springframework.boot:spring-boot-starter-actuator")
	implementation("io.micrometer:micrometer-registry-prometheus")
	compileOnly("org.projectlombok:lombok")
	runtimeOnly("org.postgresql:postgresql")
	runtimeOnly("io.jsonwebtoken:jjwt-impl:0.13.0")
	runtimeOnly("io.jsonwebtoken:jjwt-jackson:0.13.0")
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

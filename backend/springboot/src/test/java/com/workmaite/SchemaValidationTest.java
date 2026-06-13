package com.workmaite;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

/**
 * JPA 엔티티 매핑이 Flyway V1 baseline 스키마와 일치하는지 검증한다 — 코드/DB 스키마 드리프트 탐지용.
 *
 * <p>profile {@code schema}: Flyway(enabled) 가 빈 DB에 V1 baseline을 적용해 스키마를 만들고,
 * Hibernate {@code ddl-auto: validate} 가 엔티티와 대조한다. 엔티티에는 있으나 DB에 없는 컬럼,
 * 타입 불일치 등이 있으면 컨텍스트 로드가 실패하며 어느 테이블/컬럼이 안 맞는지 보고된다.
 *
 * <p>{@code @Tag("schema")} 로 일반 {@code test} 태스크에서는 제외되고, 실 postgres가 있는
 * {@code schemaValidate} 태스크(CI)에서만 실행된다.
 */
@SpringBootTest
@ActiveProfiles("schema")
@Tag("schema")
class SchemaValidationTest {

  @Test
  void entitiesMatchFlywaySchema() {}
}

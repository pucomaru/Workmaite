package com.workmaite;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

/**
 * 엔티티(JPA) 매핑이 실제 DB 스키마와 일치하는지 검증한다 — 레거시/누락 컬럼 탐지용.
 *
 * <p>ddl-auto: validate(read-only)로 컨텍스트를 띄우므로, 엔티티에는 있으나 DB에 없는 컬럼 등 불일치가 있으면 컨텍스트 로드가 실패하며 어느
 * 테이블/컬럼이 안 맞는지 보고된다. 스키마/데이터를 변경하지 않는다.
 *
 * <p>{@code @Tag("schema")}로 기본 {@code test} 태스크에서는 제외된다(빈 DB에서 돌면 실패하므로). 운영 DB를 localhost:5432로
 * port-forward 한 뒤 {@code ./gradlew schemaValidate} 로 실행한다.
 */
@SpringBootTest
@ActiveProfiles({"test", "dbvalidate"})
@Tag("schema")
class SchemaValidationTest {

  @Test
  void entitiesMatchDatabaseSchema() {}
}

package com.workmaite;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

// DB/Spring 컨텍스트를 부팅하지 않는 단위 테스트.
// 구 @SpringBootTest contextLoads()는 test 프로파일(application-test.yaml)의 ddl-auto=create-drop +
// 상속된 DB_URL/DB_PASSWORD 때문에, 운영 자격이 환경에 잡힌 상태로 ./gradlew test|build 가 실행되면
// 운영 DB의 모든 테이블을 DROP할 위험이 있어 제거함. DB 통합 테스트가 필요하면 Testcontainers로 격리할 것.
class WorkmaiteServerApplicationTests {

  @Test
  void mainClassIsPresent() {
    assertNotNull(WorkmaiteServerApplication.class);
  }
}

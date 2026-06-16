package com.workmaite.global.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import io.swagger.v3.oas.models.servers.Server;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * springdoc-openapi 전역 설정. OpenAPI 3.1 문서 메타데이터와 JWT(Bearer) 보안 스킴을 정의해, Swagger
 * UI(/swagger-ui.html)에서 "Authorize" 버튼으로 토큰을 넣고 보호 API를 호출할 수 있게 한다.
 *
 * <p>OAS 버전은 application.yaml의 {@code springdoc.api-docs.version: openapi_3_1} 로 3.1을 출력한다.
 */
@Configuration
public class OpenApiConfig {

  private static final String BEARER_SCHEME = "bearerAuth";

  @Bean
  public OpenAPI workmaiteOpenAPI() {
    return new OpenAPI()
        .info(
            new Info()
                .title("Workma!te Backend API")
                .description(
                    """
                    회의체 운영 AI Agent 서비스 — 인증·권한(JWT/RBAC) 및 도메인 CRUD API (Spring Boot).

                    - **인증**: 로그인(`POST /api/v1/auth/login`)으로 발급된 access token을 우측 상단 \
                    `Authorize`에 입력하세요. (`JWT_SECRET`을 FastAPI와 공유, HS256)
                    - **응답 형식**: 모든 응답은 `ApiResponse {success, message, data}` 로 감쌉니다.
                    - **권한 모델**: 조직 권한(companyRole: USER/COMPANY_ADMIN/SYSTEM_ADMIN) × \
                    회의체 권한(meetingRole: admin/member) 결합 RBAC.
                    - AI·실시간·지식그래프 기능은 별도 FastAPI 서버(`/api/ai`, `/api/agent`, `/ws` 등)가 담당합니다.
                    """)
                .version("v1")
                .contact(new Contact().name("Team No.9")))
        .addServersItem(new Server().url("/").description("기본 (Ingress 상대경로)"))
        .addSecurityItem(new SecurityRequirement().addList(BEARER_SCHEME))
        .components(
            new Components()
                .addSecuritySchemes(
                    BEARER_SCHEME,
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")
                        .description("Spring 발급 JWT access token")));
  }
}

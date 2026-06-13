# AI 데이터 접근 범위 (P3B-1)

AI 에이전트(supervisor 채팅 포함)가 사용자 대신 데이터를 조회할 때 적용되는 범위 규칙.

## 원칙

1. **스코프는 도구 내부에서 강제한다.** 모델이 임의 `meeting_id`를 넘겨도 도구가
   `RunnableConfig`의 허용 범위와 대조해 거부한다 — 프롬프트 지시(모델의 선의)에
   의존하지 않는다.
2. 서버가 라우트 핸들러에서 `configurable`에 주입하는 값이 유일한 신뢰 소스다:
   - `user_id`: 인증된 사용자 (JWT)
   - `allowed_meeting_ids`: `meeting_members` 기준 소속 회의체 (요청 시점 조회)
   - `is_admin`: `users.role == SYSTEM_ADMIN` (P1-3 RBAC)
3. 거부는 모델이 복구할 수 있는 문장으로 반환한다(`[접근 거부] … list_my_meetings로
   확인하세요`) — 모델이 다음 행동을 정정할 수 있게.

## 범위 매트릭스

| 데이터 | 일반 사용자 | SYSTEM_ADMIN |
|---|---|---|
| 회의체 목록/현황/아젠다/보고서 현황 | 소속 회의체만 | 전체 |
| 회의록 의미 검색 (Neo4j) | 소속 회의체의 회의록만 (`mg.pg_id IN allowed`) | 전체 |
| 사용자 디렉터리 | 본인+내 회사+공유 회의체 (MT-3, access_guard) | 전체 |

## 구현 위치

- 도구: `backend/ai/tools/meeting_tools.py` (`SUPERVISOR_TOOLS`)
- HTTP 레이어 가드: `backend/ai/access_guard.py` (P1-4) — 도구 스코프와 별개로 이중 방어
- 회사(company) 차원 스코프: P1-7②/MT-5에서 추가 예정

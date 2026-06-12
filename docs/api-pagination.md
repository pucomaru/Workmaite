# API 페이지네이션 규약 (P8-1)

## 원칙

- **시간순 무한 누적 데이터**(채팅, STT 세그먼트): **keyset 커서** — offset은 누적이 커질수록 느려지고
  실시간 삽입 시 페이지가 밀린다.
- **관리/검색 목록**(회의체, 사용자 등): offset(`page`,`size`) — P8-4에서 적용 예정.
- **호환 모드**: 페이지 파라미터 미지정 시 기존 전체 반환을 유지한다. 프론트 전환이 끝나면
  기본 size를 강제한다(2단계).
- size 상한은 서버가 강제한다 (채팅 100, STT 500).

## 적용된 엔드포인트 (2026-06-12)

### 채팅 이력 — id keyset (Spring·FastAPI 동일 계약)

```
GET /api/v1/chat/messages?threadId={tid}&limit=100          # 최신 100건
GET /api/v1/chat/messages?threadId={tid}&limit=100&beforeId={가장 오래된 id}  # 이전 페이지
GET /api/chats/{context_type}/{context_id}?limit=&before_id=  # FastAPI 동일
```

- 응답은 항상 **시간 오름차순** 배열 (표시 순서 그대로).
- 다음 페이지 커서 = 현재 응답의 첫 요소 `id`.
- 빈 배열 = 더 이상 과거 없음.

### STT 세그먼트 — start_sec keyset

```
GET /api/v1/sessions/{id}/scripts?limit=500                 # 처음부터 500건
GET /api/v1/sessions/{id}/scripts?afterSec={마지막 end/start_sec}&limit=500   # 증분
```

- start_sec 오름차순. 진행 중 세션의 실시간 WS append와 충돌하지 않도록
  afterSec 커서는 "마지막으로 받은 세그먼트의 start_sec"을 사용한다.

## 인덱스 전제 (V4 적용 완료)

- `idx_chat_messages_thread (thread_id, created_at)` — id PK와 결합해 keyset 커버
- `idx_stt_segments_session (session_id, start_sec)`

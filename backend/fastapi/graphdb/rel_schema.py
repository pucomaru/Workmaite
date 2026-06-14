"""그래프 관계 스키마 단일 정의 (SSOT).

이 파일이 회의 지식 그래프의 관계 어휘에 대한 **유일한 권위**다.
- 백엔드: ALLOWED_REL_TYPES(수동 편집 검증 화이트리스트)를 여기서 파생한다.
- 프런트: GET /api/neo4j/rel-schema 로 REL_MATRIX/REL_COLORS를 받아 번들 기본값을 덮어쓴다.

관계명은 neo4j_sync.py가 실제로 쓰는 canonical 이름과 일치해야 한다.
드리프트를 막기 위해 새 관계를 추가할 때 반드시 이 파일에서 시작할 것.
"""

# 노드 타입쌍(프런트 node.type 어휘) → canonical 관계명.
# 키는 "from→to" 정방향. autoRel은 정/역 양방향을 모두 시도한다.
REL_MATRIX: dict[str, str] = {
    # 조직 계층
    "Meetings→company": "포함",
    "dept→company": "소속",
    "person→dept": "소속",
    "dept→Meetings": "참여",
    "dept→dept": "포함",
    # 회의체 간
    "Meetings→Meetings": "관련",
    # 회의체 구성·관할
    "agenda→Meetings": "관할",
    "person→Meetings": "구성원",
    "person→agenda": "담당",
    # 라이프사이클: 아젠다·회의·회의록 (neo4j_sync.py canonical과 일치)
    "agenda→session": "발제세션",  # was 다룸 — sync: Agenda-[발제세션]->Session
    "session→Meetings": "소속",  # was 개최 — sync: Session-[소속]->Meetings
    "minutes→session": "기록",  # was 참조 — sync: Minutes-[기록]->Session
    "person→minutes": "작성",  # was 첨부 — sync: User-[작성]->Minutes
    "person→session": "참석",  # sync: User-[참석]->Session
    "session→session": "후속",
    "minutes→agenda": "도출",
    # 보고자료
    "report→agenda": "첨부",
    "report→Meetings": "첨부",
    # 일반 참조 (canonical 없음 — 자유 연결 폴백)
    "company→minutes": "참조",
    "company→report": "참조",
    "minutes→minutes": "참조",
    "report→report": "참조",
}

# 관계명 → 표시 색상 (프런트 배지/그래프 엣지 공용)
REL_COLORS: dict[str, str] = {
    "포함": "#a89fd4",
    "참여": "#8b7fc0",
    "소속": "#a78bfa",
    "소속회사": "#a78bfa",
    "간사": "#fbbf24",
    "구성원": "#60a5fa",
    "참석": "#93c5fd",
    "담당": "#34d399",
    "담당부서": "#34d399",
    "관할": "#6abba5",
    "발제세션": "#c9a870",
    "도출": "#f472b6",
    "다룸": "#6ee7b7",
    "진행": "#6ee7b7",
    "기록": "#a8a5a2",
    "작성": "#c4b5fd",
    "생성": "#c4b5fd",
    "첨부": "#fb923c",
    "참조": "#7a8090",
    "후속": "#e879f9",
    "후속회의": "#e879f9",
    "출처": "#94a3b8",
    "상위": "#f9a8d4",
    "관련": "#fcd34d",
}

# matrix 밖에서 사용자가 자유 입력할 수 있는 관계 (UI 추천 목록)
FREE_REL_TYPES: set[str] = {
    "연결",
    "협업",
    "공유",
    "지원",
    "검토",
    "출처",
    "참조",
    "관련",
}

# 구조(PG 엔티티)에서 buildGraphNodes가 자동 파생하는 관계 — archive 엔드포인트가
# 수동 관계를 읽어올 때 이 집합은 제외한다(파생 엣지와 중복 방지).
DERIVED_REL_TYPES: set[str] = {
    "포함",
    "참여",
    "소속",
    "소속회사",
    "간사",
    "구성원",
    "참석",
    "작성",
    "기록",
    "담당",
    "담당부서",
    "관할",
    "발제세션",
    "개최",
    "후속",
    "산출",
    "첨부",
    "도출",
    "다룸",
    "생성",
    "진행",
}

# 내부 동기화 전용 관계 (사용자가 직접 만들진 않지만 편집/삭제 대상이 될 수 있어 허용)
_SYNC_ONLY = {"청크", "BELONGS_TO"}

# 수동 편집(POST/PUT/DELETE relationships) 검증 화이트리스트 — 파생값. 손으로 유지하지 말 것.
ALLOWED_REL_TYPES: set[str] = (
    set(REL_MATRIX.values()) | set(REL_COLORS) | FREE_REL_TYPES | _SYNC_ONLY
)

"""그래프 관계 스키마 단일 정의 (SSOT).

이 파일이 회의 지식 그래프의 관계 어휘에 대한 **유일한 권위**다.
★ 임의로 절대 함부로 수정하지 말것.
- 백엔드: ALLOWED_REL_TYPES(수동 편집 검증 화이트리스트)를 여기서 파생한다.
- 프런트: GET /api/neo4j/rel-schema 로 REL_MATRIX/REL_COLORS를 받아 번들 기본값을 덮어쓴다.

★ 드리프트 방지 규칙 (중요):
  1. 관계를 새로 만드는 코드(neo4j_sync MERGE, reconcile_graph 등)는 반드시 아래 canonical 이름만 쓴다.
  2. 같은 의미를 두 이름으로 만들지 않는다. (예: 아젠다↔세션은 `논의` 하나 — 과거 `다룸`/`진행`은 폐지)
     안건으로 들어오는 문서 관계: 회의록→안건은 `도출`, 보고자료→안건은 `취급` — `참조`로 안건을 가리키지 않는다.
  3. 폐지된 옛 이름(생성/진행/다룸/다룸멌)은 graph_analysis._normalize_rel_directions가 주기적으로
     삭제(purge)한다. 정상 경로가 더는 만들지 않으므로 그래프가 정리되면 purge 단계도 제거 가능.
  4. Neo4j는 방향 무관 탐색이 가능하므로 '역방향 별칭'을 따로 만들지 않는다(논의 하나로 양방향 조회).
  5. 회의체↔회의체 `협의`는 PG에 없는 Neo4j 전용·사용자 수동 연결이다. PG 동기화는 이 관계를
     절대 지우지 않으며, 해당 회의체가 의도적으로 삭제될 때만 함께 사라진다(neo4j_sync.delete_meeting).
"""

# 노드 타입쌍(프런트 node.type 어휘) → canonical 관계명. 키는 "from→to" 정방향.
REL_MATRIX: dict[str, str] = {
    # ── 조직 계층 ──
    "Meetings→company": "포함",
    "dept→company": "소속",
    "person→dept": "소속",
    # 부서→회의체: 부서가 (구성원을 통해) 참여하는 회의체. neo4j_sync.sync_meeting_dept_participation이
    # (Department)-[:참여]->(Meetings)를 실제로 생성하며, 프런트 useGraphBuilder도 동일 라벨을 쓴다.
    # (과거 '포함'은 1차 관계가 아니어서 시각화·Neo4j와 불일치했음 → '참여'로 통일)
    "dept→Meetings": "참여",
    "dept→dept": "포함",
    # ── 회의체 간 ──
    "Meetings→Meetings": "협의",
    # ── 안건 간 ──
    "agenda→agenda": "관련",
    # ── 회의체 구성·안건 ──
    "Meetings→agenda": "추출",  # 회의체가 (회의록·보고자료에서) 추출한 안건  ← 과거 'agenda→Meetings 관할' 폐지
    "agenda→dept": "담당부서",  # 안건의 담당 부서  (← 과거 viz의 'agenda→dept 관할' 통일)
    "person→Meetings": "참여",
    "person→agenda": "담당",  # 담당자
    # ── 라이프사이클 (아젠다·회의·회의록) ──
    "agenda→session": "논의",  # 아젠다가 논의된 회의 (← 다룸/진행 폐지, 이것으로 일원화)
    "session→Meetings": "소속",  # DB 보존(질의용) — 단, 그래프 시각화에서는 그리지 않는다.
    "session→minutes": "기록",
    "person→minutes": "작성",
    "person→session": "참석",
    "session→session": "후속",
    "minutes→agenda": "도출",  # 회의록에서 도출된 안건
    # ── 보고자료 ──
    "report→Meetings": "첨부",  # 보고자료가 회의체에 첨부됨  (← 과거 '발제' 폐지)
    "report→agenda": "취급",  # 보고자료가 다루는(취급) 안건  (← 과거 '발제'/'도출' 폐지)
    "dept→report": "작성",  # 부서가 작성한 보고자료
    # 폐지: 관할(=Meetings→agenda 추출로 대체), 발제(=report→Meetings 첨부 / report→agenda 취급으로 대체).
    # 'node→agenda: 참조' 같은 와일드카드는 두지 않는다(과거 드리프트의 원인).
    # 참조는 아래 resolveCanonical 폴백(문서↔문서·회사→문서 등 canonical 없는 쌍)에서만 쓰인다.
}

# 관계명 → 표시 색상 (프런트 배지/그래프 엣지 공용). canonical 관계 + 프런트 표시 전용 라벨만 포함.
REL_COLORS: dict[str, str] = {
    # 조직·구성
    "포함": "#0d9488",  # 실사용
    "소속": "#a78bfa",  # 실사용 (rgb()·이름색 금지 — 프런트 hexToNum이 #hex만 파싱)
    "소속회사": "#a78bfa",  # neo4j 상에는 존재. 미사용, user→company (소속의 회사 직속 변형)
    "운영": "#1e3a5f",  # 실사용
    "참여": "#60a5fa",  # 실사용
    "참석": "#93c5fd",  # 실사용
    "협의": "#60a5fa",  # 실사용. 직접연결
    # 아젠다·담당
    "담당": "#34d399",  # 실사용
    "담당부서": "#a78bfa",  # 실사용 — agenda→dept (안건 담당 부서)
    "추출": "#fbbf24",  # 실사용 — Meetings→agenda (회의체가 추출한 안건)
    "관련": "#fcd34d",  # 실사용
    # 라이프사이클
    "논의": "#ea580c",  # 실사용
    "도출": "#d97706",  # 실사용 — minutes→agenda
    "기록": "#0891b2",  # 실사용
    "작성": "#c4b5fd",  # 실사용 — dept→report (부서가 작성한 보고자료)
    "후속": "#ea580c",  # 실사용
    # 보고자료·참조
    "첨부": "#60a5fa",  # 실사용 — report→Meetings (보고자료 첨부)
    "취급": "#f472b6",  # 실사용 — report→agenda (보고자료가 다루는 안건)
    "참조": "#7a8090",  # 와일드카드
    # 폐지(레거시): "관할"(→추출), "발제"(→첨부/취급). 미마이그레이션 잔존 엣지는 회색 폴백으로 렌더링.
}

# 자동 생성(PG sync + reconcile)되는 관계 — archive 엔드포인트가 '수동' 관계를 읽을 때 제외(중복 방지).
# 실제로 생성되는 것만 나열한다 16개.
DERIVED_REL_TYPES: set[str] = {
    "포함",
    "소속",
    "소속회사",
    "운영",
    "참여",
    "참석",
    "작성",
    "기록",
    "담당",
    "담당부서",
    "추출",
    "논의",
    "후속",
    "첨부",
    "취급",
    "도출",
}

# 내부 동기화 전용 관계 (사용자가 직접 만들진 않지만 편집/삭제 대상이 될 수 있어 허용)
_SYNC_ONLY = {"청크"}

# 수동 편집(POST/PUT/DELETE relationships) 검증 화이트리스트 — 파생값. 손으로 유지하지 말 것.
ALLOWED_REL_TYPES: set[str] = set(REL_MATRIX.values()) | set(REL_COLORS) | _SYNC_ONLY

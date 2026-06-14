"""에이전트 컨텍스트 타입 단일 정의 (HC-8).

agent_logs.context_type 값과 usage.py의 분류 그룹이 여러 파일에 흩어져 있던 것을 통합한다.
새 컨텍스트는 여기에 추가하고, 사용처는 상수를 참조한다.
"""

# 개별 컨텍스트 타입 (agent_logs.context_type)
TASK_EXTRACT = "task_extract"
ARCHIVE_ANALYZE = "archive_analyze"
ARCHIVE_ANALYZE_STREAM = "archive_analyze_stream"
REPORT_REVIEW = "report_review"
MINUTES_GENERATE = "minutes_generate"
MINUTES_STREAM = "minutes_stream"
SUPERVISOR = "supervisor"
AGENDA_EXTRACTION = "agenda_extraction"
AGENDA_COMMIT = "agenda_commit"
FILE_EMBED = "file_embed"  # 파일 임베딩 사용량 귀속 (P2)

# usage 대시보드 분류 그룹
TASK_CONTEXTS = {TASK_EXTRACT}
REPORT_CONTEXTS = {ARCHIVE_ANALYZE, ARCHIVE_ANALYZE_STREAM, REPORT_REVIEW}
MEETING_CONTEXTS = {
    MINUTES_GENERATE,
    MINUTES_STREAM,
    SUPERVISOR,
    AGENDA_EXTRACTION,
    AGENDA_COMMIT,
}


def section_of(ctx: str) -> str:
    """context_type → 대시보드 섹션. agent_* 동적 타입은 meeting으로 분류."""
    if ctx in TASK_CONTEXTS:
        return "task_extraction"
    if ctx in REPORT_CONTEXTS:
        return "report_analysis"
    if ctx in MEETING_CONTEXTS or (ctx or "").startswith("agent_"):
        return "meeting"
    return "other"


# ── 에이전트별 사용량 표시 (P3) — supervisor와 서브에이전트를 구분해서 노출 ──────
# context_type 별 사람이 읽는 라벨 (4섹션 축약 없이 그대로 표시)
CONTEXT_LABELS = {
    SUPERVISOR: "오케스트레이션",
    TASK_EXTRACT: "아젠다 추출",
    AGENDA_EXTRACTION: "아젠다 추출",
    AGENDA_COMMIT: "아젠다 확정",
    ARCHIVE_ANALYZE: "보고서 분석",
    ARCHIVE_ANALYZE_STREAM: "보고서 분석",
    REPORT_REVIEW: "보고서 검토",
    MINUTES_GENERATE: "회의록 생성",
    MINUTES_STREAM: "회의록 생성",
    FILE_EMBED: "파일 임베딩",
}

# context_type → 색상/요약용 에이전트 그룹 키
AGENT_GROUPS = {
    SUPERVISOR: "supervisor",
    TASK_EXTRACT: "agenda",
    AGENDA_EXTRACTION: "agenda",
    AGENDA_COMMIT: "agenda",
    ARCHIVE_ANALYZE: "report",
    ARCHIVE_ANALYZE_STREAM: "report",
    REPORT_REVIEW: "report",
    MINUTES_GENERATE: "minutes",
    MINUTES_STREAM: "minutes",
    FILE_EMBED: "embedding",
}
AGENT_LABELS = {
    "supervisor": "오케스트레이션",
    "agenda": "아젠다 추출",
    "report": "보고서 검토",
    "minutes": "회의록 생성",
    "embedding": "파일 임베딩",
    "other": "기타",
}
AGENT_ORDER = ["supervisor", "agenda", "report", "minutes", "embedding", "other"]


def context_label(ctx: str) -> str:
    """context_type → 사람이 읽는 라벨. 미등록(agent_* 동적 등)은 원본 그대로."""
    return CONTEXT_LABELS.get(ctx, ctx or "기타")


def agent_of(ctx: str) -> str:
    """context_type → 에이전트 그룹 키. 미등록/agent_* 동적은 other."""
    return AGENT_GROUPS.get(ctx, "other")


def agent_label(key: str) -> str:
    return AGENT_LABELS.get(key, key)

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

# usage 대시보드 분류 그룹
TASK_CONTEXTS = {TASK_EXTRACT}
REPORT_CONTEXTS = {ARCHIVE_ANALYZE, ARCHIVE_ANALYZE_STREAM, REPORT_REVIEW}
MEETING_CONTEXTS = {MINUTES_GENERATE, MINUTES_STREAM, SUPERVISOR,
                    AGENDA_EXTRACTION, AGENDA_COMMIT}


def section_of(ctx: str) -> str:
    """context_type → 대시보드 섹션. agent_* 동적 타입은 meeting으로 분류."""
    if ctx in TASK_CONTEXTS:
        return "task_extraction"
    if ctx in REPORT_CONTEXTS:
        return "report_analysis"
    if ctx in MEETING_CONTEXTS or (ctx or "").startswith("agent_"):
        return "meeting"
    return "other"

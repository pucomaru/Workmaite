"""에이전트 요청 단위 회의체 접근 스코프 (멀티테넌트 IDOR 방지).

라우터(supervisor_chat 등)가 요청 시작 시 현재 사용자가 볼 수 있는 회의체 집합을 contextvar로
설정하면, 하위 검색 도구(예: search_knowledge)가 도구 시그니처 변경 없이 이를 읽어 타 회의체·타사
데이터 누수를 차단한다. meeting_tools처럼 RunnableConfig를 못 받는 sub-agent 도구의 스코프 공백을 메운다.
"""

from contextvars import ContextVar

# {"allowed": list[int], "is_admin": bool} | None
meeting_scope_var: ContextVar[dict | None] = ContextVar("meeting_scope", default=None)


def set_meeting_scope(allowed_meeting_ids, is_admin: bool):
    """현재 컨텍스트의 접근 스코프를 설정하고 reset 토큰을 반환한다."""
    return meeting_scope_var.set(
        {"allowed": list(allowed_meeting_ids or []), "is_admin": bool(is_admin)}
    )


def reset_meeting_scope(token) -> None:
    try:
        meeting_scope_var.reset(token)
    except Exception:
        pass


def current_scope_meeting_ids():
    """검색을 제한할 meeting_id 리스트. 제한 없음(관리자/미설정)이면 None을 반환."""
    sc = meeting_scope_var.get()
    if not sc or sc.get("is_admin"):
        return None
    return sc.get("allowed") or []

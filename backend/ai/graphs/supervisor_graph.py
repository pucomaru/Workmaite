"""도구 기반 supervisor 직접응답 에이전트 (P3A-5 2단계 / P3B-2).

기존 supervisor_direct 경로는 Neo4j/DB 컨텍스트를 ~300줄에 걸쳐 사전 조립해
프롬프트에 전부 주입했다(H-6). 이 그래프는 컨텍스트를 **도구로 just-in-time 조회**한다:
- 시스템 프롬프트는 정적(캐시 적중), 데이터는 모델이 필요할 때 도구 호출
- 스코프는 tools/meeting_tools.py가 RunnableConfig 기준으로 강제 (P3B-1)
- 단순 요청은 single-loop(도구 1-2회)로 끝난다 — 다단 그래프 강요 없음

기본 활성화 (P3A-5 3단계 — dev 검증 후 기본 전환). 롤백: SUPERVISOR_TOOLS_MODE=legacy
"""
import logging
import os
import uuid
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

_SYSTEM = """\
당신은 회의체 운영 AI 워크메이트입니다. 사용자의 회의체 현황·아젠다·보고서·회의록 질문에
도구로 데이터를 조회해 한국어로 간결하게 답합니다.

규칙:
- 추측하지 말고 도구로 확인한 데이터만 근거로 답하세요. 조회 결과가 비면 그대로 알려주세요.
- meeting_id를 모르면 list_my_meetings로 먼저 확인하세요.
- 답변에는 어떤 회의체 데이터를 근거로 했는지 표시하세요 (예: "[skala 5기] 기준").
- 접근 거부 응답을 받으면 다른 회의체를 시도하지 말고 권한이 없음을 안내하세요.
"""

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        from langgraph.prebuilt import create_react_agent
        from llm_factory import llm_factory
        from tools.meeting_tools import SUPERVISOR_TOOLS
        _agent = create_react_agent(
            model=llm_factory("chat", temperature=0.2),
            tools=SUPERVISOR_TOOLS,
            prompt=_SYSTEM,
        )
    return _agent


def react_mode_enabled() -> bool:
    """도구 기반 에이전트가 기본. legacy로 설정 시 사전조립 경로로 롤백 (제거 예정)."""
    return os.environ.get("SUPERVISOR_TOOLS_MODE", "react").lower() != "legacy"


async def direct_agent_stream(
    message: str,
    history_msgs: list,
    *,
    user_id: int,
    allowed_meeting_ids: list[int],
    is_admin: bool,
    meeting_id: int | None = None,
) -> AsyncGenerator[tuple[str, str], None]:
    """(kind, text) 튜플 스트림 — kind: 'planning'(도구 호출 진행표시) | 'token'.

    진행표시는 별도 narration LLM 없이 astream_events의 실제 도구 이벤트에서 파생한다(H-13).
    """
    hint = f"(현재 보고 있는 회의체 meeting_id={meeting_id})\n" if meeting_id else ""
    config = {"configurable": {
        "thread_id": f"run-{uuid.uuid4()}",
        "user_id": user_id,
        "allowed_meeting_ids": list(allowed_meeting_ids),
        "is_admin": is_admin,
    }}
    inputs = {"messages": list(history_msgs) + [HumanMessage(content=hint + message)]}
    async for event in _get_agent().astream_events(inputs, config, version="v2"):
        kind = event["event"]
        if kind == "on_tool_start":
            yield ("planning", f"{event.get('name', '도구')} 조회")
        elif kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield ("token", chunk.content)

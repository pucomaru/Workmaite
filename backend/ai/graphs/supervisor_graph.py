"""도구 기반 supervisor 직접응답 에이전트 (P3A-5 2단계 / P3B-2).

기존 supervisor_direct 경로는 Neo4j/DB 컨텍스트를 ~300줄에 걸쳐 사전 조립해
프롬프트에 전부 주입했다(H-6). 이 그래프는 컨텍스트를 **도구로 just-in-time 조회**한다:
- 시스템 프롬프트는 정적(캐시 적중), 데이터는 모델이 필요할 때 도구 호출
- 스코프는 tools/meeting_tools.py가 RunnableConfig 기준으로 강제 (P3B-1)
- 단순 요청은 single-loop(도구 1-2회)로 끝난다 — 다단 그래프 강요 없음

유일한 직접응답 경로 (P3B-2 — 사전조립 경로 제거 완료)
"""
import logging
import uuid
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# 긴 스레드 컴팩션 임계값 (H-4) — 이보다 길면 오래된 턴을 요약으로 압축
_COMPACT_AFTER = 30
_KEEP_RECENT = 10


async def _compact_history(history_msgs: list) -> list:
    """30턴 초과 시 오래된 메시지를 1개의 요약 메시지로 압축한다 (H-4).

    최근 _KEEP_RECENT개는 원본 유지, 그 앞은 LLM 요약으로 대체해 토큰·지연을 억제한다.
    요약 실패 시 원본을 그대로 반환(가용성 우선).
    """
    if len(history_msgs) <= _COMPACT_AFTER:
        return history_msgs
    old_msgs, recent = history_msgs[:-_KEEP_RECENT], history_msgs[-_KEEP_RECENT:]
    convo = "\n".join(
        f"{'사용자' if isinstance(m, HumanMessage) else 'AI'}: {str(m.content)[:200]}"
        for m in old_msgs
    )
    try:
        from llm_factory import llm_factory
        resp = await llm_factory("routing").ainvoke([
            SystemMessage(content="다음 대화를 3~5문장 한국어로 요약하세요. 결정사항·맥락 위주."),
            HumanMessage(content=convo[:6000]),
        ])
        summary = resp.content
    except Exception as e:
        logger.warning(f"[Compaction] 요약 실패, 원본 유지: {e}")
        return history_msgs
    return [AIMessage(content=f"[이전 대화 요약]\n{summary}")] + recent

_SYSTEM = """\
당신은 회의체 운영 AI 워크메이트입니다. 사용자의 회의체 현황·아젠다·보고서·회의록 질문에
도구로 데이터를 조회해 한국어로 간결하게 답합니다.

규칙:
- 추측하지 말고 도구로 확인한 데이터만 근거로 답하세요. 조회 결과가 비면 그대로 알려주세요.
- meeting_id를 모르면 list_my_meetings로 먼저 확인하세요.
- 답변 끝에 근거를 반드시 인용하세요: 어떤 회의체·아젠다·보고서·회의록을 조회했는지
  (예: "근거: [skala 5기] 아젠다 3건, 보고서 제출현황"). 도구를 호출하지 않았으면 인용하지 마세요.
- 접근 거부 응답을 받으면 다른 회의체를 시도하지 말고 권한이 없음을 안내하세요.
- 데이터를 만들어내지 마세요(쓰기 도구 없음 — 생성/수정 요청은 해당 화면에서 처리하도록 안내).
- 도구 결과로 확인되지 않은 수치·사실을 단정하지 마세요. 모르면 "확인되지 않았습니다"라고 답하세요.
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
    compacted = await _compact_history(list(history_msgs))
    inputs = {"messages": compacted + [HumanMessage(content=hint + message)]}
    async for event in _get_agent().astream_events(inputs, config, version="v2"):
        kind = event["event"]
        if kind == "on_tool_start":
            yield ("planning", f"{event.get('name', '도구')} 조회")
        elif kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield ("token", chunk.content)

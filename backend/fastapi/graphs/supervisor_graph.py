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
        from llm.llm_factory import llm_factory

        resp = await llm_factory("routing").ainvoke(
            [
                SystemMessage(
                    content="다음 대화를 3~5문장 한국어로 요약하세요. 결정사항·맥락 위주."
                ),
                HumanMessage(content=convo[:6000]),
            ]
        )
        summary = resp.content
    except Exception as e:
        logger.warning(f"[Compaction] 요약 실패, 원본 유지: {e}")
        return history_msgs
    return [AIMessage(content=f"[이전 대화 요약]\n{summary}")] + recent


_SYSTEM = """\
당신은 회의체 운영 AI 워크메이트입니다. 사용자의 회의체 현황·아젠다·보고서·회의록 질문에
도구로 데이터를 조회해 한국어로 답합니다.

[답변 스타일 — 두괄식·간결]
- 첫 문장에 결론/핵심을 먼저 말합니다. 부연·맥락은 그 뒤에 짧게만 덧붙입니다.
- 묻지 않은 정보·인사말·반복·군더더기는 넣지 않습니다. 질문에 답하는 데 필요한 만큼만 씁니다.
- 여러 항목은 핵심만 추려 bullet로, 한 항목은 한 줄로 정리합니다.
- 한두 문장으로 충분한 질문은 그대로 짧게 답합니다(표·장황한 형식 강요 금지).

규칙:
- 추측하지 말고 도구로 확인한 데이터만 근거로 답하세요. 조회 결과가 비면 그대로 알려주세요.
- meeting_id를 모르면 list_my_meetings로 먼저 확인하세요.
- 질문이 모호하거나(예: 어느 회의체인지 불명확) 답하는 데 필요한 정보가 부족하면, 억지로 추측하지 말고
  필요한 한 가지를 사용자에게 짧게 되물어 확인한 뒤 답하세요(예: "어느 회의체를 말씀하시는 걸까요?").
- 답변 끝에 근거를 반드시 밝히세요. 단, 사용자는 비개발자입니다 — 쿼리·DB·인덱스 같은 기술 표현은
  절대 쓰지 말고, "○○ 회의체의 △△ 아젠다에서 확인했습니다"처럼 출처(회의체명·아젠다명·문서명·회의 회차)를
  자연어로 알려주세요. 도구를 호출하지 않았으면 근거를 지어내지 마세요.
- 접근 거부 응답을 받으면 다른 회의체를 시도하지 말고 권한이 없음을 안내하세요.
- 데이터를 만들어내지 마세요(쓰기 도구 없음 — 생성/수정 요청은 해당 화면에서 처리하도록 안내).
- 도구 결과로 확인되지 않은 수치·사실을 단정하지 마세요. 모르면 "확인되지 않았습니다"라고 답하세요.

[데이터 변경(쓰기) — 신중·안전]
- 사용자가 생성/삭제/수정 등 데이터 변경을 요청하면 propose_data_change 도구로 '제안'만 하세요(직접 실행 불가).
  가능 범위: agenda(생성·수정·삭제), minutes(수정·삭제), report(수정·삭제), meeting(삭제). 그 외는 불가.
  status 변경(예: 아젠다 완료)은 operation="update", fields={"status":...}로, 아젠다 생성은
  operation="create", fields={"meeting_id":회의체ID, "title":제목}로 표현합니다.
- 반드시 먼저 read 도구로 정확한 대상 id를 확인한 뒤 제안하세요. 엉뚱한 대상을 변경하지 않도록.
- 제안이 만들어지면 사용자에게 무엇을 할지 한 문장으로 알리고 확인을 요청하세요(실행은 사용자가 확인 버튼을 눌러야 일어납니다).
- 도구가 "[작업 불가] …"를 반환하면(권한 없음·대상 없음 등) 그 사유를 사용자에게 그대로, 친절히 설명하세요. 왜 안 되는지 사용자가 이해하도록.
"""

# 모델별 컴파일된 에이전트 캐시. 단일 싱글톤으로 캐시하면 첫 빌드 모델로 고정되어
# 사용자의 model-select-btn 선택(model_override_var)이 무시됐다(버그). 도구·프롬프트는
# 정적이고 모델만 요청마다 달라지므로, 해석된 모델명을 키로 에이전트를 캐시한다.
_agents: dict[str, object] = {}


def _resolve_chat_model() -> str:
    """현재 요청의 chat 모델명. 사용자 선택(model_override_var) > OPENAI_MODEL_CHAT > OPENAI_MODEL."""
    import os
    from llm.llm_factory import model_override_var

    return (
        model_override_var.get()
        or os.environ.get("OPENAI_MODEL_CHAT")
        or os.environ.get("OPENAI_MODEL", "gpt-4o")
    )


def _get_agent():
    # llm_factory("chat")도 동일하게 model_override_var를 먼저 읽으므로 키와 실제 모델이 일치한다.
    model = _resolve_chat_model()
    agent = _agents.get(model)
    if agent is None:
        from langgraph.prebuilt import create_react_agent
        from llm.llm_factory import llm_factory
        from tools.meeting_tools import SUPERVISOR_TOOLS
        from tools.action_tools import ACTION_TOOLS

        agent = create_react_agent(
            model=llm_factory("chat", temperature=0.2),
            tools=SUPERVISOR_TOOLS + ACTION_TOOLS,
            prompt=_SYSTEM,
        )
        _agents[model] = agent
    return agent


def _build_agent_hint(
    meeting_id: int | None, thread_id: str | None
) -> str:
    """신호 활용: meeting_id가 있으면 그 회의체의 지침·설명·맥락을, 같은 스레드에 최근 부정
    피드백(rating=-1)이 있으면 '피해야 할 점'을 주입해 답변 품질을 끌어올린다."""
    parts: list[str] = []
    if meeting_id:
        parts.append(f"(현재 보고 있는 회의체 meeting_id={meeting_id})")
    try:
        from db.database import SessionLocal
        from db import models as _m

        db = SessionLocal()
        try:
            if meeting_id:
                mg = db.query(_m.Meeting).filter(_m.Meeting.id == meeting_id).first()
                if mg:
                    brief = []
                    if mg.description:
                        brief.append(f"설명: {mg.description}")
                    if mg.guidelines:
                        brief.append(f"운영 지침: {mg.guidelines}")
                    if mg.context:
                        brief.append(f"배경: {mg.context}")
                    if brief:
                        parts.append(
                            "[이 회의체 지침·맥락 — 답변에 반영하세요]\n" + "\n".join(brief)
                        )
            if thread_id:
                rows = (
                    db.query(_m.ChatFeedback.reason)
                    .filter(
                        _m.ChatFeedback.thread_id == thread_id,
                        _m.ChatFeedback.rating == -1,
                        _m.ChatFeedback.reason.isnot(None),
                    )
                    .order_by(_m.ChatFeedback.created_at.desc())
                    .limit(3)
                    .all()
                )
                reasons = [r.reason for r in rows if r.reason]
                if reasons:
                    parts.append(
                        "[이전 답변에서 아쉬웠던 점 — 이번엔 피하세요]\n- "
                        + "\n- ".join(reasons)
                    )
        finally:
            db.close()
    except Exception:
        pass
    return ("\n".join(parts) + "\n") if parts else ""


async def direct_agent_stream(
    message: str,
    history_msgs: list,
    *,
    user_id: int,
    allowed_meeting_ids: list[int],
    is_admin: bool,
    meeting_id: int | None = None,
    upcoming_ctx: str = "",
    thread_id: str | None = None,
) -> AsyncGenerator[tuple[str, str], None]:
    """(kind, text) 튜플 스트림 — kind: 'planning'(도구 호출 진행표시) | 'token' | 'action'.

    진행표시는 별도 narration LLM 없이 astream_events의 실제 도구 이벤트에서 파생한다(H-13).
    """
    hint = _build_agent_hint(meeting_id, thread_id)
    if upcoming_ctx:
        hint += upcoming_ctx + "\n"
    config = {
        "configurable": {
            "thread_id": thread_id or f"run-{uuid.uuid4()}",
            "user_id": user_id,
            "allowed_meeting_ids": list(allowed_meeting_ids),
            "is_admin": is_admin,
        }
    }
    compacted = await _compact_history(list(history_msgs))
    inputs = {"messages": compacted + [HumanMessage(content=hint + message)]}
    from tools.action_tools import ACTION_CONFIRM_SENTINEL

    async for event in _get_agent().astream_events(inputs, config, version="v2"):
        kind = event["event"]
        if kind == "on_tool_start":
            yield ("planning", f"{event.get('name', '도구')} 조회")
        elif kind == "on_tool_end":
            # 쓰기 제안 도구가 확인 표식을 반환하면 → 프런트 확인 카드용 action 이벤트로 변환
            _out = event.get("data", {}).get("output")
            _txt = getattr(_out, "content", None)
            if _txt is None and isinstance(_out, str):
                _txt = _out
            if _txt and ACTION_CONFIRM_SENTINEL in str(_txt):
                _spec = str(_txt).split(ACTION_CONFIRM_SENTINEL, 1)[1].split("\n", 1)[0]
                yield ("action", _spec)
        elif kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if chunk.content:
                yield ("token", chunk.content)

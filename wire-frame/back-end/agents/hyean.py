"""혜안 (Hyean) - Supervisor Agent + 암묵지 관리"""
import os, json, re
from typing import AsyncGenerator, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _make_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL,
        temperature=temperature,
        api_key=os.getenv("OPENAI_API_KEY"),
    )


def _to_lc_messages(messages: List[dict]):
    result = []
    for m in messages:
        role, content = m["role"], m["content"]
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(HumanMessage(content=content))
        else:
            result.append(AIMessage(content=content))
    return result


def _status_system_prompt() -> str:
    return """당신은 회의체 운영 현황을 파악하고 안내하는 AI 혜안(Hyean)입니다.
현재 회의체의 상태를 분석하여:
1. 현황을 자연어로 간결하게 설명합니다
2. 다음에 해야 할 액션을 추천합니다
3. 주의가 필요한 사항을 알립니다
한국어로, 친근하지만 전문적으로 응답합니다."""


async def status_stream(
    meeting_status: dict,
    user_role: str,
    active_knowledge: List[dict] = None,
    chat_history: List[dict] = None,
    message: str = "현재 회의체 현황을 알려주세요.",
) -> AsyncGenerator[str, None]:
    status_text = json.dumps(meeting_status, ensure_ascii=False, indent=2)

    messages = [{"role": "system", "content": _status_system_prompt()}]
    messages.append({
        "role": "user",
        "content": f"[회의체 현황]\n{status_text}\n\n[사용자 역할] {user_role}"
    })
    messages.append({
        "role": "assistant",
        "content": "현황을 확인했습니다. 무엇이 궁금하신가요?"
    })

    if chat_history:
        for h in (chat_history or [])[-8:]:
            messages.append(h)

    messages.append({"role": "user", "content": message})

    llm = _make_llm(temperature=0.3)
    async for chunk in llm.astream(_to_lc_messages(messages)):
        if chunk.content:
            yield chunk.content


async def analyze_and_propose(
    recent_events: List[dict],
    current_knowledge: List[dict],
    scope: str = "global",
    meeting_id: int = None,
) -> dict | None:
    if len(recent_events) < 3:
        return None

    events_text = json.dumps(recent_events[-10:], ensure_ascii=False, indent=2)
    knowledge_text = json.dumps(current_knowledge[:5], ensure_ascii=False, indent=2)

    prompt = f"""최근 회의체 이벤트 패턴을 분석하여 암묵지 업데이트를 제안해주세요.

반드시 JSON 형식으로만 응답하세요. 제안이 없으면 null을 반환하세요.
형식:
{{
  "category": "report_standard",
  "title": "기준 제목",
  "proposed_content": "새 기준 내용 (마크다운)",
  "diff_summary": "변경 요약",
  "evidence_summary": "이벤트 패턴에서 도출된 근거"
}}

[최근 이벤트]
{events_text}

[현재 기준]
{knowledge_text}"""

    llm = _make_llm(temperature=0.2)
    response = await llm.ainvoke(_to_lc_messages([
        {"role": "system", "content": "당신은 조직의 암묵지를 분석하고 기준을 업데이트하는 전문가입니다."},
        {"role": "user", "content": prompt},
    ]))
    text = response.content.strip()
    if text.lower() == "null":
        return None
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None

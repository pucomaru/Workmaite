"""가온 (Gaon) - Agenda/Todo 추출 Agent"""
import os
from typing import AsyncGenerator, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _make_llm(temperature: float = 0.1) -> ChatOpenAI:
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


def _build_system_prompt(knowledge: List[dict] = None) -> str:
    base = """당신은 회의체 아젠다 및 To-do 추출 전문 AI 가온(Gaon)입니다.
사용자가 업로드한 보고자료와 이전 회의록을 분석하여:
1. 회의 아젠다 항목을 추출합니다 (담당 부서, 내용)
2. To-do 과제를 도출합니다 (내용, 마감일, 담당 부서)

응답 형식:
- 아젠다 추출 시: JSON 형식으로 [{\"department\": \"부서명\", \"content\": \"아젠다 내용\"}] 포함
- 친절하고 명확하게 안내합니다
- 한국어로 응답합니다"""

    if knowledge:
        criteria = "\n".join([f"- [{k.get('category','')}] {k.get('title','')}" for k in knowledge])
        base += f"\n\n[조직 아젠다 선정 기준]\n{criteria}"
    return base


async def chat_stream(
    message: str,
    chat_history: List[dict],
    file_content: str = "",
    previous_minutes: List[str] = None,
    knowledge: List[dict] = None,
) -> AsyncGenerator[str, None]:
    messages = [{"role": "system", "content": _build_system_prompt(knowledge)}]

    if file_content:
        messages.append({
            "role": "user",
            "content": f"[업로드된 문서 내용]\n{file_content[:4000]}"
        })
        messages.append({
            "role": "assistant",
            "content": "문서를 확인했습니다. 분석을 시작하겠습니다."
        })

    if previous_minutes:
        minutes_text = "\n\n".join(previous_minutes[:3])
        messages.append({
            "role": "user",
            "content": f"[이전 회의록]\n{minutes_text[:2000]}"
        })
        messages.append({
            "role": "assistant",
            "content": "이전 회의록도 검토했습니다."
        })

    for h in chat_history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})

    llm = _make_llm(temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.1")))
    async for chunk in llm.astream(_to_lc_messages(messages)):
        if chunk.content:
            yield chunk.content


async def extract_agendas(
    file_content: str,
    previous_minutes: List[str] = None,
    knowledge: List[dict] = None,
) -> List[dict]:
    prompt = f"""다음 문서에서 회의 아젠다를 추출해주세요.
반드시 JSON 배열 형식으로만 응답하세요: [{{"department": "부서명", "content": "아젠다 내용"}}]

[문서 내용]
{file_content[:3000]}"""

    llm = _make_llm(temperature=0.1)
    import json, re
    response = await llm.ainvoke(_to_lc_messages([
        {"role": "system", "content": _build_system_prompt(knowledge)},
        {"role": "user", "content": prompt},
    ]))
    text = response.content
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return []

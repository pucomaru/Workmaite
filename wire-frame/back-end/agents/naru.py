"""나루 (Naru) - 보고서 검토 Agent"""
import os, json, re
from typing import AsyncGenerator, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _make_llm(temperature: float = 0.2) -> ChatOpenAI:
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

SYSTEM_PROMPT = """당신은 보고서 검토 전문 AI 나루(Naru)입니다.
전체 보고서를 총괄 분석하여:
1. 공통 품질 이슈를 파악합니다
2. 누락된 내용을 지적합니다
3. 개선 방향을 제시합니다
4. 각 발제자별 피드백을 제공합니다
한국어로, 구체적이고 건설적으로 응답합니다."""


async def global_review_stream(
    reports_info: List[dict],
    chat_history: List[dict],
    knowledge: List[dict] = None,
) -> AsyncGenerator[str, None]:
    system = SYSTEM_PROMPT
    if knowledge:
        criteria = "\n".join([f"- {k.get('title','')}: {k.get('content','')[:100]}" for k in knowledge])
        system += f"\n\n[보고서 검토 기준]\n{criteria}"

    reports_text = "\n\n".join([
        f"[{r.get('presenter_name','')} - {r.get('file_name','')}]\n상태: {r.get('status','')}"
        for r in reports_info
    ])

    messages = [{"role": "system", "content": system}]
    messages.append({"role": "user", "content": f"다음 보고서 목록을 검토해주세요:\n{reports_text}"})
    for h in chat_history[-8:]:
        messages.append(h)

    llm = _make_llm(temperature=0.2)
    async for chunk in llm.astream(_to_lc_messages(messages)):
        if chunk.content:
            yield chunk.content


async def review_report(
    report_content: str,
    agenda: str = "",
    knowledge: List[dict] = None,
) -> dict:
    system = SYSTEM_PROMPT
    if knowledge:
        criteria = "\n".join([f"- {k.get('title','')}" for k in knowledge])
        system += f"\n\n[검토 기준]\n{criteria}"

    prompt = f"""다음 보고서를 검토하고 반드시 JSON 형식으로 응답하세요.
형식: {{"score": 75, "feedback": ["피드백1", "피드백2", "피드백3"]}}

[아젠다]
{agenda}

[보고서 내용]
{report_content[:3000]}"""

    llm = _make_llm(temperature=0.1)
    response = await llm.ainvoke(_to_lc_messages([
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]))
    text = response.content
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return {"score": 70, "feedback": ["보고서를 검토했습니다. 구체적인 피드백을 위해 내용을 더 자세히 작성해 주세요."]}


async def chat_stream(
    message: str,
    chat_history: List[dict],
    knowledge: List[dict] = None,
) -> AsyncGenerator[str, None]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in chat_history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})

    llm = _make_llm(temperature=0.2)
    async for chunk in llm.astream(_to_lc_messages(messages)):
        if chunk.content:
            yield chunk.content

"""아라 (Ara) - 회의 진행 Agent + 회의록 생성"""
import os
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

SYSTEM_PROMPT = """당신은 회의 진행을 돕는 AI 아라(Ara)입니다.
- 지난 회의 내용을 요약 제공합니다
- 현재 아젠다 진행 상황을 안내합니다
- 회의 중 궁금한 사항에 답변합니다
- 간결하고 실용적으로 응답합니다
한국어로 응답합니다."""


async def chat_stream(
    message: str,
    chat_history: List[dict],
    previous_minutes: List[str] = None,
    current_agendas: List[dict] = None,
) -> AsyncGenerator[str, None]:
    system = SYSTEM_PROMPT
    context_parts = []
    if previous_minutes:
        context_parts.append(f"[이전 회의 요약]\n" + "\n".join(previous_minutes[:2]))
    if current_agendas:
        agenda_text = "\n".join([f"- {a.get('content','')}" for a in current_agendas])
        context_parts.append(f"[현재 아젠다]\n{agenda_text}")

    messages = [{"role": "system", "content": system}]
    if context_parts:
        messages.append({
            "role": "user",
            "content": "\n\n".join(context_parts)
        })
        messages.append({
            "role": "assistant",
            "content": "회의 정보를 확인했습니다. 도움이 필요하신 게 있나요?"
        })

    for h in chat_history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})

    llm = _make_llm(temperature=0.3)
    async for chunk in llm.astream(_to_lc_messages(messages)):
        if chunk.content:
            yield chunk.content


async def generate_minutes(raw_transcript: str) -> str:
    if not raw_transcript or len(raw_transcript.strip()) < 10:
        return "회의 내용이 기록되지 않았습니다."

    prompt = f"""다음 회의 녹취록을 바탕으로 회의록을 작성해주세요.

형식:
## 회의 요약
(3-5줄 요약)

## 주요 논의 사항
- 항목별 정리

## 결정 사항
- 결정된 내용

## 후속 과제
- 과제 및 담당자

[녹취록]
{raw_transcript[:4000]}"""

    llm = _make_llm(temperature=0.2)
    response = await llm.ainvoke(_to_lc_messages([
        {"role": "system", "content": "당신은 전문 회의록 작성 AI입니다. 한국어로 작성합니다."},
        {"role": "user", "content": prompt},
    ]))
    return response.content

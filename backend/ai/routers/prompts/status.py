import os
from typing import List

from langchain_openai import ChatOpenAI

from llm_factory import llm_factory

STATUS_STREAM_SYSTEM = (
    "당신은 회의체 운영을 지원하는 AI ReportAgent입니다.\n"
    "공손하고 정중한 비서 말투로 응답합니다. ('~드립니다', '~습니다')\n"
    "데이터에 없는 내용은 절대 언급하지 않습니다.\n"
    "추측성 표현 금지: '~일 것 같습니다', '~인 것 같아요' 사용 불가\n"
    "한국어로 응답합니다."
)


def status_stream_context(user_label: str, role_label: str, context_block: str) -> str:
    return (
        f"[사용자 정보]\n- 이름: {user_label}\n- 역할: {role_label}\n\n"
        f"{context_block}\n\n"
        f"위 데이터만을 기반으로, {user_label}의 질문에 자연스럽게 응대하세요."
    )

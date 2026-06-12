import os
from typing import List

from langchain_openai import ChatOpenAI

from llm_factory import llm_factory

KNOWLEDGE_SYSTEM = """\
당신은 조직 지식 관리 전문 AI KnowledgeAgent입니다.
- 승인된 회의록·과제·보고서를 Neo4j Knowledge Base에 정제·저장합니다
- 조직의 패턴과 암묵지를 분석해 인사이트를 제공합니다
- 지식 그래프에서 연관 정보를 검색하고 요약합니다
한국어로 응답합니다."""

RELATIONSHIP_SUMMARY_SYSTEM = (
    "당신은 조직의 지식 그래프를 책임지는 KnowledgeAgent입니다. "
    "Supervisor가 '분석'해 넘긴 결과를, 당신이 직접 그래프에 '재구성'한 결과를 사용자에게 보고합니다.\n"
    "[작성 원칙]\n"
    "1. 기술 용어(Cypher, 노드, 임베딩 차원 등) 금지 — '회의 흐름', '의미 유사도', '회의 간 연결' 같은 업무 언어 사용\n"
    "2. 보고 우선순위: ① 가장 기본인 '회의 흐름'(같은 회의체 1차→2차→3차 세션 연결), "
    "② '회의 생명주기'(회의록이 안건과 이어졌는지 — 회의→회의록→안건→다음 회의)를 다루고, "
    "그다음 ③ 회의 경계를 넘는 의미 기반 연결을 설명하세요\n"
    "3. 핵심은 '흩어져 있던 회의 지식을 어떻게 이어 붙였는지'입니다. 단순 정합성 점검처럼 보고하지 말 것\n"
    "4. 다음 순서로 간결하게:\n"
    "   📊 분석 요약 (무엇을 훑었고 무엇을 발견했는지)\n"
    "   🧵 회의 흐름 복원 (세션 시간순 연결)\n"
    "   🔄 회의 생명주기 복원 (회의록이 안건과 이어졌는지 확인·연결)\n"    "   ✂️ 연결 정제 (완료된 안건 이월·낙은 유사도 지운 것 특등)\n"    "   🔗 회의 간 새 지식 연결 (실제 사례와 유사도를 근거로)\n"
    "   ⚠️ 사용자 확인이 필요한 공백 (자동으로 메울 수 없는 부분)\n"
    "   ✅ 결과 한 줄 요약\n"
    "5. 발견·연결이 하나도 없으면 '이미 충분히 연결돼 있다'고 안내\n"
    "6. 정중하고 명확한 비서 말투"
)


def relationship_summary_human(
    counts: dict, findings: dict, stats: dict, act_block: str, adv_block: str
) -> str:
    return (
        f"[Supervisor 분석 범위]\n"
        f"- 회의 {counts.get('meetings',0)}개 · 세션 {counts.get('sessions',0)}개 · "
        f"안건 {counts.get('agendas',0)}개 · 문서 {counts.get('documents',0)}개 · 구성원 {counts.get('persons',0)}명\n\n"
        f"[Supervisor 발굴 결과]\n"
        f"- 끊긴 회의 흐름(세션 미연결): {findings.get('session_missing',0)}건 "
        f"(회의체 {findings.get('session_groups',0)}곳)\n"
        f"- 회의록→안건 미연결: {findings.get('lifecycle_gaps',0)}건\n"
        f"- 불필요 연결(정제 대상): {findings.get('stale_links',0)}건\n"
        f"- 회의 간 잠재 연관 안건: {findings.get('agenda_links',0)}쌍\n"
        f"- 미연결 문서-안건 적합쌍: {findings.get('doc_links',0)}건\n"
        f"- 담당자 없는 안건: {findings.get('ownerless',0)}건 / 고아 문서: {findings.get('orphans',0)}건\n\n"
        f"[KnowledgeAgent 재구성 통계]\n"
        f"- 회의 흐름(세션) '후속' 연결: {stats.get('session_links',0)}건\n"
        f"- 세션→안건 직접 연결: {stats.get('session_agenda_links',0)}건\n"
        f"- 회의록→안건 연결(생명주기): {stats.get('lifecycle_links',0)}건\n"
        f"- 미해결 안건 다음 회차 이월: {stats.get('carry_links',0)}건\n"
        f"- 회의 간 '관련' 링크 생성: {stats.get('related_agendas',0)}건\n"
        f"- 문서 '참조' 링크 생성: {stats.get('doc_refs',0)}건\n"
        f"- 고아 문서 자동 편입: {stats.get('doc_attached',0)}건\n"
        f"- 소속 무결성 보정: {stats.get('membership_fixed',0)}건\n"
        f"- 불필요 연결 정제: {stats.get('pruned_links',0)}건\n\n"
        f"[재구성 상세 내역 및 근거]\n{act_block}\n\n"
        f"[사용자 확인 필요 — 자동 보완 불가]\n{adv_block}\n\n"
        "위 결과를 사용자에게 보고해 주세요."
    )


# ─── minutes_agent ────────────────────────────────────────────────────────────

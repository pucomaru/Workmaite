KNOWLEDGE_SYSTEM = """\
당신은 조직 지식 관리 전문 AI KnowledgeAgent입니다.
- 승인된 회의록·과제·보고서를 Neo4j Knowledge Base에 정제·저장합니다
- 조직의 패턴과 암묵지를 분석해 인사이트를 제공합니다
- 지식 그래프에서 연관 정보를 검색하고 요약합니다
한국어로 응답합니다."""

RELATIONSHIP_SUMMARY_SYSTEM = (
    "당신은 조직의 지식 그래프를 책임지는 AI Agent입니다. "
    "Supervisor가 '분석'해 넘긴 결과를, 당신이 직접 그래프에 '재구성'한 결과를 사용자에게 보고합니다.\n"
    "[작성 원칙]\n"
    "1. 기술 용어(Cypher, 노드, 임베딩 차원 등) 금지 — '회의 흐름', '의미 유사도', '회의 간 연결' 같은 업무 언어 사용\n"
    "2. 보고 우선순위: ① 가장 기본인 '회의 흐름'(같은 회의체 1차→2차→3차 세션 연결), "
    "② '회의 생명주기'(회의록이 안건과 이어졌는지 — 회의→회의록→안건→다음 회의)를 다루고, "
    "그다음 ③ 회의 경계를 넘는 의미 기반 연결을 설명하세요\n"
    "3. 핵심은 '흩어져 있던 회의 지식을 어떻게 이어 붙였는지'입니다. 단순 정합성 점검처럼 보고하지 말 것\n"
    "4. 분석 결과 요약 (무엇을 훑었고 무엇을 발견했는지)\n"
    "5. 발견·연결이 하나도 없으면 '이미 충분히 연결돼 있다'고 안내\n"
    "6. 정중하고 명확한 비서 말투"
    "7. 보고 끝에 '근거'를 반드시 알려주세요: 어떤 회의체·아젠다·보고서·회의록을 조회하였기에 결과가 그렇게 도출되었는지. 도구를 호출하지 않았으면 인용하지 마세요."
    "8. 본인 소개 및 감사합니다 등 마무리 인사 하지 말것."
)


def relationship_summary_human(
    counts: dict, findings: dict, stats: dict, act_block: str, adv_block: str
) -> str:
    return (
        f"[Supervisor 분석 범위]\n"
        f"- 회의 {counts.get('meetings', 0)}개 · 세션 {counts.get('sessions', 0)}개 · "
        f"안건 {counts.get('agendas', 0)}개 · 문서 {counts.get('documents', 0)}개 · 구성원 {counts.get('persons', 0)}명\n\n"
        f"[Supervisor 발굴 결과]\n"
        f"- 끊긴 회의 흐름(세션 미연결): {findings.get('session_missing', 0)}건 "
        f"(회의체 {findings.get('session_groups', 0)}곳)\n"
        f"- 회의록→안건 미연결: {findings.get('lifecycle_gaps', 0)}건\n"
        f"- 불필요 연결(정제 대상): {findings.get('stale_links', 0)}건\n"
        f"- 회의 간 잠재 연관 안건: {findings.get('agenda_links', 0)}쌍\n"
        f"- 미연결 문서-안건 적합쌍: {findings.get('doc_links', 0)}건\n"
        f"- 담당자 없는 안건: {findings.get('ownerless', 0)}건 / 고아 문서: {findings.get('orphans', 0)}건\n\n"
        f"[KnowledgeAgent 재구성 통계]\n"
        f"- 회의 흐름(세션) '후속' 연결: {stats.get('session_links', 0)}건\n"
        f"- 세션→안건 직접 연결: {stats.get('session_agenda_links', 0)}건\n"
        f"- 회의록→안건 연결(생명주기): {stats.get('lifecycle_links', 0)}건\n"
        f"- 미해결 안건 다음 회차 이월: {stats.get('carry_links', 0)}건\n"
        f"- 회의 간 '관련' 링크 생성: {stats.get('related_agendas', 0)}건\n"
        f"- 문서 '참조' 링크 생성: {stats.get('doc_refs', 0)}건\n"
        f"- 고아 문서 자동 편입: {stats.get('doc_attached', 0)}건\n"
        f"- 소속 무결성 보정: {stats.get('membership_fixed', 0)}건\n"
        f"- 불필요 연결 정제: {stats.get('pruned_links', 0)}건\n\n"
        f"[재구성 상세 내역 및 근거]\n{act_block}\n\n"
        f"[사용자 확인 필요 — 자동 보완 불가]\n{adv_block}\n\n"
        "위 결과를 사용자에게 보고해 주세요."
    )


# ─── '채우기'(필드 자동 보정) ───────────────────────────────────────────────────
FIELD_FILL_SYSTEM = (
    "당신은 회의 안건(Agenda)의 메타데이터를 점검·보완하는 AI입니다. "
    "비어있는 필드를 맥락에 맞게 적극적으로 채우고, 우선순위와 완료 상태를 현실에 맞게 보정합니다.\n"
    "[규칙]\n"
    "1. department(담당 부서): 안건 제목·근거로 가장 적합한 부서명을 추론해 채웁니다. 확신이 없으면 null.\n"
    "2. due_date(마감일): 비어있으면 회의 맥락·우선순위·오늘 날짜를 고려해 현실적인 마감일을 YYYY-MM-DD로 제안합니다 "
    "(예: 긴급=1주 내, 보통=2~4주 내). 합리적 근거가 전혀 없으면 null.\n"
    "3. priority: 마감 임박·중요도를 보고 low/medium/high로 재평가합니다. 근거가 약하면 null(기존 유지).\n"
    "4. status: 맥락상 이미 완료로 보이면 'done', 진행 중이면 'ongoing'. 명확하지 않으면 null(변경 안 함).\n"
    "   ★ 임의로 미완료를 완료(done)로 바꾸지 마세요. 근거(완료 신호·결론·결정)가 분명할 때만 done.\n"
    "5. 각 변경에는 한국어 reason 한 문장. 바꿀 게 없는 안건은 결과(items)에서 생략합니다.\n"
    "6. 마감일은 반드시 오늘 이후로만, 과거나 비현실적으로 먼 미래는 피하세요."
)


def field_fill_human(agendas: list[dict], today: str | None = None) -> str:
    lines = []
    if today:
        lines.append(f"오늘 날짜: {today}")
    lines.append(
        "다음 안건들의 비어있는 필드(특히 비어있는 마감일·부서)를 채우고 우선순위·상태를 보정하세요. "
        "변경이 필요한 안건만 items에 포함하세요.\n"
    )
    for a in agendas:
        lines.append(
            f"- id={a['id']} | 제목: {a.get('title', '')} | 현재상태: {a.get('status') or '?'} "
            f"| 우선순위: {a.get('priority') or '?'} | 부서: {a.get('department') or '없음'} "
            f"| 마감: {a.get('due_date') or '없음'}"
            + (f" | 근거: {str(a['evidence'])[:200]}" if a.get("evidence") else "")
            + (f" | 회의체: {a['meeting']}" if a.get("meeting") else "")
        )
    return "\n".join(lines)


# ─── minutes_agent ────────────────────────────────────────────────────────────

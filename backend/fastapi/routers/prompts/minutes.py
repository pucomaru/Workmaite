MINUTES_SYSTEM = """\
당신은 회의록 작성 전문 AI MinutesAgent입니다.
- STT 변환 텍스트를 분석해 구조적 회의록을 생성합니다
- 이전 유사 회의록을 참고해 일관성 있는 형식을 유지합니다
- 결정 사항, 액션 아이템, 참석자 정보를 명확히 기록합니다
한국어로 응답합니다."""


def generate_minutes_system(
    meeting_context: str,
    agenda_text: str,
    session_info: dict = None,
    participants: list = None,
    prev_minutes: list = None,
    report_chunks: list = None,
    overdue_agendas: list = None,
) -> str:
    parts = [
        "당신은 전문 회의록 작성 AI입니다.\n"
        "STT 대화 기록과 제공된 모든 맥락을 종합해 실무에서 바로 활용 가능한 고품질 회의록을 작성합니다."
    ]

    # 회의 기본 정보
    info_lines = [meeting_context] if meeting_context else []
    if session_info:
        if session_info.get("started_at"):
            info_lines.append(f"시작: {session_info['started_at']}")
        if session_info.get("ended_at"):
            info_lines.append(f"종료: {session_info['ended_at']}")
        if session_info.get("location"):
            info_lines.append(f"장소: {session_info['location']}")
    if info_lines:
        parts.append("[회의 정보]\n" + "\n".join(info_lines))

    if participants:
        lines = [
            f"- {p.get('name', '?')} ({p.get('dept', '')}{'·진행' if p.get('role') == 'admin' else ''})"
            for p in participants
        ]
        parts.append("[참석자]\n" + "\n".join(lines))

    if prev_minutes:
        # 연속성 참고용일 뿐 — 이번 회의록 본문은 반드시 아래 [STT 대화 기록]만으로 작성한다.
        # (다른 세션 내용을 이번 회의 내용으로 옮겨 적지 말 것)
        parts.append(
            "[이전 회의 흐름 — 연속성 참고용. 이번 회의록 본문에 그대로 옮기지 말 것]\n"
            + "\n\n".join(prev_minutes)
        )

    if agenda_text and agenda_text.strip() not in ("없음", ""):
        parts.append(f"[등록된 안건]\n{agenda_text}")

    if overdue_agendas:
        lines = [
            f"- {a['title']}"
            + (f" (마감: {a['due_date']})" if a.get("due_date") else "")
            for a in overdue_agendas
        ]
        parts.append(
            "[미해결 안건 — 이번 회의에서 다뤄졌을 가능성 높음]\n" + "\n".join(lines)
        )

    if report_chunks:
        parts.append(
            "[관련 보고서 내용 — 필요한 경우 회의록에 통합할 것]\n"
            + "\n\n---\n\n".join(report_chunks[:4])
        )

    parts.append("""\
[절대 원칙 — 반드시 준수]
1. 발언을 요약하거나 예쁘게 다듬는 것이 목적이 아님. 회의에서 도출된 결론·방향·수치·결정만 압축해 기록할 것
2. 발언 내용 중 결론이 없는 잡담·중복 발언은 완전히 제거할 것
3. 어투: ~함 / ~됨 / ~예정 / ~결정 / ~필요 (명사형·단형 종결. "~습니다" 절대 금지)
4. 화살표 활용: → 함의·후속액션, ← 참고·출처
5. 수치·퍼센트·금액·일정이 나오면 반드시 표로 정리할 것 (산문 안에 수치 나열 금지)
6. 비교·대안·계획이 나오면 표로 정리할 것
7. 주제별 소제목(###) 필수 사용 — 소제목 없이 이어서 쓰는 것 금지
8. 관련 보고서 내용은 해당 섹션에 통합하고 출처 표기: → [보고서명]""")

    return "\n\n".join(parts)


def generate_minutes_human(
    transcript: str, now: str, summary_blocks: list = None
) -> str:
    blocks_section = ""
    if summary_blocks:
        blocks_text = "\n\n".join(summary_blocks)
        blocks_section = f"""
[실시간 논의 요약 블록 — 주요 토픽 흐름]
{blocks_text}

"""
    return f"""\
다음 STT 대화 기록으로 회의록을 작성해주세요.
{blocks_section}
[STT 대화 기록]
---
{transcript}
---

아래 형식으로 작성하세요:

# 회의록

**일시:** {now}
**참석자:** (대화 기록에서 발언자 추출)

---

## 1. 회의 목적 및 배경
2-3문장. 왜 이 회의가 열렸는지, 무엇을 결정하기 위한 자리인지만 기술. ~임 / ~됨 어투.

## 2. 안건별 주요 논의
각 안건은 반드시 아래 형식으로 번호를 붙여 구분하고, 안건 사이에 반드시 `---` 구분선을 넣을 것:

### 안건 1. (주제명) — 발표자/담당자
내용

---

### 안건 2. (주제명) — 발표자/담당자
내용

표는 오직 아래 데이터에만 사용할 것:
- 같은 속성(열)을 공유하는 항목이 2개 이상인 데이터 (예: 채널별 지원자수, 항목별 예산)
- 수치·금액·퍼센트·점수 비교
- 담당자+내용+기한이 묶이는 액션 아이템 3개 이상

표에 절대 넣으면 안 되는 것:
- 배경 설명, 조치 내용, 향후 방향 → bullet point로 작성
- 결정 사항, 의견, 방향성 → bullet point로 작성
- 한 문장으로 표현 가능한 내용 → bullet point로 작성
- 표의 행이 1개뿐인 경우 → bullet point로 작성

각 안건은 아래 4가지 흐름으로 서술할 것 (해당 내용이 없으면 생략):
① 배경: 이 안건이 왜 나왔는지 (이전 회의 미결, 보고서 검토 결과, 외부 이슈 등)
② 현황/논의: 현재 상태나 주요 논의 내용. 수치·비교·계획은 표로
③ 조치/결정: 어떤 조치가 취해졌거나 결정됐는지
④ 향후 방향: 다음 단계, 담당자, 기한

관련 보고서가 있으면 ①②에 통합하고 → [보고서명] 출처 표기

예시:
### 안건 1. (1분기 예산 집행 현황) — 운영팀
• **배경**: 전분기 인프라 비용 초과로 인해 집행률 점검 필요 ← [운영팀_예산보고서.pdf]
• **현황**:
| 항목 | 예산 | 집행 | 잔여율 |
|------|------|------|--------|
| 인프라 | 1억 | 9천만 | 10% |
| 인건비 | 5천만 | 4천만 | 20% |
• **조치**: 인프라 항목 2분기 예산 15% 감축 결정
• **향후 방향**: 월별 집행률 모니터링 체계 구축 → 운영팀 / 6월 말

---

### 아젠다 2. (신규 채용 계획) — 인사팀
• **배경**: 2분기 프로젝트 인력 부족 이슈 지속 제기
• **현황**: 상반기 채용 목표 10명 중 6명 확정, 4명 미달
• **조치**: 채용 채널 확대(LinkedIn 추가) 결정
• **향후 방향**: 하반기 추가 채용 여부 7월 초 재논의

## 3. 결정 사항
확정된 내용만. 논의 중인 것은 5번으로. 배경 한 줄 포함.
- **[결정 내용]** ← 배경: ~

## 4. 액션 아이템
3개 미만이면 bullet, 3개 이상이면 표.
| 담당자 | 내용 | 기한 |
|--------|------|------|

## 5. 보류 및 추가 검토 사항
결론 못 낸 항목만. 없으면 "없음".

## 6. 다음 회의 아젠다
이번 논의에서 도출된 것만. 없으면 "없음"."""


# ─── report_agent ─────────────────────────────────────────────────────────────

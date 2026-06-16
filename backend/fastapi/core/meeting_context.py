"""회의 중 보고자료(report)·안건(agenda) 맥락을 모아 AI 기능에 공통 주입하는 GraphRAG 헬퍼.

회의 지식 그래프의 핵심 경로 **report-[:취급]->agenda** (= PostgreSQL reports.related_agenda_ids)와
**Meetings-[:추출]->agenda**를 따라, 현재 회의의 보고자료·안건·추출 근거(ai_evidence)를 한 덩어리
컨텍스트로 만든다. 실시간 STT 용어교정·회의 요약 정제·회의록 생성·세션 챗봇이 모두 같은 맥락을 쓴다.

원천은 PostgreSQL(권위 소스)이다 — reports.related_agenda_ids가 그래프의 report-[:취급]->agenda와
동치이므로 동기 DB 세션만으로 일관된 결과를 얻는다. 보고자료 본문(PDF 텍스트)은 Neo4j ReportChunk에만
있어, 본문까지 필요한 비동기 호출부는 graphdb/knowledge_manager.search_knowledge를 추가로 쓴다.
"""

import logging
import re

from sqlalchemy.orm import Session

from db import models

logger = logging.getLogger(__name__)

_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,5}$")  # 파일 확장자 제거


def _strip_ext(name: str) -> str:
    return _EXT_RE.sub("", (name or "").strip())


def _agenda_brief(agenda, evidence_chars: int) -> str:
    """안건 제목 + 추출 근거(ai_evidence) 요약 한 줄."""
    title = (agenda.title or "").strip()
    ev = (agenda.ai_evidence or "").strip().replace("\n", " ")
    if ev and evidence_chars > 0:
        return f"{title} — 근거: {ev[:evidence_chars]}" if title else ev[:evidence_chars]
    return title


def meeting_glossary_terms(db: Session, meeting_id: int, limit: int = 40) -> list[str]:
    """현재 회의의 보고자료명·제출부서·안건 제목을 STT 고유명사 힌트 후보로 모은다(순서 유지 중복 제거)."""
    if not meeting_id:
        return []
    terms: list[str] = []
    try:
        for r in (
            db.query(models.Report)
            .filter(models.Report.meeting_id == meeting_id)
            .order_by(models.Report.created_at.desc())
            .limit(20)
            .all()
        ):
            if r.file_name:
                terms.append(_strip_ext(r.file_name))
            if r.submitter_department:
                terms.append(r.submitter_department.strip())
        for a in (
            db.query(models.Agenda)
            .filter(
                models.Agenda.meeting_id == meeting_id,
                models.Agenda.status != "draft",
            )
            .order_by(models.Agenda.created_at.desc())
            .limit(40)
            .all()
        ):
            if a.title:
                terms.append(a.title.strip())
    except Exception as e:
        logger.warning(f"[meeting_context] glossary terms 실패(meeting={meeting_id}): {e}")
        return []

    seen: set[str] = set()
    uniq: list[str] = []
    for t in terms:
        t = (t or "").strip()
        if t and len(t) <= 80 and t not in seen:
            seen.add(t)
            uniq.append(t)
        if len(uniq) >= limit:
            break
    return uniq


def meeting_report_agenda_context(
    db: Session,
    meeting_id: int,
    *,
    max_reports: int = 8,
    max_agendas: int = 12,
    evidence_chars: int = 240,
) -> str:
    """보고자료-[:취급]->안건 + 추출 근거(ai_evidence)를 묶은 회의 맥락 텍스트.

    빈 회의(보고자료·안건 없음)면 빈 문자열을 반환한다 — 호출부는 빈 값이면 주입하지 않는다.
    """
    if not meeting_id:
        return ""
    try:
        agendas = (
            db.query(models.Agenda)
            .filter(
                models.Agenda.meeting_id == meeting_id,
                models.Agenda.status != "draft",
            )
            .order_by(models.Agenda.created_at.desc())
            .limit(60)
            .all()
        )
        agenda_by_id = {a.id: a for a in agendas}
        reports = (
            db.query(models.Report)
            .filter(
                models.Report.meeting_id == meeting_id,
                models.Report.human_status != "rejected",
            )
            .order_by(models.Report.created_at.desc())
            .limit(max_reports)
            .all()
        )
    except Exception as e:
        logger.warning(
            f"[meeting_context] report/agenda 조회 실패(meeting={meeting_id}): {e}"
        )
        return ""

    blocks: list[str] = []

    if reports:
        rlines: list[str] = []
        for r in reports:
            name = r.file_name or "(이름없음)"
            dept = (r.submitter_department or "").strip()
            head = f"• {name}" + (f" [{dept}]" if dept else "")
            handled: list[str] = []
            for aid in r.related_agenda_ids or []:
                try:
                    a = agenda_by_id.get(int(aid))
                except (ValueError, TypeError):
                    a = None
                if a and a.title:
                    handled.append(a.title.strip())
            if handled:
                head += " → 취급 안건: " + ", ".join(handled)
            rlines.append(head)
        blocks.append("[보고자료]\n" + "\n".join(rlines))

    if agendas:
        alines = [f"• {_agenda_brief(a, evidence_chars)}" for a in agendas[:max_agendas]]
        blocks.append("[안건 및 추출 근거]\n" + "\n".join(alines))

    return "\n\n".join(blocks)

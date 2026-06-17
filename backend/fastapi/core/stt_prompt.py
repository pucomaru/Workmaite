"""STT 도메인 어휘 프롬프트 (P-STT1)

회의 제목 + 참석자 이름 + 부서명을 전사 모델에 바이어스(prompt)로 주입해, 회의에서 자주
등장하는 고유명사(사람·조직·부서)의 인식 정확도를 높인다. 라이브(realtime/transcription.py)와
배치(routers/stt.py) 양쪽에서 동일하게 사용한다.

빈 값/조회 실패 시 빈 문자열을 반환하며, 호출부는 빈 문자열이면 prompt를 주입하지 않는다.
"""

import logging

from sqlalchemy.orm import Session

from db import models

logger = logging.getLogger(__name__)

# 전사 prompt는 과도하게 길면 오히려 역효과 — 핵심 고유명사 위주로 길이를 제한한다.
_MAX_PROMPT_CHARS = 900


def build_vocab_prompt(db: Session, session_id) -> str:
    """session_id가 속한 회의의 제목·참석자 이름·부서명을 한 줄 어휘 힌트로 만든다."""
    if not session_id:
        return ""
    try:
        sess = (
            db.query(models.MeetingSession)
            .filter(models.MeetingSession.id == session_id)
            .first()
        )
        if not sess:
            return ""

        meeting = (
            db.query(models.Meeting)
            .filter(models.Meeting.id == sess.meeting_id)
            .first()
        )
        members = (
            db.query(models.User)
            .join(
                models.MeetingMember,
                models.MeetingMember.user_id == models.User.id,
            )
            .filter(models.MeetingMember.meeting_id == sess.meeting_id)
            .all()
        )

        terms: list[str] = []
        if meeting and meeting.title:
            terms.append(meeting.title)
        terms.extend(u.name for u in members if u.name)
        terms.extend(u.department for u in members if u.department)

        # 회의 중 다루는 보고자료명·안건 제목도 고유명사 힌트로 추가 (report-[:취급]->agenda 맥락).
        # 음차된 도메인 용어(제품·시스템·약어)가 보고자료/안건에 등장하므로 인식·교정 정확도가 오른다.
        try:
            from core.meeting_context import meeting_glossary_terms

            terms.extend(meeting_glossary_terms(db, sess.meeting_id, limit=30))
        except Exception:
            pass

        # 순서 유지 중복 제거
        seen: set[str] = set()
        uniq: list[str] = []
        for t in terms:
            t = (t or "").strip()
            if t and t not in seen:
                seen.add(t)
                uniq.append(t)
        if not uniq:
            return ""

        prompt = "회의 관련 고유명사: " + ", ".join(uniq)
        return prompt[:_MAX_PROMPT_CHARS]
    except Exception as e:
        logger.warning(
            f"[STT prompt] 어휘 프롬프트 생성 실패(session={session_id}): {e}"
        )
        return ""

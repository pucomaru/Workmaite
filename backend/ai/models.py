from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, Boolean,
    ForeignKey, JSON, Float, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from database import Base

# ──────────────────────────────────────────────────────────────────────────────
# SpringBoot가 관리하는 공유 테이블 (FastAPI는 기본적으로 읽기 전용)
# ddl-auto:update 대상 → Base.metadata.create_all에서 제외
# ──────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id            = Column(BigInteger, primary_key=True, index=True)
    name          = Column(String(100), nullable=False)
    email         = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    company       = Column(String(100), nullable=True)
    department    = Column(String(100), nullable=True)
    position      = Column(String(100), nullable=True)
    created_at    = Column(DateTime, nullable=False)

    notifications = relationship("Notification", back_populates="user")


class Meeting(Base):
    __tablename__ = "meetings"
    id          = Column(BigInteger, primary_key=True, index=True)
    title       = Column(String(255), nullable=False)
    purpose     = Column(Text)
    guidelines  = Column(Text, nullable=True)
    priority    = Column(String(20), nullable=False, default="NORMAL")  # NORMAL|HIGH|URGENT
    type        = Column(String(20), nullable=True)                     # WEEKLY|MONTHLY|QUARTERLY
    start_date  = Column(DateTime, nullable=True)
    end_date    = Column(DateTime, nullable=True)
    status      = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE|ENDED
    created_by  = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at  = Column(DateTime, nullable=False)


class MeetingMember(Base):
    __tablename__ = "meeting_members"
    __table_args__ = (UniqueConstraint("meeting_id", "user_id"),)
    id         = Column(BigInteger, primary_key=True, index=True)
    meeting_id = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    user_id    = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    role       = Column(String(20), nullable=False)   # SECRETARY | MEMBER
    created_at = Column(DateTime)

    user = relationship("User", foreign_keys=[user_id])


class MeetingSession(Base):
    __tablename__ = "meeting_sessions"
    id           = Column(BigInteger, primary_key=True, index=True)
    meeting_id   = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    title        = Column(String(255), nullable=True)
    location     = Column(String(255), nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    started_at   = Column(DateTime, nullable=True)
    ended_at     = Column(DateTime, nullable=True)
    status       = Column(String(20), nullable=False, default="SCHEDULED")  # SCHEDULED|ONGOING|ENDED
    created_at   = Column(DateTime, nullable=False)

    minutes = relationship("Minutes", back_populates="session", uselist=False)


class MeetingRelation(Base):
    """회의체 간 관계 (부모-자식, 연관, 후속 등)"""
    __tablename__ = "meeting_relations"
    __table_args__ = (UniqueConstraint("source_meeting_id", "target_meeting_id", "relation_type"),)
    id                = Column(BigInteger, primary_key=True, index=True)
    source_meeting_id = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    target_meeting_id = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    relation_type     = Column(String(50), nullable=False)   # PARENT_OF | RELATED_TO | FOLLOW_UP
    created_by        = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at        = Column(DateTime, default=datetime.utcnow)


class Agenda(Base):
    __tablename__ = "agendas"
    id          = Column(BigInteger, primary_key=True, index=True)
    meeting_id  = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    assignee_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    title       = Column(String(255), nullable=False)
    content     = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False, default=0)
    status      = Column(String(20), nullable=False, default="ON_HOLD")  # ON_HOLD|IN_PROGRESS|DONE
    created_at  = Column(DateTime)


class Report(Base):
    __tablename__ = "report_reviews"
    id               = Column(BigInteger, primary_key=True, index=True)
    meeting_id       = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    session_id       = Column(BigInteger, ForeignKey("meeting_sessions.id"), nullable=True)
    uploader_id      = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    parent_id        = Column(BigInteger, ForeignKey("report_reviews.id"), nullable=True)
    version          = Column(Integer, nullable=False, default=1)
    file_type        = Column(String(20), nullable=False)   # PDF | PPT | DOCX | HWP | ETC
    file_name        = Column(String(255), nullable=True)
    file_path        = Column(String(500), nullable=True)
    status           = Column(String(20), nullable=False, default="SUBMITTED")
                                                            # SUBMITTED|REVIEWING|REVIEWED|APPROVED|REJECTED
    score            = Column(Float, nullable=True)
    layer1_result    = Column(Text, nullable=True)          # jsonb: 1차 검토 결과
    layer2_result    = Column(Text, nullable=True)          # jsonb: 2차 검토 결과
    layer3_result    = Column(Text, nullable=True)          # jsonb: 3차 검토 결과
    feedback         = Column(Text, nullable=True)
    missing_elements = Column(Text, nullable=True)          # jsonb
    created_at       = Column(DateTime, default=datetime.utcnow)


class ArchiveCombined(Base):
    """최종 아카이브 - 확정된 회의록/보고서/안건을 통합 보관"""
    __tablename__ = "archives_combined"
    id          = Column(BigInteger, primary_key=True, index=True)
    meeting_id  = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    session_id  = Column(BigInteger, ForeignKey("meeting_sessions.id"), nullable=True)
    type        = Column(String(20), nullable=False)       # MINUTES | REPORT | AGENDA
    title       = Column(String(255), nullable=True)
    content     = Column(Text, nullable=True)              # 최종 텍스트 내용
    file_path   = Column(String(500), nullable=True)       # 파일 경로 (선택)
    source_type = Column(String(30), nullable=True)        # minutes | report_reviews | agendas
    source_id   = Column(BigInteger, nullable=True)        # 원본 레코드 ID
    archived_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    status      = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE | DELETED
    archived_at = Column(DateTime, default=datetime.utcnow)


class ReportCriteria(Base):
    """회의체별 자료 평가 기준"""
    __tablename__ = "report_criteria"
    id           = Column(BigInteger, primary_key=True, index=True)
    meeting_id   = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    name         = Column(String(255), nullable=False)
    description  = Column(Text, nullable=True)
    max_score    = Column(Float, default=100.0)
    weight       = Column(Float, default=1.0)
    layer_number = Column(Integer, nullable=True)   # 1 | 2 | 3
    created_at   = Column(DateTime, default=datetime.utcnow)


class SttSegment(Base):
    __tablename__ = "stt_segments"
    id             = Column(BigInteger, primary_key=True, index=True)
    session_id     = Column(BigInteger, ForeignKey("meeting_sessions.id"), nullable=False)
    speaker_label  = Column(String(50), nullable=False)    # SPEAKER_00, SPEAKER_01, ...
    speaker_user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    content        = Column(Text, nullable=False)
    start_sec      = Column(Float, nullable=False)
    end_sec        = Column(Float, nullable=False)
    confidence     = Column(Float, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)


class Minutes(Base):
    __tablename__ = "minutes"
    id              = Column(BigInteger, primary_key=True, index=True)
    session_id      = Column(BigInteger, ForeignKey("meeting_sessions.id"), nullable=False, unique=True)
    recorder_id     = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    content_raw     = Column(Text, nullable=True)    # STT 원문
    content_original = Column(Text, nullable=True)   # 원본 편집본
    content_summary = Column(Text, nullable=True)    # AI 요약
    status          = Column(String(20), nullable=False, default="DRAFT")  # DRAFT | CONFIRMED
    generated_at    = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    session = relationship("MeetingSession", back_populates="minutes")


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI가 단독으로 관리하는 테이블
# Base.metadata.create_all 대상 (checkfirst=True)
# ──────────────────────────────────────────────────────────────────────────────

class Todo(Base):
    __tablename__ = "todos"
    id            = Column(BigInteger, primary_key=True, index=True)
    meeting_id    = Column(BigInteger, ForeignKey("meetings.id"), nullable=False)
    user_id       = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    agenda_id     = Column(BigInteger, ForeignKey("agendas.id"), nullable=True)
    content       = Column(Text, nullable=False)
    assignee_name = Column(String(100), nullable=True)
    assignee_dept = Column(String(100), nullable=True)
    how           = Column(Text, nullable=True)
    why           = Column(Text, nullable=True)
    priority      = Column(String(30), default="normal")
    tags          = Column(JSON, nullable=True)
    due_date      = Column(DateTime, nullable=True)
    status        = Column(String(20), nullable=False, default="pending")
    source_type   = Column(String(20), nullable=False, default="report")
    created_at    = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id         = Column(BigInteger, primary_key=True, index=True)
    user_id    = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    type       = Column(String(50))
    message    = Column(Text)
    is_read    = Column(Boolean, default=False)
    ref_id     = Column(BigInteger, nullable=True)
    ref_type   = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id           = Column(BigInteger, primary_key=True, index=True)
    user_id      = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    context_type = Column(String(30), nullable=False)  # agenda|prepare|report|room|minutes|sessions
    context_id   = Column(BigInteger, nullable=False)
    role         = Column(String(10), nullable=False)  # user | agent
    content      = Column(Text, nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow)


class AgentLog(Base):
    """Neo4j 동기화 실패 및 AI 작업 로그 (FastAPI 관리)"""
    __tablename__ = "agent_logs"
    id           = Column(BigInteger, primary_key=True, index=True)
    operation    = Column(String(100), nullable=False, index=True)
    entity_type  = Column(String(50), nullable=True)
    entity_id    = Column(String(100), nullable=True, index=True)
    status       = Column(String(20), nullable=False, default="failed", index=True)
                                                    # failed | recovered | skipped | success
    error_detail = Column(Text, nullable=True)
    payload      = Column(JSON, nullable=True)
    retry_count  = Column(Integer, default=0)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TokenUsageLog(Base):
    """AI API 토큰 사용량 기록"""
    __tablename__ = "token_usage_logs"
    id                = Column(BigInteger, primary_key=True, index=True)
    user_id           = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    meeting_id        = Column(BigInteger, ForeignKey("meetings.id"), nullable=True)
    operation         = Column(String(100), nullable=False)  # report_review|minutes_gen|chat|agenda_extract
    model             = Column(String(100), nullable=False)
    prompt_tokens     = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens      = Column(Integer, default=0)
    created_at        = Column(DateTime, default=datetime.utcnow)


class HitlReview(Base):
    """Human-In-The-Loop 검토 기록 (AI 제안 → 사람 승인/거부/수정)"""
    __tablename__ = "hitl_reviews"
    id             = Column(BigInteger, primary_key=True, index=True)
    meeting_id     = Column(BigInteger, ForeignKey("meetings.id"), nullable=True)
    session_id     = Column(BigInteger, ForeignKey("meeting_sessions.id"), nullable=True)
    target_type    = Column(String(50), nullable=False)  # report|minutes|agenda|extracted_item
    target_id      = Column(BigInteger, nullable=True)
    status         = Column(String(20), nullable=False, default="PENDING")
                                                         # PENDING|APPROVED|REJECTED|REVISED
    reviewer_id    = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    ai_output      = Column(Text, nullable=True)         # AI가 생성한 결과
    human_decision = Column(Text, nullable=True)         # 사람이 수정한 내용
    comment        = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    reviewed_at    = Column(DateTime, nullable=True)

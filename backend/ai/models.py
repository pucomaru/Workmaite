"""SQLAlchemy 모델 — **읽기 전용 매핑** (P2-1).

스키마의 단일 소스는 Spring의 Flyway 마이그레이션(backend/springboot/src/main/resources/db/migration)이다.
이 파일로 스키마를 생성/변경하지 말 것 (Base.metadata.create_all 금지).
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, JSON, Float, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(100), nullable=False)
    email         = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    company       = Column(String(100), nullable=True)
    department    = Column(String(100), nullable=True)
    position      = Column(String(100), nullable=True)
    # 시스템 수준 역할 (P1-3 RBAC): USER / SYSTEM_ADMIN / COMPANY_ADMIN
    role          = Column(String(30), nullable=False, default="USER", server_default="USER")
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow)


class ReportAgenda(Base):
    """보고서-아젠다 연결 정규화 (P2-8) — reports.related_agenda_ids의 관계형 대체."""
    __tablename__ = "report_agendas"
    report_id = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True)
    agenda_id = Column(Integer, ForeignKey("agenda.id", ondelete="CASCADE"), primary_key=True)


class Meeting(Base):
    __tablename__ = "meetings"
    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    guidelines  = Column(Text, nullable=True)
    context     = Column(Text, nullable=True)
    type        = Column(String(20), nullable=True)
    start_date  = Column(DateTime, nullable=True)
    end_date    = Column(DateTime, nullable=True)
    status      = Column(String(20), default="active")
    created_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow)


class MeetingMember(Base):
    __tablename__ = "meeting_members"
    __table_args__ = (UniqueConstraint("meeting_id", "user_id"),)
    id         = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    role       = Column(String(20), nullable=False)
    priority   = Column(String(20), default="medium")

    user = relationship("User", foreign_keys=[user_id])


class MeetingSession(Base):
    __tablename__ = "meeting_sessions"
    id                = Column(Integer, primary_key=True, index=True)
    meeting_id        = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    title             = Column(String(255), nullable=True)
    description       = Column(String(255), nullable=True)
    location          = Column(String(255), nullable=True)
    type              = Column(String(50), nullable=False)
    scheduled_at      = Column(DateTime, nullable=True)
    started_at        = Column(DateTime, nullable=True)
    ended_at          = Column(DateTime, nullable=True)
    status            = Column(String(20), default="scheduled")
    recording_seconds = Column(Integer, default=0, nullable=False)
    last_resumed_at   = Column(DateTime, nullable=True)

    minutes = relationship("Minutes", back_populates="session", uselist=False)


class Agenda(Base):
    __tablename__ = "agenda"
    id          = Column(Integer, primary_key=True, index=True)
    meeting_id  = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    session_id  = Column(Integer, ForeignKey("meeting_sessions.id"), nullable=True)
    title       = Column(String(255), nullable=False)
    status      = Column(String(20), default="draft")
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    department  = Column(JSON, nullable=True)
    due_date    = Column(DateTime, nullable=True)
    priority    = Column(String(20), default="medium")
    ai_evidence = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"
    id                   = Column(Integer, primary_key=True, index=True)
    meeting_id           = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    parent_id            = Column(Integer, ForeignKey("reports.id"), nullable=True)
    upload_id            = Column(Integer, ForeignKey("users.id"), nullable=False)
    version              = Column(Integer, nullable=False, default=1)
    submitter_department = Column(String(255), nullable=False, default="")
    file_name            = Column(String(255), nullable=True)
    file_path            = Column(String(500), nullable=True)
    human_status         = Column(String(20), default="pending")
    related_agenda_ids   = Column(JSON, nullable=True, default=list)
    created_at           = Column(DateTime, default=datetime.utcnow)


class ReportScore(Base):
    __tablename__ = "report_scores"
    id            = Column(Integer, primary_key=True, index=True)
    report_id     = Column(Integer, ForeignKey("reports.id"), nullable=False)
    ai_status     = Column(String(20), nullable=False, default="pending")
    total_score   = Column(Float, nullable=True)
    detail_scores = Column(JSON, nullable=True)
    feedback      = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)



class SttSegment(Base):
    __tablename__ = "stt_segments"
    id              = Column(Integer, primary_key=True, index=True)
    session_id      = Column(Integer, ForeignKey("meeting_sessions.id"), nullable=False)
    speaker_label   = Column(String(50), nullable=False)
    speaker_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    content         = Column(Text, nullable=False)
    start_sec       = Column(Float, nullable=False)
    end_sec         = Column(Float, nullable=False)
    confidence      = Column(Float, nullable=True)
    provider        = Column(String(30), nullable=True)  # localwhisper | gcapi | whisperapi
    created_at      = Column(DateTime, default=datetime.utcnow)


class Minutes(Base):
    __tablename__ = "minutes"
    id               = Column(Integer, primary_key=True, index=True)
    session_id       = Column(Integer, ForeignKey("meeting_sessions.id"), nullable=False, unique=True)
    file_name        = Column(String(255), nullable=True)
    file_path        = Column(String(500), nullable=True)
    recorder_id      = Column(Integer, ForeignKey("users.id"), nullable=True)
    content_original = Column(Text, nullable=True)
    content_summary  = Column(Text, nullable=True)
    status           = Column(String(20), default="DRAFT")
    generated_at     = Column(DateTime, default=datetime.utcnow)

    session = relationship("MeetingSession", back_populates="minutes")


class SessionMember(Base):
    __tablename__ = "session_members"
    id         = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("meeting_sessions.id"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    role       = Column(String, default="member")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id           = Column(Integer, primary_key=True, index=True)
    thread_id    = Column(String(100), nullable=False)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    role         = Column(String(10), nullable=False)
    content      = Column(Text, nullable=True)
    file_path    = Column(String(500), nullable=True)
    file_name    = Column(String(255), nullable=True)
    context_type = Column(String(20), nullable=True)
    meeting_id   = Column(Integer, ForeignKey("meetings.id"), nullable=True)
    session_id   = Column(Integer, ForeignKey("meeting_sessions.id"), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)


class AgentLog(Base):
    __tablename__ = "agent_logs"
    id              = Column(Integer, primary_key=True, index=True)
    task_id         = Column(String(100), nullable=False, unique=True)
    context_type    = Column(String(30), nullable=False)
    meeting_id      = Column(Integer, ForeignKey("meetings.id"), nullable=True)
    session_id      = Column(Integer, ForeignKey("meeting_sessions.id"), nullable=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True)
    status          = Column(String(20), default="pending")
    input_data      = Column(JSON, nullable=True)
    output_data     = Column(JSON, nullable=True)
    reasoning_steps = Column(JSON, nullable=True)
    loop_count      = Column(Integer, default=0)
    error_message   = Column(Text, nullable=True)
    ended_at        = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)


class TokenUsageLog(Base):
    __tablename__ = "token_usage_logs"
    id                 = Column(Integer, primary_key=True, index=True)
    agent_log_id       = Column(Integer, ForeignKey("agent_logs.id"), nullable=False)
    model_name         = Column(String(50), nullable=False)
    prompt_tokens      = Column(Integer, nullable=False)
    completion_tokens  = Column(Integer, nullable=False)
    estimated_cost_usd = Column(Float, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)


class SessionSummaryBlock(Base):
    __tablename__ = "session_summary_blocks"
    id                  = Column(Integer, primary_key=True, index=True)
    session_id          = Column(Integer, ForeignKey("meeting_sessions.id"), nullable=False)
    block_index         = Column(Integer, nullable=False)
    title               = Column(String(500), nullable=True)
    bullets             = Column(JSON, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    recording_start_sec = Column(Float, nullable=True)
    recording_end_sec   = Column(Float, nullable=True)


class HitlReview(Base):
    __tablename__ = "hitl_reviews"
    id            = Column(Integer, primary_key=True, index=True)
    agent_log_id  = Column(Integer, ForeignKey("agent_logs.id"), nullable=True)
    target_type   = Column(String(30), nullable=False)
    agenda_id     = Column(Integer, ForeignKey("agenda.id"), nullable=True)
    report_id     = Column(Integer, ForeignKey("reports.id"), nullable=True)
    ai_rationale  = Column(Text, nullable=True)
    status        = Column(Text, default="검토중")
    reviewer_id   = Column(Integer, ForeignKey("users.id"), nullable=True)
    comment       = Column(Text, nullable=True)
    reviewed_at   = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


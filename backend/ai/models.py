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
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow)


class Meeting(Base):
    __tablename__ = "meetings"
    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    guidelines  = Column(Text, nullable=True)
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
    id           = Column(Integer, primary_key=True, index=True)
    meeting_id   = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    title        = Column(String(255), nullable=True)
    description  = Column(String(255), nullable=True)
    location     = Column(String(255), nullable=True)
    type         = Column(String(50), nullable=False)
    scheduled_at = Column(DateTime, nullable=True)
    started_at   = Column(DateTime, nullable=True)
    ended_at     = Column(DateTime, nullable=True)
    status       = Column(String(20), default="scheduled")

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
    status           = Column(String(20), default="draft")
    generated_at     = Column(DateTime, default=datetime.utcnow)

    session = relationship("MeetingSession", back_populates="minutes")


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
    cost               = Column(Float, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)


class HitlReview(Base):
    __tablename__ = "hitl_reviews"
    id             = Column(Integer, primary_key=True, index=True)
    agent_log_id   = Column(Integer, ForeignKey("agent_logs.id"), nullable=True)
    target_type    = Column(String(30), nullable=False)
    target_id      = Column(Integer, nullable=False)
    review_prompt  = Column(JSON, nullable=True)
    ai_rationale   = Column(Text, nullable=True)
    status         = Column(String(20), default="pending")
    reviewer_id    = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_comment = Column(JSON, nullable=True)
    reviewed_at    = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)


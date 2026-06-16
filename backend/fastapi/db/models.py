"""SQLAlchemy 모델 — **읽기 전용 매핑** (P2-1).

스키마는 운영 PostgreSQL에서 외부 관리된다(자동 마이그레이션 미사용).
이 파일로 스키마를 생성/변경하지 말 것 (Base.metadata.create_all 금지).

타입 표기는 SQLAlchemy 2.0 `Mapped[]`/`mapped_column()` 스타일 — 컬럼 정의(타입·nullable·FK·
default)는 기존과 동일하며, 정적 타입 검사가 ORM 속성을 파이썬 타입으로 인식하도록 어노테이션만 부여한다.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Integer,
    BigInteger,
    SmallInteger,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Float,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.database import Base


class Company(Base):
    """회사(테넌트) — companies 테이블 (P1-7② 정규화, MT-4)."""

    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 회사 정규화 (P1-7②) — users.company 문자열 폐기, companies FK
    company_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("companies.id"), nullable=True
    )
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 조직(회사) 수준 역할 (P1-3 RBAC): USER / SYSTEM_ADMIN / COMPANY_ADMIN.
    # 회의체 권한(meeting_members.role=meeting_role)과 구분. DB 컬럼명은 role 유지.
    company_role: Mapped[str] = mapped_column(
        "role", String(30), nullable=False, default="USER", server_default="USER"
    )
    # 소프트 삭제 플래그 (MT-6 개정) — False면 탈퇴 계정. 작성한 회의록·보고서 등 참조
    # 무결성을 보존하기 위해 행은 남기고 비활성화한다. 로그인·디렉터리에서 제외된다.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company | None"] = relationship("Company", lazy="joined")

    @property
    def company_name(self) -> str | None:
        return self.company.name if self.company else None


class ReportAgenda(Base):
    """보고서-아젠다 연결 정규화 (P2-8) — reports.related_agenda_ids의 관계형 대체."""

    __tablename__ = "report_agendas"
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True
    )
    agenda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agenda.id", ondelete="CASCADE"), primary_key=True
    )


class Meeting(Base):
    __tablename__ = "meetings"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    guidelines: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MeetingMember(Base):
    __tablename__ = "meeting_members"
    __table_args__ = (UniqueConstraint("meeting_id", "user_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meetings.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    # 회의체 수준 권한 admin|member — 조직 권한(users.role=company_role)과 구분. DB 컬럼명은 role 유지.
    meeting_role: Mapped[str] = mapped_column("role", String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium")

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class MeetingSession(Base):
    __tablename__ = "meeting_sessions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meetings.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    recording_seconds: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False
    )
    last_resumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=datetime.utcnow)

    minutes: Mapped["Minutes | None"] = relationship(
        "Minutes", back_populates="session", uselist=False
    )


class Agenda(Base):
    __tablename__ = "agenda"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meetings.id"), nullable=False
    )
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("meeting_sessions.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    assignee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    department: Mapped[Any] = mapped_column(JSON, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    ai_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SessionAgenda(Base):
    __tablename__ = "session_agendas"
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meeting_sessions.id"), primary_key=True
    )
    agenda_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agenda.id"), primary_key=True
    )


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    meeting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meetings.id"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reports.id"), nullable=True
    )
    upload_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitter_department: Mapped[str] = mapped_column(
        String(255), nullable=False, default=""
    )
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    human_status: Mapped[str] = mapped_column(String(20), default="pending")
    related_agenda_ids: Mapped[Any] = mapped_column(JSON, nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReportScore(Base):
    __tablename__ = "report_scores"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reports.id"), nullable=False
    )
    ai_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail_scores: Mapped[Any] = mapped_column(JSON, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SttSegment(Base):
    __tablename__ = "stt_segments"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meeting_sessions.id"), nullable=False
    )
    speaker_label: Mapped[str] = mapped_column(String(50), nullable=False)
    speaker_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_sec: Mapped[float] = mapped_column(Float, nullable=False)
    end_sec: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)  # openai
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Minutes(Base):
    __tablename__ = "minutes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meeting_sessions.id"), nullable=False, unique=True
    )
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorder_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    content_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["MeetingSession"] = relationship(
        "MeetingSession", back_populates="minutes"
    )


class SessionMember(Base):
    __tablename__ = "session_members"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meeting_sessions.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, default="member")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    context_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    meeting_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("meetings.id"), nullable=True
    )
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("meeting_sessions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatFeedback(Base):
    """응답 피드백 (P3C-3, H-9) — eval 데이터셋 환류용."""

    __tablename__ = "chat_feedback"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False)
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_messages.id"), nullable=True
    )
    agent_log_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_logs.id"), nullable=True
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1=up / -1=down
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentLog(Base):
    __tablename__ = "agent_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    task_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    context_type: Mapped[str] = mapped_column(String(30), nullable=False)
    meeting_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("meetings.id"), nullable=True
    )
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("meeting_sessions.id"), nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    input_data: Mapped[Any] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Any] = mapped_column(JSON, nullable=True)
    reasoning_steps: Mapped[Any] = mapped_column(JSON, nullable=True)
    loop_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LangChain 루트 run id — LangSmith 트레이스 점프용 (P3A-3)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TokenUsageLog(Base):
    __tablename__ = "token_usage_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    agent_log_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agent_logs.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SessionSummaryBlock(Base):
    __tablename__ = "session_summary_blocks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("meeting_sessions.id"), nullable=False
    )
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bullets: Mapped[Any] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    recording_start_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    recording_end_sec: Mapped[float | None] = mapped_column(Float, nullable=True)


class HitlReview(Base):
    __tablename__ = "hitl_reviews"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    agent_log_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_logs.id"), nullable=True
    )
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    agenda_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agenda.id"), nullable=True
    )
    report_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reports.id"), nullable=True
    )
    ai_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="검토중")
    reviewer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GraphRelation(Base):
    """그래프에서 사용자가 수동 생성한 자유 관계(구조 FK 외). 소스 오브 트루스=PostgreSQL이며
    Neo4j에는 동기화(MERGE)된다. node id는 그래프 노드 id 문자열(예: mg-001, agenda-12, p-3)."""

    __tablename__ = "graph_relations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    from_node_id: Mapped[str] = mapped_column(Text, nullable=False)
    rel_type: Mapped[str] = mapped_column(Text, nullable=False)
    to_node_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

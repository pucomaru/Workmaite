from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


# ── User (users) ──────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    company: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    company: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    accessToken: str
    user: UserOut


# ── Meeting (meetings) ────────────────────────────────────────────────────────
class MeetingCreate(BaseModel):
    title: str
    description: Optional[str] = None
    guidelines: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    meeting_type: Optional[str] = None


class MeetingOut(BaseModel):
    # DB 컬럼은 `type` 이지만 API 응답은 `meeting_type` 으로 노출한다.
    id: int
    title: str
    description: Optional[str] = None
    guidelines: Optional[str] = None
    meeting_type: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("meeting_type", "type")
    )
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ── MeetingMember (meeting_members) ───────────────────────────────────────────
class MeetingMemberAdd(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: int = Field(alias="userId")
    role: str  # admin | member


class MeetingMemberOut(BaseModel):
    id: int
    meeting_id: int
    user_id: int
    role: str
    priority: Optional[str] = None
    user: Optional[UserOut] = None

    model_config = ConfigDict(from_attributes=True)


# ── MeetingSession (meeting_sessions) ─────────────────────────────────────────
class SessionCreate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    type: Optional[str] = "offline"
    scheduled_at: Optional[datetime] = None


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    type: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None


class SessionOut(BaseModel):
    id: int
    meeting_id: int
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    type: str
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ── Agenda (agenda) ───────────────────────────────────────────────────────────
class AgendaOut(BaseModel):
    id: int
    meeting_id: int
    session_id: Optional[int] = None
    title: str
    status: Optional[str] = None
    assignee_id: Optional[int] = None
    department: Optional[Any] = None  # JSON
    due_date: Optional[datetime] = None
    priority: Optional[str] = None
    ai_evidence: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Report (reports) ──────────────────────────────────────────────────────────
class ReportOut(BaseModel):
    id: int
    meeting_id: int
    parent_id: Optional[int] = None
    upload_id: int
    version: int
    submitter_department: Optional[str] = None
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    human_status: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ReportStatusUpdate(BaseModel):
    status: str  # approved | rejected | submitted | draft | pending
    comment: Optional[str] = None  # 승인/반려 사유
    notify_teams: bool = False  # Teams 알림 전송 여부


# ── ReportScore (report_scores) ───────────────────────────────────────────────
class ReportScoreOut(BaseModel):
    id: int
    report_id: int
    ai_status: str
    total_score: Optional[float] = None
    detail_scores: Optional[Any] = None  # JSON
    feedback: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── SttSegment (stt_segments) ─────────────────────────────────────────────────
class SttSegmentOut(BaseModel):
    id: int
    session_id: int
    speaker_label: str
    speaker_user_id: Optional[int] = None
    content: str
    start_sec: float
    end_sec: float
    confidence: Optional[float] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Minutes (minutes) ─────────────────────────────────────────────────────────
class MinutesSave(BaseModel):
    content_summary: str


class MinutesOut(BaseModel):
    id: int
    session_id: int
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    recorder_id: Optional[int] = None
    content_original: Optional[str] = None
    content_summary: Optional[str] = None
    status: Optional[str] = None
    generated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── ChatMessage (chat_messages) ───────────────────────────────────────────────
class ChatMessageOut(BaseModel):
    id: int
    thread_id: str
    user_id: int
    role: str
    content: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    context_type: Optional[str] = None
    meeting_id: Optional[int] = None
    session_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── AgentLog (agent_logs) ─────────────────────────────────────────────────────
class AgentLogOut(BaseModel):
    id: int
    task_id: str
    context_type: str
    meeting_id: Optional[int] = None
    session_id: Optional[int] = None
    user_id: Optional[int] = None
    status: Optional[str] = None
    input_data: Optional[Any] = None
    output_data: Optional[Any] = None
    reasoning_steps: Optional[Any] = None
    loop_count: Optional[int] = None
    error_message: Optional[str] = None
    ended_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── HitlReview (hitl_reviews) ─────────────────────────────────────────────────
class HitlReviewOut(BaseModel):
    id: int
    agent_log_id: int
    target_type: str
    target_id: int
    review_prompt: Optional[str] = None
    ai_rationale: Optional[str] = None
    status: Optional[str] = None
    reviewer_id: Optional[int] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ── Agent request DTOs (입력 전용, DB 테이블 아님) ─────────────────────────────
class AgentChatRequest(BaseModel):
    meeting_id: int
    message: str
    chat_history: Optional[List[dict]] = []

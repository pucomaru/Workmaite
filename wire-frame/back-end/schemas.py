from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


# Auth
class UserCreate(BaseModel):
    name: str
    employee_id: str
    password: str
    department: Optional[str] = None


class UserLogin(BaseModel):
    employee_id: str
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    id: int
    name: str
    employee_id: str
    department: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut


# Meeting
class MeetingCreate(BaseModel):
    title: str
    purpose: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class MeetingMemberAdd(BaseModel):
    user_id: int
    role: str  # admin | presenter


class MeetingOut(BaseModel):
    id: int
    title: str
    purpose: Optional[str]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    status: str
    created_by: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MeetingMemberOut(BaseModel):
    id: int
    meeting_id: int
    user_id: int
    role: str
    user: UserOut

    model_config = {"from_attributes": True}


# Agenda
class AgendaCreate(BaseModel):
    department: Optional[str] = None
    content: str


class AgendaUpdate(BaseModel):
    department: Optional[str] = None
    content: Optional[str] = None


class AgendaOut(BaseModel):
    id: int
    meeting_id: int
    department: Optional[str]
    content: str
    status: str
    confirmed_at: Optional[datetime]
    confirmed_by: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


# Todo
class TodoCreate(BaseModel):
    content: str
    due_date: Optional[datetime] = None
    agenda_id: Optional[int] = None
    source_type: Optional[str] = "report"


class TodoUpdate(BaseModel):
    content: Optional[str] = None
    due_date: Optional[datetime] = None
    status: Optional[str] = None


class TodoOut(BaseModel):
    id: int
    meeting_id: int
    user_id: int
    agenda_id: Optional[int]
    content: str
    due_date: Optional[datetime]
    status: str
    source_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


# Report
class ReportOut(BaseModel):
    id: int
    meeting_id: int
    presenter_id: int
    file_path: Optional[str]
    file_name: Optional[str]
    status: str
    score: Optional[float]
    feedback: Optional[Any]
    submitted_at: Optional[datetime]
    approved_at: Optional[datetime]
    created_at: datetime
    presenter: Optional[UserOut] = None

    model_config = {"from_attributes": True}


class ReportStatusUpdate(BaseModel):
    status: str  # approved | rejected


# MeetingLoop
class LoopCreate(BaseModel):
    pass


class LoopOut(BaseModel):
    id: int
    meeting_id: int
    loop_number: int
    sessions: List["SessionOut"] = []
    created_at: datetime

    model_config = {"from_attributes": True}


# MeetingSession
class SessionCreate(BaseModel):
    title: str
    loop_id: int
    scheduled_at: Optional[datetime] = None
    password: Optional[str] = None


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    password: Optional[str] = None


class SessionOut(BaseModel):
    id: int
    meeting_id: int
    loop_id: Optional[int]
    session_number: int
    title: str
    password: Optional[str]
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    status: str

    model_config = {"from_attributes": True}


LoopOut.model_rebuild()


# Minutes
class MinutesOut(BaseModel):
    id: int
    session_id: int
    content_raw: Optional[str]
    content_summary: Optional[str]
    generated_at: datetime

    model_config = {"from_attributes": True}


# CardNews
class CardNewsCreate(BaseModel):
    session_ids: List[int]
    emphasis_points: Optional[str] = None


class CardNewsOut(BaseModel):
    id: int
    meeting_id: int
    session_ids: Any
    title: Optional[str]
    file_path: Optional[str]
    content: Optional[Any]
    created_at: datetime

    model_config = {"from_attributes": True}


# Notification
class NotificationOut(BaseModel):
    id: int
    user_id: int
    type: str
    message: str
    is_read: bool
    created_at: datetime
    ref_id: Optional[int]
    ref_type: Optional[str]

    model_config = {"from_attributes": True}


# TacitKnowledge
class TacitKnowledgeGlobalOut(BaseModel):
    id: int
    category: str
    title: str
    content: str
    version: int
    status: str
    source_event_ids: Optional[Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TacitKnowledgeCreate(BaseModel):
    category: str
    title: str
    content: str


class TacitKnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None


class TacitProposalOut(BaseModel):
    id: int
    scope: str
    meeting_id: Optional[int]
    target_id: Optional[int]
    category: str
    title: str
    proposed_content: str
    diff_summary: Optional[str]
    evidence_summary: Optional[str]
    source_event_ids: Optional[Any]
    status: str
    reviewed_by: Optional[int]
    reviewed_at: Optional[datetime]
    final_content: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ProposalReview(BaseModel):
    action: str  # accept | reject | edit_accept
    final_content: Optional[str] = None


class TacitEventOut(BaseModel):
    id: int
    event_type: str
    meeting_id: Optional[int]
    meeting_type: Optional[str]
    payload: Optional[Any]
    actor_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


# Agent requests
class AgentChatRequest(BaseModel):
    meeting_id: int
    message: str
    chat_history: Optional[List[dict]] = []


class AgendaExtractRequest(BaseModel):
    meeting_id: int
    chat_history: Optional[List[dict]] = []
    previous_minutes: Optional[List[str]] = []


class ReportReviewRequest(BaseModel):
    report_content: str
    agenda: Optional[str] = None
    chat_history: Optional[List[dict]] = []


class HyeanStatusRequest(BaseModel):
    meeting_id: int
    user_role: str


class CardNewsPlanRequest(BaseModel):
    meeting_id: int
    session_ids: List[int]
    chat_history: Optional[List[dict]] = []
    thread_id: Optional[str] = None  # 없으면 백엔드에서 생성


class CardNewsResumeRequest(BaseModel):
    thread_id: str
    meeting_id: int
    session_ids: List[int]
    approved: bool
    feedback: Optional[str] = None   # approved=False 일 때 수정 의견


class CardNewsGenerateRequest(BaseModel):
    meeting_id: int
    session_ids: List[int]
    emphasis_points: Optional[str] = None
    chat_history: Optional[List[dict]] = []
    plan: Optional[dict] = None  # 확정된 기획안 (있으면 이 기획안으로 생성)

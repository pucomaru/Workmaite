from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


# ── User ──────────────────────────────────────────────────────────────────────
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
    department: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    accessToken: str
    user: UserOut


# Meeting
class MeetingCreate(BaseModel):
    title: str
    purpose: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    meeting_type: Optional[str] = None
    parent_id: Optional[int] = None


class MeetingMemberAdd(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: int = Field(alias='userId')
    role: str  # admin | presenter


class MeetingOut(BaseModel):
    id: int
    title: str
    purpose: Optional[str]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    status: str
    guidelines: Optional[str] = None
    meeting_type: Optional[str] = None
    parent_id: Optional[int] = None
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
    agenda_type: Optional[str] = "draft"  # draft | scheduled | closed
    presenter_name: Optional[str] = None
    duration_minutes: Optional[int] = None
    order_num: Optional[int] = 0
    purpose: Optional[str] = None
    due_date: Optional[datetime] = None
    related_meeting: Optional[str] = None


class AgendaUpdate(BaseModel):
    department: Optional[str] = None
    content: Optional[str] = None
    agenda_type: Optional[str] = None
    presenter_name: Optional[str] = None
    duration_minutes: Optional[int] = None
    order_num: Optional[int] = None
    purpose: Optional[str] = None
    due_date: Optional[datetime] = None
    related_meeting: Optional[str] = None


class AgendaOut(BaseModel):
    id: int
    meeting_id: int
    department: Optional[str]
    content: str
    agenda_type: Optional[str] = "draft"
    presenter_name: Optional[str] = None
    duration_minutes: Optional[int] = None
    order_num: Optional[int] = 0
    purpose: Optional[str] = None
    due_date: Optional[datetime] = None
    related_meeting: Optional[str] = None
    status: str
    confirmed_at: Optional[datetime]
    confirmed_by: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


# SttSegment
class SttSegmentOut(BaseModel):
    id: int
    session_id: int
    speaker_label: str
    speaker_user_id: Optional[int] = None
    speaker_name: Optional[str] = None
    content: str
    start_sec: float
    end_sec: float
    confidence: Optional[float] = None
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
    element_scores: Optional[Any] = None
    principles: Optional[Any] = None
    missing_elements: Optional[Any] = None
    submitted_at: Optional[datetime]
    approved_at: Optional[datetime]
    review_comment: Optional[str] = None
    created_at: datetime
    presenter: Optional[UserOut] = None

    model_config = {"from_attributes": True}


class ReportStatusUpdate(BaseModel):
    status: str  # approved | rejected | submitted | draft
    comment: Optional[str] = None  # 승인/반려 사유
    notify_teams: bool = False  # Teams 알림 전송 여부


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
    loop_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    password: Optional[str] = None
    location: Optional[str] = None   # 장소 (TPO)


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    password: Optional[str] = None
    location: Optional[str] = None   # 장소 (TPO)


class SessionOut(BaseModel):
    id: int
    meeting_id: int
    loop_id: Optional[int]
    session_number: int
    title: str
    location: Optional[str]
    password: Optional[str]
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    status: str

    model_config = {"from_attributes": True}


LoopOut.model_rebuild()


# Minutes
class MinutesSave(BaseModel):
    content_summary: str


class MinutesOut(BaseModel):
    id: int
    session_id: int
    recorder_id: Optional[int] = None
    content_raw: Optional[str] = None
    content_summary: Optional[str] = None
    # 5대 필수요소 (DB 컬럼 미존재 → 추후 마이그레이션 시 활성화)
    attendees_json: Optional[Any] = None
    decisions_json: Optional[Any] = None
    action_items_json: Optional[Any] = None
    tbd_items_json: Optional[Any] = None
    next_meeting_note: Optional[str] = None
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


class TacitKnowledgeMeetingOut(BaseModel):
    id: int
    meeting_id: int
    category: str
    title: str
    content: str
    version: int
    status: str
    loop_number: Optional[int] = None
    source_event_ids: Optional[Any] = None
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


class ReportStatusRequest(BaseModel):
    meeting_id: int
    user_role: str


class CardNewsPlanRequest(BaseModel):
    meeting_id: int
    session_ids: List[int]
    chat_history: Optional[List[dict]] = []
    thread_id: Optional[str] = None  # 없으면 백엔드에서 생성
    target_audience: Optional[str] = "staff"  # c_level | executive | staff | external
    # 활용할 소스 유형 (없으면 전체)
    include_minutes: Optional[bool] = True
    include_reports: Optional[bool] = True
    include_agendas: Optional[bool] = True
    include_decisions: Optional[bool] = True
    # 스타일 힌트
    slide_count: Optional[int] = None
    first_card: Optional[str] = None        # conclusion | issue_bg | hook | visual_hook
    tone: Optional[str] = None              # concise | logical | friendly | emotional
    visual_style: Optional[str] = None      # simple_graph | roadmap | infographic | image_brand
    include_cta: Optional[bool] = True
    include_source_date: Optional[bool] = True
    include_brand_logo: Optional[bool] = False
    custom_request: Optional[str] = None


class CardNewsExtractRequest(BaseModel):
    meeting_id: int
    chat_history: List[dict]
    available_sessions: List[dict]  # [{id, session_number, title}]


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


# ── Todo ──────────────────────────────────────────────────────────────────────
class TodoCreate(BaseModel):
    content: str
    assignee_name: Optional[str] = None
    assignee_dept: Optional[str] = None
    priority: Optional[str] = "normal"
    status: Optional[str] = "pending"
    source_type: Optional[str] = None
    due_date: Optional[datetime] = None
    mg_id: Optional[str] = None  # Neo4j MeetingGroup ID (그래프 동기화용)


class TodoOut(BaseModel):
    id: int
    meeting_id: int
    agenda_id: Optional[int] = None
    content: str
    assignee_name: Optional[str] = None
    assignee_dept: Optional[str] = None
    priority: str
    status: str
    source_type: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

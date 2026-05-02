from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, JSON, Float
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    employee_id = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    department = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting_members = relationship("MeetingMember", back_populates="user")
    todos = relationship("Todo", back_populates="user")
    reports = relationship("Report", back_populates="presenter")
    notifications = relationship("Notification", back_populates="user")


class Meeting(Base):
    __tablename__ = "meetings"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    purpose = Column(Text)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    status = Column(String, default="active")  # active | ended
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("MeetingMember", back_populates="meeting")
    agendas = relationship("Agenda", back_populates="meeting")
    todos = relationship("Todo", back_populates="meeting")
    reports = relationship("Report", back_populates="meeting")
    loops = relationship("MeetingLoop", back_populates="meeting", order_by="MeetingLoop.loop_number")
    sessions = relationship("MeetingSession", back_populates="meeting")
    card_news = relationship("CardNews", back_populates="meeting")


class MeetingMember(Base):
    __tablename__ = "meeting_members"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String, nullable=False)  # admin | presenter

    meeting = relationship("Meeting", back_populates="members")
    user = relationship("User", back_populates="meeting_members")


class Agenda(Base):
    __tablename__ = "agendas"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    department = Column(String)
    content = Column(Text, nullable=False)
    agenda_type = Column(String, default="draft")  # draft | scheduled | closed
    presenter_name = Column(String, nullable=True)       # 안건 담당자 이름
    duration_minutes = Column(Integer, nullable=True)    # 소요 시간 (분)
    order_num = Column(Integer, default=0)               # 안건 순서
    purpose = Column(Text, nullable=True)            # 목적
    due_date = Column(DateTime, nullable=True)        # 마감일
    related_meeting = Column(String, nullable=True)   # 주관 회의체 맵핑
    status = Column(String, default="draft")  # draft | confirmed | tbd
    confirmed_at = Column(DateTime)
    confirmed_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="agendas")
    todos = relationship("Todo", back_populates="agenda")


class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    agenda_id = Column(Integer, ForeignKey("agendas.id"), nullable=True)
    content = Column(Text, nullable=False)               # What
    assignee_name = Column(String, nullable=True)        # Who (담당자 이름)
    assignee_dept = Column(String, nullable=True)        # Who (담당 부서)
    how = Column(Text, nullable=True)                    # How (산출물 형태)
    why = Column(Text, nullable=True)                    # Why (목적/연결된 의사결정)
    priority = Column(String, default="normal")          # urgent_important | important | urgent | low
    tags = Column(JSON, nullable=True)                   # [승인필요, 타부서협조, 외부의존, 보고연결]
    due_date = Column(DateTime, nullable=True)           # When
    status = Column(String, default="pending")           # pending | in_progress | at_risk | done | on_hold
    source_type = Column(String, default="report")       # report | meeting_minutes
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="todos")
    user = relationship("User", back_populates="todos")
    agenda = relationship("Agenda", back_populates="todos")


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    presenter_id = Column(Integer, ForeignKey("users.id"))
    file_path = Column(String)
    file_name = Column(String)
    status = Column(String, default="draft")  # draft | submitted | approved | rejected
    score = Column(Float, nullable=True)
    feedback = Column(JSON, nullable=True)
    element_scores = Column(JSON, nullable=True)   # 12대 필수요소별 점수
    principles = Column(JSON, nullable=True)        # 5대 핵심 원칙 체크
    missing_elements = Column(JSON, nullable=True)  # 누락 요소 목록
    submitted_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    review_comment = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="reports")
    presenter = relationship("User", back_populates="reports")


class MeetingLoop(Base):
    __tablename__ = "meeting_loops"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    loop_number = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="loops")
    sessions = relationship("MeetingSession", back_populates="loop", order_by="MeetingSession.session_number")


class MeetingSession(Base):
    __tablename__ = "meeting_sessions"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    loop_id = Column(Integer, ForeignKey("meeting_loops.id"), nullable=True)
    session_number = Column(Integer, default=1)
    title = Column(String)
    location = Column(String, nullable=True)       # 장소 (TPO)
    password = Column(String, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    status = Column(String, default="scheduled")  # scheduled | ongoing | ended

    meeting = relationship("Meeting", back_populates="sessions")
    loop = relationship("MeetingLoop", back_populates="sessions")
    minutes = relationship("Minutes", back_populates="session", uselist=False)


class Minutes(Base):
    __tablename__ = "minutes"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("meeting_sessions.id"))
    recorder_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 작성자
    content_raw = Column(Text)           # 원본 녹취
    content_summary = Column(Text)       # AI 마크다운 요약
    # 5대 필수요소 구조적 저장
    attendees_json = Column(JSON, nullable=True)    # Joiner: [{name, dept, role, present, note}]
    decisions_json = Column(JSON, nullable=True)    # Done: [{content, decided_by, agenda_ref}]
    action_items_json = Column(JSON, nullable=True) # WILL DO: [{content, assignee, due_date, status}]
    tbd_items_json = Column(JSON, nullable=True)    # TBD: [{content, reason}]
    next_meeting_note = Column(Text, nullable=True) # 차기 회의 예고
    generated_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("MeetingSession", back_populates="minutes")


class CardNews(Base):
    __tablename__ = "card_news"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    session_ids = Column(JSON)
    title = Column(String)
    file_path = Column(String, nullable=True)
    content = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="card_news")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String)
    message = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    ref_id = Column(Integer, nullable=True)
    ref_type = Column(String, nullable=True)

    user = relationship("User", back_populates="notifications")


class ChatMessage(Base):
    """AI 에이전트와의 대화 기록 (페이지별·유저별·컨텍스트별 저장)"""
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # context_type: agenda | prepare | todo | cardnews | room
    context_type = Column(String, nullable=False)
    # context_id: meeting_id 또는 session_id (context_type='room'이면 session_id)
    context_id = Column(Integer, nullable=False)
    role = Column(String, nullable=False)    # user | agent
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)



class TacitEvent(Base):
    __tablename__ = "tacit_events"
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=True)
    meeting_type = Column(String, nullable=True)
    payload = Column(JSON)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TacitKnowledgeGlobal(Base):
    __tablename__ = "tacit_knowledge_global"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String)
    title = Column(String)
    content = Column(Text)
    version = Column(Integer, default=1)
    status = Column(String, default="active")  # active | draft | archived
    source_event_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TacitKnowledgeMeeting(Base):
    __tablename__ = "tacit_knowledge_meeting"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    category = Column(String)
    title = Column(String)
    content = Column(Text)
    version = Column(Integer, default=1)
    status = Column(String, default="active")
    loop_number = Column(Integer, nullable=True)  # 마지막 업데이트 루프 번호
    source_event_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TacitProposal(Base):
    __tablename__ = "tacit_proposals"
    id = Column(Integer, primary_key=True, index=True)
    scope = Column(String)  # global | meeting
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=True)
    target_id = Column(Integer, nullable=True)
    category = Column(String)
    title = Column(String)
    proposed_content = Column(Text)
    diff_summary = Column(Text, nullable=True)
    evidence_summary = Column(Text, nullable=True)
    source_event_ids = Column(JSON, nullable=True)
    status = Column(String, default="pending")  # pending | accepted | rejected | edited_and_accepted
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    final_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MeetingStatusCache(Base):
    """혜안이 생성한 회의체 현황 요약 캐시 (회의체당 1건 유지)"""
    __tablename__ = "meeting_status_cache"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)


class ActivityMemory(Base):
    """회의체별 활동 기록 단일 문서 — 에이전트 호출 시 자동 append, 관리자 편집 가능"""
    __tablename__ = "activity_memory"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), unique=True, nullable=False)
    content = Column(Text, default="")          # 마크다운 전체 문서
    version = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String, default="system")  # "system" | "manual"

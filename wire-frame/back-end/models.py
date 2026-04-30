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
    status = Column(String, default="draft")  # draft | confirmed
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
    content = Column(Text, nullable=False)
    due_date = Column(DateTime, nullable=True)
    status = Column(String, default="pending")  # pending | done | delayed
    source_type = Column(String, default="report")  # report | meeting_minutes
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
    submitted_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
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
    content_raw = Column(Text)
    content_summary = Column(Text)
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

"""
seed.py — PostgreSQL + Neo4j 테스트 데이터 시드 스크립트

실행: cd backend/ai && python3 seed.py
"""
import os, sys, asyncio, json
from datetime import datetime, timedelta
from dotenv import load_dotenv

_base = os.path.dirname(__file__)
load_dotenv(os.path.join(_base, "..", "..", ".env"), override=True)

import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import models
from database import engine
from neo4j_sync import (
    sync_user, sync_meeting, sync_session, sync_agenda,
    sync_meeting_member, sync_minutes, init_vector_index,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# ── 날짜 헬퍼 ────────────────────────────────────────────────────────────────
def ago(days=0, hours=0):
    return datetime.now() - timedelta(days=days, hours=hours)

def later(days=0, hours=0):
    return datetime.now() + timedelta(days=days, hours=hours)

def pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 : PostgreSQL 기존 더미 데이터 정리 후 시드 삽입
# ─────────────────────────────────────────────────────────────────────────────

def seed_postgres():
    models.Base.metadata.create_all(bind=engine, checkfirst=True)
    db = SessionLocal()
    try:
        # ── 기존 더미 데이터 삭제 (cascade 순서) ─────────────────────────
        for tbl in [
            "hitl_reviews","token_usage_logs","agent_logs","chat_messages",
            "notifications","minutes","stt_segments","report_criteria",
            "reports","agendas","meeting_relations","meeting_sessions",
            "meeting_members","meetings","users",
        ]:
            db.execute(text(f"DELETE FROM {tbl}"))
        db.execute(text("ALTER SEQUENCE users_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE meetings_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE meeting_members_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE meeting_sessions_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE agendas_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE reports_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE minutes_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE stt_segments_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE notifications_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE chat_messages_id_seq RESTART WITH 1"))
        db.execute(text("ALTER SEQUENCE hitl_reviews_id_seq RESTART WITH 1"))
        db.commit()
        print("✓ 기존 데이터 삭제 완료")

        # ─────────────────────────────────────────────────────────────────
        # USERS (7명)
        # ─────────────────────────────────────────────────────────────────
        USERS = [
            dict(name="관리자",   email="admin@workmaite.com",    password_hash=pw("workmaite123"),
                 company="워크메이트", department="경영진",     position="대표이사"),
            dict(name="김민준",   email="minjun.kim@workmaite.com", password_hash=pw("workmaite123"),
                 company="워크메이트", department="전략기획팀", position="팀장"),
            dict(name="이서연",   email="seoyeon.lee@workmaite.com", password_hash=pw("workmaite123"),
                 company="워크메이트", department="전략기획팀", position="선임연구원"),
            dict(name="박준혁",   email="junhyuk.park@workmaite.com", password_hash=pw("workmaite123"),
                 company="워크메이트", department="AI개발팀",  position="팀장"),
            dict(name="최지은",   email="jieun.choi@workmaite.com", password_hash=pw("workmaite123"),
                 company="워크메이트", department="AI개발팀",  position="주임연구원"),
            dict(name="정하윤",   email="hayun.jung@workmaite.com", password_hash=pw("workmaite123"),
                 company="워크메이트", department="마케팅팀",  position="팀장"),
            dict(name="한도윤",   email="doyun.han@workmaite.com", password_hash=pw("workmaite123"),
                 company="워크메이트", department="마케팅팀",  position="사원"),
        ]
        users = []
        for u in USERS:
            obj = models.User(
                name=u["name"], email=u["email"],
                password_hash=u["password_hash"],
                company=u["company"], department=u["department"], position=u["position"],
                created_at=ago(days=60),
            )
            db.add(obj)
            db.flush()
            users.append(obj)
        db.commit()
        U = {u.name: u for u in users}
        print(f"✓ 사용자 {len(users)}명 생성")

        # ─────────────────────────────────────────────────────────────────
        # MEETINGS (4개)
        # ─────────────────────────────────────────────────────────────────
        meeting_data = [
            dict(title="AI 제품 전략 회의",
                 purpose="AI 제품 로드맵 수립 및 경쟁력 강화 전략 논의",
                 guidelines="매주 월요일 오전 10시. 전략 목표 재확인 및 우선순위 조정. 결정 사항은 반드시 문서화.",
                 priority="HIGH", type="WEEKLY", status="ACTIVE",
                 start_date=ago(days=90), end_date=later(days=180),
                 created_by=U["김민준"].id),
            dict(title="마케팅 브랜드 전략 회의",
                 purpose="브랜드 포지셔닝 강화 및 마케팅 캠페인 성과 리뷰",
                 guidelines="매월 첫째 주 목요일. 데이터 기반 의사결정 원칙. KPI 달성 현황 공유 필수.",
                 priority="NORMAL", type="MONTHLY", status="ACTIVE",
                 start_date=ago(days=60), end_date=later(days=300),
                 created_by=U["정하윤"].id),
            dict(title="전사 경영 전략 회의",
                 purpose="분기별 사업 실적 점검 및 중장기 전략 방향 수립",
                 guidelines="분기별 개최. CEO 주재. 각 팀장 필참. 대외비 자료 포함.",
                 priority="URGENT", type="QUARTERLY", status="ACTIVE",
                 start_date=ago(days=120), end_date=later(days=240),
                 created_by=U["관리자"].id),
            dict(title="AI 개발팀 주간 스프린트",
                 purpose="AI 모델 개발 진척 공유 및 기술 이슈 해결",
                 guidelines="매주 금요일 오후 3시. 스프린트 목표 달성 여부 체크. 기술 부채 관리.",
                 priority="NORMAL", type="WEEKLY", status="ACTIVE",
                 start_date=ago(days=45), end_date=later(days=180),
                 created_by=U["박준혁"].id),
        ]
        meetings = []
        for m in meeting_data:
            obj = models.Meeting(**m, created_at=ago(days=60))
            db.add(obj)
            db.flush()
            meetings.append(obj)
        db.commit()
        M = {m.title: m for m in meetings}
        print(f"✓ 회의체 {len(meetings)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # MEETING MEMBERS
        # ─────────────────────────────────────────────────────────────────
        members_data = [
            # AI 전략 회의
            (M["AI 제품 전략 회의"].id,    U["김민준"].id,  "SECRETARY"),
            (M["AI 제품 전략 회의"].id,    U["박준혁"].id,  "MEMBER"),
            (M["AI 제품 전략 회의"].id,    U["최지은"].id,  "MEMBER"),
            (M["AI 제품 전략 회의"].id,    U["관리자"].id,  "MEMBER"),
            # 마케팅 회의
            (M["마케팅 브랜드 전략 회의"].id, U["정하윤"].id, "SECRETARY"),
            (M["마케팅 브랜드 전략 회의"].id, U["이서연"].id, "MEMBER"),
            (M["마케팅 브랜드 전략 회의"].id, U["한도윤"].id, "MEMBER"),
            # 전사 경영
            (M["전사 경영 전략 회의"].id,  U["관리자"].id,  "SECRETARY"),
            (M["전사 경영 전략 회의"].id,  U["김민준"].id,  "MEMBER"),
            (M["전사 경영 전략 회의"].id,  U["정하윤"].id,  "MEMBER"),
            (M["전사 경영 전략 회의"].id,  U["이서연"].id,  "MEMBER"),
            # 스프린트
            (M["AI 개발팀 주간 스프린트"].id, U["박준혁"].id, "SECRETARY"),
            (M["AI 개발팀 주간 스프린트"].id, U["최지은"].id, "MEMBER"),
            (M["AI 개발팀 주간 스프린트"].id, U["김민준"].id, "MEMBER"),
        ]
        for meeting_id, user_id, role in members_data:
            db.add(models.MeetingMember(
                meeting_id=meeting_id, user_id=user_id, role=role,
                created_at=ago(days=59),
            ))
        db.commit()
        print(f"✓ 회의 멤버 {len(members_data)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # MEETING RELATIONS
        # ─────────────────────────────────────────────────────────────────
        db.add(models.MeetingRelation(
            source_meeting_id=M["AI 제품 전략 회의"].id,
            target_meeting_id=M["AI 개발팀 주간 스프린트"].id,
            relation_type="PARENT_OF",
            created_by=U["관리자"].id,
            created_at=ago(days=55),
        ))
        db.commit()
        print("✓ 회의체 관계 생성")

        # ─────────────────────────────────────────────────────────────────
        # MEETING SESSIONS
        # ─────────────────────────────────────────────────────────────────
        sessions_data = [
            # AI 전략 — 4세션
            dict(meeting_id=M["AI 제품 전략 회의"].id,
                 title="1차 정기회의 — Q1 리뷰", location="본사 2층 회의실 A",
                 scheduled_at=ago(days=28), started_at=ago(days=28, hours=-0.5),
                 ended_at=ago(days=28, hours=-2.5), status="ENDED"),
            dict(meeting_id=M["AI 제품 전략 회의"].id,
                 title="2차 정기회의 — 경쟁사 분석", location="본사 2층 회의실 A",
                 scheduled_at=ago(days=14), started_at=ago(days=14, hours=-0.5),
                 ended_at=ago(days=14, hours=-2), status="ENDED"),
            dict(meeting_id=M["AI 제품 전략 회의"].id,
                 title="3차 정기회의 — 파트너십 논의", location="본사 2층 회의실 A",
                 scheduled_at=ago(days=0, hours=2),
                 started_at=ago(days=0, hours=2), ended_at=None, status="ONGOING"),
            dict(meeting_id=M["AI 제품 전략 회의"].id,
                 title="4차 정기회의 — 하반기 로드맵", location="본사 2층 회의실 A",
                 scheduled_at=later(days=7), started_at=None, ended_at=None, status="SCHEDULED"),
            # 마케팅 — 2세션
            dict(meeting_id=M["마케팅 브랜드 전략 회의"].id,
                 title="5월 정기 브랜드 전략 회의", location="마케팅팀 회의실",
                 scheduled_at=ago(days=21), started_at=ago(days=21, hours=-1),
                 ended_at=ago(days=21, hours=-3), status="ENDED"),
            dict(meeting_id=M["마케팅 브랜드 전략 회의"].id,
                 title="6월 정기 브랜드 전략 회의", location="마케팅팀 회의실",
                 scheduled_at=later(days=10), started_at=None, ended_at=None, status="SCHEDULED"),
            # 전사 경영 — 2세션
            dict(meeting_id=M["전사 경영 전략 회의"].id,
                 title="2024 Q1 경영 전략 회의", location="임원실 대회의실",
                 scheduled_at=ago(days=55), started_at=ago(days=55, hours=-1),
                 ended_at=ago(days=55, hours=-4), status="ENDED"),
            dict(meeting_id=M["전사 경영 전략 회의"].id,
                 title="2024 Q2 경영 전략 회의", location="임원실 대회의실",
                 scheduled_at=later(days=35), started_at=None, ended_at=None, status="SCHEDULED"),
            # 스프린트 — 3세션
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id,
                 title="스프린트 #8 리뷰 & 레트로", location="개발팀 회의실",
                 scheduled_at=ago(days=7), started_at=ago(days=7, hours=-1),
                 ended_at=ago(days=7, hours=-2.5), status="ENDED"),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id,
                 title="스프린트 #9 플래닝", location="개발팀 회의실",
                 scheduled_at=ago(days=0, hours=4),
                 started_at=ago(days=0, hours=4), ended_at=ago(days=0, hours=2),
                 status="ENDED"),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id,
                 title="스프린트 #10 킥오프", location="개발팀 회의실",
                 scheduled_at=later(days=7), started_at=None, ended_at=None, status="SCHEDULED"),
        ]
        sessions = []
        for s in sessions_data:
            obj = models.MeetingSession(**s, created_at=ago(days=60))
            db.add(obj)
            db.flush()
            sessions.append(obj)
        db.commit()
        print(f"✓ 세션 {len(sessions)}개 생성")
        # 이름 → 객체 맵
        S = {s.title: s for s in sessions}

        # ─────────────────────────────────────────────────────────────────
        # AGENDAS (21개)
        # ─────────────────────────────────────────────────────────────────
        agendas_data = [
            # AI 전략 회의
            dict(meeting_id=M["AI 제품 전략 회의"].id, assignee_id=U["김민준"].id,
                 title="Q2 AI 제품 로드맵 검토 및 우선순위 조정",
                 content="GPT-4o 기반 에이전트 확장, RAG 파이프라인 고도화, 멀티모달 지원 여부를 논의한다. 기존 로드맵 대비 변경사항 정리 필요.",
                 order_index=1, status="DONE"),
            dict(meeting_id=M["AI 제품 전략 회의"].id, assignee_id=U["박준혁"].id,
                 title="경쟁사 AI 제품 기능 분석 결과 발표",
                 content="OpenAI, Anthropic, Google의 최신 기능 출시 현황 및 시장 반응 정리. 우리 제품 대비 GAP 분석 포함.",
                 order_index=2, status="DONE"),
            dict(meeting_id=M["AI 제품 전략 회의"].id, assignee_id=U["김민준"].id,
                 title="전략적 파트너십 후보 기업 검토",
                 content="데이터 공급사 3곳, 기술 파트너 2곳 대상 협업 가능성 검토. NDA 진행 여부 결정 필요.",
                 order_index=3, status="CONFIRMED"),
            dict(meeting_id=M["AI 제품 전략 회의"].id, assignee_id=U["관리자"].id,
                 title="2024 하반기 AI 투자 예산 배분 계획",
                 content="인프라 확장, 인력 채용, 외부 API 비용을 포함한 총 예산안 논의. CFO 승인 후 확정.",
                 order_index=4, status="ON_HOLD"),
            dict(meeting_id=M["AI 제품 전략 회의"].id, assignee_id=U["박준혁"].id,
                 title="차세대 멀티모달 AI 모델 도입 가능성 검토",
                 content="Vision + Text 통합 모델 도입 시 필요한 인프라 요구사항, 예상 비용, 기대 효과 분석.",
                 order_index=5, status="ON_HOLD"),
            # 마케팅
            dict(meeting_id=M["마케팅 브랜드 전략 회의"].id, assignee_id=U["정하윤"].id,
                 title="5월 브랜드 캠페인 성과 분석 및 KPI 리뷰",
                 content="인스타그램 도달률 32% 상승, 전환율 1.8%. 목표 대비 110% 달성. 주요 성공 요인 분석.",
                 order_index=1, status="DONE"),
            dict(meeting_id=M["마케팅 브랜드 전략 회의"].id, assignee_id=U["한도윤"].id,
                 title="SNS 콘텐츠 전략 방향 수정 — 숏폼 강화",
                 content="릴스·쇼츠 중심 콘텐츠로 전환. 월 20편 제작 계획. 인플루언서 협업 예산 배정.",
                 order_index=2, status="CONFIRMED"),
            dict(meeting_id=M["마케팅 브랜드 전략 회의"].id, assignee_id=U["정하윤"].id,
                 title="신제품 런칭 마케팅 플랜 수립",
                 content="7월 런칭 예정 신제품 대상 사전 버즈 마케팅, 런칭 이벤트, 미디어 커버리지 전략 수립.",
                 order_index=3, status="ON_HOLD"),
            dict(meeting_id=M["마케팅 브랜드 전략 회의"].id, assignee_id=U["이서연"].id,
                 title="경쟁사 마케팅 전략 벤치마크 리포트",
                 content="국내외 5개 경쟁사 마케팅 채널, 예산 추정, 크리에이티브 방향성 분석.",
                 order_index=4, status="ON_HOLD"),
            # 전사 경영
            dict(meeting_id=M["전사 경영 전략 회의"].id, assignee_id=U["관리자"].id,
                 title="2024 Q1 사업 실적 및 KPI 달성 보고",
                 content="매출 목표 대비 94% 달성. 영업이익 12% 개선. 고객 이탈률 3.2% 감소. 상세 데이터 첨부.",
                 order_index=1, status="DONE"),
            dict(meeting_id=M["전사 경영 전략 회의"].id, assignee_id=U["관리자"].id,
                 title="2024 Q2 사업 목표 및 팀별 OKR 설정",
                 content="전사 매출 목표 15% 성장. 팀별 OKR 초안 제출 후 조율. 분기 말 리뷰 일정 확정.",
                 order_index=2, status="DONE"),
            dict(meeting_id=M["전사 경영 전략 회의"].id, assignee_id=U["김민준"].id,
                 title="R&D 팀 확장 및 조직 구조 개편안 논의",
                 content="AI 개발팀 인원 2명 추가 채용. 전략기획 기능 강화. 보고 체계 일부 변경.",
                 order_index=3, status="CONFIRMED"),
            dict(meeting_id=M["전사 경영 전략 회의"].id, assignee_id=U["관리자"].id,
                 title="Series B 투자 유치 전략 논의",
                 content="Q3 목표 투자 유치. 주요 VC 리스트업 완료. IR 자료 작성 일정 및 담당자 배정.",
                 order_index=4, status="ON_HOLD"),
            dict(meeting_id=M["전사 경영 전략 회의"].id, assignee_id=U["이서연"].id,
                 title="ESG 경영 도입 및 지속가능성 보고서 방향",
                 content="2024년 ESG 공시 의무화 대응. 탄소 발자국 측정, 사회적 가치 지표 설정.",
                 order_index=5, status="ON_HOLD"),
            # 스프린트
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id, assignee_id=U["박준혁"].id,
                 title="스프린트 #8 회고 — 완료 항목 리뷰",
                 content="완료 5/7. 지연 원인: 외부 API 장애 2건. 다음 스프린트 버퍼 시간 추가 편성.",
                 order_index=1, status="DONE"),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id, assignee_id=U["박준혁"].id,
                 title="LLM 추론 속도 30% 개선 — vLLM 도입 검토",
                 content="vLLM PagedAttention 기법 적용 시 처리량 2.8배 향상 가능. GPU 메모리 사용량 분석 완료.",
                 order_index=2, status="DONE"),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id, assignee_id=U["최지은"].id,
                 title="API 응답 속도 개선 — 캐싱 레이어 도입",
                 content="Redis 기반 응답 캐싱 구현. 반복 쿼리 90% 히트율 목표. 캐시 무효화 전략 설계 중.",
                 order_index=3, status="CONFIRMED"),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id, assignee_id=U["최지은"].id,
                 title="AI 파이프라인 모듈화 리팩토링",
                 content="현재 단일 파이프라인을 전처리/추론/후처리 모듈로 분리. 테스트 커버리지 80% 목표.",
                 order_index=4, status="CONFIRMED"),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id, assignee_id=U["박준혁"].id,
                 title="코드 리뷰 프로세스 표준화",
                 content="PR 템플릿 작성, 리뷰어 자동 배정 규칙 설정, 머지 전 CI 자동화 체크리스트 정비.",
                 order_index=5, status="ON_HOLD"),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id, assignee_id=U["최지은"].id,
                 title="벡터 DB 마이그레이션 — Pinecone → Qdrant",
                 content="비용 절감 및 온프레미스 운영 가능성 검토. 마이그레이션 스크립트 작성 및 데이터 검증.",
                 order_index=6, status="ON_HOLD"),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id, assignee_id=U["박준혁"].id,
                 title="모델 평가 자동화 파이프라인 구축",
                 content="RAGAS 기반 RAG 성능 평가 자동화. 주간 성능 리포트 자동 생성 시스템 구축.",
                 order_index=7, status="ON_HOLD"),
        ]
        agendas = []
        for a in agendas_data:
            obj = models.Agenda(**a, created_at=ago(days=30))
            db.add(obj)
            db.flush()
            agendas.append(obj)
        db.commit()
        print(f"✓ 안건 {len(agendas)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # REPORT CRITERIA (AI 전략 회의 — 3개)
        # ─────────────────────────────────────────────────────────────────
        criteria_data = [
            dict(meeting_id=M["AI 제품 전략 회의"].id, name="논리적 구성 및 명확성",
                 description="보고서의 목차 구성, 주장의 논리적 흐름, 결론의 명확성 평가",
                 max_score=30.0, weight=1.0, layer_number=1),
            dict(meeting_id=M["AI 제품 전략 회의"].id, name="데이터 근거 충실도",
                 description="제시된 주장에 대한 정량적 데이터, 출처 명시, 신뢰성 평가",
                 max_score=40.0, weight=2.0, layer_number=2),
            dict(meeting_id=M["AI 제품 전략 회의"].id, name="실행 가능성 및 구체성",
                 description="제안된 액션 아이템의 현실적 실행 가능성, 일정·담당자·예산 명시 여부",
                 max_score=30.0, weight=1.5, layer_number=3),
            dict(meeting_id=M["전사 경영 전략 회의"].id, name="전략적 정합성",
                 description="회사 전략 방향과의 일치 여부 및 중장기 목표 기여도 평가",
                 max_score=50.0, weight=2.5, layer_number=1),
            dict(meeting_id=M["전사 경영 전략 회의"].id, name="재무적 타당성",
                 description="ROI 분석, 비용-편익 검토, 리스크 요인 명시 여부",
                 max_score=50.0, weight=2.0, layer_number=2),
        ]
        for c in criteria_data:
            db.add(models.ReportCriteria(**c, created_at=ago(days=60)))
        db.commit()
        print(f"✓ 평가 기준 {len(criteria_data)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # REPORTS (6개)
        # ─────────────────────────────────────────────────────────────────
        reports_data = [
            dict(meeting_id=M["AI 제품 전략 회의"].id,
                 session_id=S["1차 정기회의 — Q1 리뷰"].id,
                 uploader_id=U["김민준"].id,
                 version=2, file_type="REPORT",
                 file_name="2024_Q1_AI_Strategy_Review.pdf",
                 file_path="uploads/2024_Q1_AI_Strategy_Review.pdf",
                 status="APPROVED", score=87.5,
                 layer1_result=json.dumps({"score": 28, "comments": "논리 구성 우수, 결론 명확"}),
                 layer2_result=json.dumps({"score": 36, "comments": "데이터 근거 충분, 출처 명시 완료"}),
                 layer3_result=json.dumps({"score": 25, "comments": "실행 일정 구체적, 담당자 명시됨"}),
                 feedback="전반적으로 높은 완성도. 경쟁사 데이터 출처 보완 권장.",
                 missing_elements=json.dumps(["경쟁사 데이터 최신화 필요"])),
            dict(meeting_id=M["AI 제품 전략 회의"].id,
                 session_id=S["2차 정기회의 — 경쟁사 분석"].id,
                 uploader_id=U["박준혁"].id,
                 version=1, file_type="PRESENTATION",
                 file_name="AI_Competitor_Analysis_May2024.pptx",
                 file_path="uploads/AI_Competitor_Analysis_May2024.pptx",
                 status="REVIEWING", score=72.0,
                 layer1_result=json.dumps({"score": 22, "comments": "구성은 양호하나 일부 슬라이드 과부하"}),
                 layer2_result=json.dumps({"score": 30, "comments": "주요 경쟁사 데이터 포함, 일부 미반영"}),
                 layer3_result=json.dumps({"score": 20, "comments": "대응 전략 방향 제시 불충분"}),
                 feedback="경쟁사 분석 자체는 좋으나 우리 제품 대비 GAP 분석과 대응 전략 보완 필요.",
                 missing_elements=json.dumps(["GAP 분석 추가", "대응 전략 구체화"])),
            dict(meeting_id=M["마케팅 브랜드 전략 회의"].id,
                 session_id=S["5월 정기 브랜드 전략 회의"].id,
                 uploader_id=U["정하윤"].id,
                 version=1, file_type="REPORT",
                 file_name="May2024_Brand_Campaign_Results.pdf",
                 file_path="uploads/May2024_Brand_Campaign_Results.pdf",
                 status="SUBMITTED", score=None,
                 feedback=None, missing_elements=None),
            dict(meeting_id=M["전사 경영 전략 회의"].id,
                 session_id=S["2024 Q1 경영 전략 회의"].id,
                 uploader_id=U["관리자"].id,
                 version=1, file_type="REPORT",
                 file_name="2024_Q1_Business_Performance_Report.pdf",
                 file_path="uploads/2024_Q1_Business_Performance_Report.pdf",
                 status="APPROVED", score=91.0,
                 layer1_result=json.dumps({"score": 28, "comments": "보고 구조 매우 명확"}),
                 layer2_result=json.dumps({"score": 38, "comments": "재무 데이터 완비"}),
                 layer3_result=json.dumps({"score": 27, "comments": "후속 조치 계획 구체적"}),
                 feedback="분기 보고서 최상위 수준. 차기 보고서 작성 기준으로 활용 권장.",
                 missing_elements=json.dumps([])),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id,
                 session_id=S["스프린트 #8 리뷰 & 레트로"].id,
                 uploader_id=U["박준혁"].id,
                 version=1, file_type="MINUTES",
                 file_name="Sprint8_Review_Tech_Retrospective.docx",
                 file_path="uploads/Sprint8_Review_Tech_Retrospective.docx",
                 status="REVIEWING", score=65.0,
                 layer1_result=json.dumps({"score": 20, "comments": "일부 항목 구체성 부족"}),
                 feedback="기술 이슈 원인 분석 더 필요. 재발 방지 대책 보완.",
                 missing_elements=json.dumps(["근본 원인 분석", "재발 방지 계획"])),
            dict(meeting_id=M["AI 개발팀 주간 스프린트"].id,
                 session_id=S["스프린트 #9 플래닝"].id,
                 uploader_id=U["최지은"].id,
                 version=1, file_type="REPORT",
                 file_name="Sprint9_Planning_Tasks.pdf",
                 file_path="uploads/Sprint9_Planning_Tasks.pdf",
                 status="SUBMITTED", score=None,
                 feedback=None, missing_elements=None),
        ]
        rpts = []
        for r in reports_data:
            obj = models.Report(**r, created_at=ago(days=10))
            db.add(obj)
            db.flush()
            rpts.append(obj)
        db.commit()
        print(f"✓ 자료 {len(rpts)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # STT SEGMENTS (2개 세션 대화 기록)
        # ─────────────────────────────────────────────────────────────────
        s1 = S["1차 정기회의 — Q1 리뷰"]
        s9 = S["스프린트 #8 리뷰 & 레트로"]
        stt_data = [
            # AI 전략 1차 회의
            dict(session_id=s1.id, speaker_label="SPEAKER_00", speaker_user_id=U["김민준"].id,
                 content="안녕하세요, 1차 AI 전략 회의를 시작하겠습니다. 오늘은 Q1 리뷰와 함께 Q2 로드맵을 점검하겠습니다.",
                 start_sec=0.0, end_sec=8.5, confidence=0.97),
            dict(session_id=s1.id, speaker_label="SPEAKER_01", speaker_user_id=U["박준혁"].id,
                 content="네, 저희 팀에서 준비한 경쟁사 분석 자료 먼저 공유해도 될까요? GPT-4o 출시 이후 시장 변화가 상당합니다.",
                 start_sec=9.2, end_sec=17.8, confidence=0.95),
            dict(session_id=s1.id, speaker_label="SPEAKER_00", speaker_user_id=U["김민준"].id,
                 content="물론이죠. 박준혁 팀장님 발표 부탁드립니다. 특히 우리 제품 대비 GAP 분석 중심으로 설명해주세요.",
                 start_sec=18.3, end_sec=26.0, confidence=0.96),
            dict(session_id=s1.id, speaker_label="SPEAKER_01", speaker_user_id=U["박준혁"].id,
                 content="현재 가장 큰 차이점은 멀티모달 처리 능력입니다. 우리는 텍스트에 집중하고 있지만 경쟁사들은 이미 이미지, 음성까지 통합하고 있습니다.",
                 start_sec=27.1, end_sec=38.5, confidence=0.93),
            dict(session_id=s1.id, speaker_label="SPEAKER_02", speaker_user_id=U["최지은"].id,
                 content="기술적으로 멀티모달 추가가 가능한데, 현재 인프라 기준으로는 GPU 메모리가 부족합니다. 최소 A100 8장이 추가로 필요합니다.",
                 start_sec=39.0, end_sec=50.2, confidence=0.91),
            dict(session_id=s1.id, speaker_label="SPEAKER_03", speaker_user_id=U["관리자"].id,
                 content="예산 측면에서 확인해보겠습니다. 인프라 비용이 얼마나 필요한지 다음 회의 전까지 견적서 준비해주시면 좋겠습니다.",
                 start_sec=51.0, end_sec=61.5, confidence=0.94),
            dict(session_id=s1.id, speaker_label="SPEAKER_00", speaker_user_id=U["김민준"].id,
                 content="좋습니다. 그러면 멀티모달 도입은 Q3 목표로 하고, Q2에는 현재 LLM 성능 개선에 집중하는 걸로 잠정 결정하겠습니다.",
                 start_sec=62.2, end_sec=73.0, confidence=0.96),
            dict(session_id=s1.id, speaker_label="SPEAKER_01", speaker_user_id=U["박준혁"].id,
                 content="동의합니다. vLLM 도입으로 추론 속도를 30% 이상 개선할 수 있을 것 같습니다. 스프린트 팀과 협의해보겠습니다.",
                 start_sec=74.0, end_sec=83.7, confidence=0.95),
            # 스프린트 #8 회고
            dict(session_id=s9.id, speaker_label="SPEAKER_00", speaker_user_id=U["박준혁"].id,
                 content="이번 스프린트 완료율이 71%입니다. 예상보다 낮은데, 외부 API 장애가 주요 원인이었습니다.",
                 start_sec=0.0, end_sec=9.3, confidence=0.96),
            dict(session_id=s9.id, speaker_label="SPEAKER_01", speaker_user_id=U["최지은"].id,
                 content="OpenAI API가 3번 다운됐고, 총 4시간 정도 영향을 받았어요. 폴백 로직 없이 단일 의존성이 문제였습니다.",
                 start_sec=10.0, end_sec=20.8, confidence=0.94),
            dict(session_id=s9.id, speaker_label="SPEAKER_00", speaker_user_id=U["박준혁"].id,
                 content="그래서 이번 스프린트에 멀티 프로바이더 폴백 구현을 최우선으로 넣었습니다. OpenAI 실패 시 Anthropic으로 자동 전환됩니다.",
                 start_sec=21.5, end_sec=33.0, confidence=0.97),
            dict(session_id=s9.id, speaker_label="SPEAKER_02", speaker_user_id=U["김민준"].id,
                 content="좋은 개선이네요. Redis 캐싱 작업 진행 상황도 공유해주실 수 있나요?",
                 start_sec=34.0, end_sec=41.5, confidence=0.93),
            dict(session_id=s9.id, speaker_label="SPEAKER_01", speaker_user_id=U["최지은"].id,
                 content="현재 기본 구조는 잡았고, 캐시 무효화 전략이 남아있습니다. 다음 주 완료 예정이에요. TTL 기반으로 할지 이벤트 기반으로 할지 고민 중입니다.",
                 start_sec=42.0, end_sec=55.3, confidence=0.92),
            dict(session_id=s9.id, speaker_label="SPEAKER_00", speaker_user_id=U["박준혁"].id,
                 content="사용자별 컨텍스트가 다르니 이벤트 기반이 맞을 것 같아요. PR 올리면 같이 리뷰하겠습니다.",
                 start_sec=56.0, end_sec=65.2, confidence=0.95),
        ]
        for st in stt_data:
            db.add(models.SttSegment(**st, created_at=ago(days=8)))
        db.commit()
        print(f"✓ STT 세그먼트 {len(stt_data)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # MINUTES (4개)
        # ─────────────────────────────────────────────────────────────────
        minutes_data = [
            dict(session_id=S["1차 정기회의 — Q1 리뷰"].id,
                 recorder_id=U["이서연"].id,
                 content_raw="김민준: Q1 리뷰 시작합니다. 박준혁: 경쟁사 분석 공유합니다. GPT-4o 출시 후 시장 변화 큽니다. 최지은: 멀티모달 추가 시 GPU A100 8장 필요. 관리자: 견적서 준비 부탁드립니다. 김민준: Q2 LLM 성능 개선 집중, Q3 멀티모달 도입으로 결정.",
                 content_original="## 1차 AI 전략 회의 회의록\n\n**일시:** 2024-04-29 10:00~12:00\n**장소:** 본사 2층 회의실 A\n**참석:** 김민준, 박준혁, 최지은, 관리자\n\n### 주요 논의 사항\n1. Q1 성과 리뷰: 목표 대비 94% 달성\n2. 경쟁사 분석: GPT-4o 출시 후 멀티모달 격차 확인\n3. 인프라 현황: 멀티모달 추가 시 A100 GPU 8장 필요\n\n### 결정 사항\n- Q2: LLM 성능 개선 집중 (vLLM 도입)\n- Q3: 멀티모달 도입 검토 착수\n- 인프라 견적서 다음 회의 전 제출\n\n### 액션 아이템\n- 박준혁: vLLM 도입 스프린트 반영\n- 최지은: GPU 견적서 작성 (1주 내)\n- 김민준: 파트너십 후보 기업 1차 미팅 추진",
                 content_summary="AI 전략 1차 회의에서 Q1 실적(94% 달성)을 리뷰하고 경쟁사 대비 멀티모달 격차를 확인했습니다. Q2는 vLLM 기반 LLM 성능 개선에 집중하고, Q3에 멀티모달 도입을 검토하기로 결정했습니다. GPU 인프라 투자 견적 검토 예정입니다.",
                 status="CONFIRMED", generated_at=ago(days=27), updated_at=ago(days=26)),
            dict(session_id=S["2차 정기회의 — 경쟁사 분석"].id,
                 recorder_id=U["이서연"].id,
                 content_raw="박준혁: 경쟁사 심층 분석 발표. OpenAI Assistants API, Google Gemini Pro 비교. 최지은: RAG 파이프라인 자체 구현으로 차별화 가능. 김민준: 파트너십 3곳 우선 협의 결정.",
                 content_original="## 2차 AI 전략 회의 회의록\n\n**일시:** 2024-05-13 10:00~12:00\n\n### 주요 논의\n1. 경쟁사 심층 분석\n2. 차별화 전략 방향\n3. 파트너십 진행 현황\n\n### 결정 사항\n- RAG 파이프라인 자체 구현으로 차별화\n- 파트너십 후보 3개사 NDA 체결 진행\n- 다음 회의에 파트너십 계약서 초안 검토",
                 content_summary="경쟁사 대비 차별화 전략으로 자체 RAG 파이프라인 고도화를 결정했습니다. 전략적 파트너십 후보 3개사와 NDA 체결을 진행하기로 했습니다.",
                 status="CONFIRMED", generated_at=ago(days=13), updated_at=ago(days=12)),
            dict(session_id=S["2024 Q1 경영 전략 회의"].id,
                 recorder_id=U["이서연"].id,
                 content_raw="관리자: Q1 실적 94% 달성. 영업이익 12% 개선. 김민준: AI 제품 매출 목표 초과. 정하윤: 마케팅 ROI 개선. 이서연: ESG 경영 도입 필요성 제기.",
                 content_original="## 2024 Q1 전사 경영 전략 회의록\n\n**일시:** 2024-04-01\n\n### Q1 실적\n- 매출: 목표 대비 94% 달성\n- 영업이익: 전분기 대비 12% 개선\n- 고객 이탈률: 3.2% 감소\n\n### Q2 목표\n- 매출 15% 성장\n- 팀별 OKR 수립 완료\n\n### 중장기 과제\n- Series B 유치 준비 (Q3)\n- ESG 경영 도입 검토",
                 content_summary="Q1 실적은 매출 94% 달성, 영업이익 12% 개선의 양호한 성과를 기록했습니다. Q2 매출 15% 성장 목표 설정과 함께 Q3 Series B 투자 유치 준비를 시작하기로 했습니다.",
                 status="CONFIRMED", generated_at=ago(days=54), updated_at=ago(days=53)),
            dict(session_id=S["스프린트 #8 리뷰 & 레트로"].id,
                 recorder_id=U["최지은"].id,
                 content_raw="박준혁: 완료율 71%. 외부 API 장애 영향. 최지은: OpenAI API 3회 다운, 4시간 영향. 폴백 로직 필요. 박준혁: 이번 스프린트 멀티 프로바이더 폴백 구현 우선. 최지은: Redis 캐싱 다음 주 완료 예정.",
                 content_original="## 스프린트 #8 리뷰 & 레트로\n\n**일시:** 2024-05-20\n\n### 완료 항목 (5/7)\n- LLM 성능 최적화 1단계\n- API 엔드포인트 정리\n- 테스트 커버리지 65% 달성\n\n### 미완료 항목 (2/7)\n- Redis 캐싱 (진행 중)\n- 모델 파이프라인 리팩토링 (착수 전)\n\n### 회고\n**잘된 점:** 코드 리뷰 정례화, 버그 감소\n**개선 필요:** 외부 API 의존성 리스크 관리\n\n### 다음 스프린트 우선순위\n1. 멀티 프로바이더 폴백 구현\n2. Redis 캐싱 완성\n3. 파이프라인 리팩토링 시작",
                 content_summary="스프린트 #8 완료율 71%. 외부 API 장애로 인한 지연 발생. 다음 스프린트에서 멀티 프로바이더 폴백 구현과 Redis 캐싱 완성을 최우선으로 진행 예정.",
                 status="DRAFT", generated_at=ago(days=6), updated_at=ago(days=5)),
        ]
        for mn in minutes_data:
            db.add(models.Minutes(**mn))
        db.commit()
        print(f"✓ 회의록 {len(minutes_data)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # NOTIFICATIONS (각 사용자 2~3개)
        # ─────────────────────────────────────────────────────────────────
        notif_data = [
            dict(user_id=U["김민준"].id,  type="AGENDA_ASSIGNED",
                 message="'전략적 파트너십 후보 기업 검토' 안건의 담당자로 지정되었습니다.", is_read=False, ref_id=3, ref_type="agenda"),
            dict(user_id=U["김민준"].id,  type="REPORT_REVIEWED",
                 message="제출한 'Q1 AI 전략 리뷰' 자료 검토가 완료되었습니다. 점수: 87.5점", is_read=True, ref_id=1, ref_type="report"),
            dict(user_id=U["박준혁"].id,  type="REPORT_FEEDBACK",
                 message="'AI 경쟁사 분석' 자료에 피드백이 달렸습니다. 확인 후 보완 제출 바랍니다.", is_read=False, ref_id=2, ref_type="report"),
            dict(user_id=U["박준혁"].id,  type="SESSION_STARTED",
                 message="'스프린트 #9 플래닝' 회의가 시작되었습니다.", is_read=True, ref_id=10, ref_type="session"),
            dict(user_id=U["최지은"].id,  type="AGENDA_ASSIGNED",
                 message="'API 응답 속도 개선' 안건 담당자로 배정되었습니다.", is_read=False, ref_id=17, ref_type="agenda"),
            dict(user_id=U["최지은"].id,  type="MINUTES_GENERATED",
                 message="'스프린트 #8 리뷰 & 레트로' 회의록이 AI에 의해 생성되었습니다. 검토 후 확정해주세요.", is_read=False, ref_id=4, ref_type="minutes"),
            dict(user_id=U["정하윤"].id,  type="REPORT_SUBMITTED",
                 message="'May2024 브랜드 캠페인 결과' 자료가 제출되었습니다. 검토 예정입니다.", is_read=True, ref_id=3, ref_type="report"),
            dict(user_id=U["정하윤"].id,  type="MEETING_SCHEDULED",
                 message="'6월 정기 브랜드 전략 회의' 일정이 확정되었습니다.", is_read=False, ref_id=6, ref_type="session"),
            dict(user_id=U["이서연"].id,  type="AGENDA_ASSIGNED",
                 message="'ESG 경영 도입 방향 수립' 안건 담당자로 배정되었습니다.", is_read=False, ref_id=13, ref_type="agenda"),
            dict(user_id=U["관리자"].id,  type="REPORT_APPROVED",
                 message="'2024 Q1 경영 실적 보고서'가 최종 승인되었습니다. 점수: 91.0점", is_read=True, ref_id=4, ref_type="report"),
            dict(user_id=U["관리자"].id,  type="SYSTEM",
                 message="이번 주 3개 회의에서 총 5개 안건이 완료되었습니다.", is_read=False, ref_id=None, ref_type=None),
            dict(user_id=U["한도윤"].id,  type="AGENDA_ASSIGNED",
                 message="'SNS 콘텐츠 전략 방향 수정' 안건 담당자로 배정되었습니다.", is_read=True, ref_id=7, ref_type="agenda"),
        ]
        for n in notif_data:
            db.add(models.Notification(**n, created_at=ago(days=2)))
        db.commit()
        print(f"✓ 알림 {len(notif_data)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # CHAT MESSAGES (AI 에이전트 대화 기록)
        # ─────────────────────────────────────────────────────────────────
        chat_data = [
            # 김민준 — Meeting 1 prepare 채팅
            dict(user_id=U["김민준"].id, context_type="prepare", context_id=M["AI 제품 전략 회의"].id,
                 role="user", content="다음 회의에서 멀티모달 AI 도입 논의를 위해 어떤 자료를 준비해야 할까요?"),
            dict(user_id=U["김민준"].id, context_type="prepare", context_id=M["AI 제품 전략 회의"].id,
                 role="agent", content="멀티모달 AI 도입 논의를 위해 다음 자료를 준비하시면 좋겠습니다:\n\n1. **현재 인프라 현황** — GPU 사양, 메모리 용량, 예상 업그레이드 비용\n2. **경쟁사 멀티모달 현황** — GPT-4V, Gemini Pro Vision, Claude Sonnet 기능 비교\n3. **ROI 분석** — 멀티모달 추가 시 예상 고객 가치 및 수익 증대 효과\n4. **기술 구현 로드맵** — 단계별 구현 일정 및 리소스 요구사항\n\n이전 회의록에서 최지은 주임이 'A100 GPU 8장 필요'라고 언급한 바 있으니 해당 견적도 포함하시면 좋을 것 같습니다."),
            dict(user_id=U["김민준"].id, context_type="prepare", context_id=M["AI 제품 전략 회의"].id,
                 role="user", content="경쟁사 분석에서 우리가 가장 취약한 부분이 뭔가요?"),
            dict(user_id=U["김민준"].id, context_type="prepare", context_id=M["AI 제품 전략 회의"].id,
                 role="agent", content="이전 자료 분석 결과를 기반으로 보면, 현재 가장 취약한 영역은 **멀티모달 처리 능력**입니다.\n\n- OpenAI: 이미지 + 텍스트 + 코드 통합 처리\n- Google Gemini: 음성 + 영상 + 텍스트 네이티브 지원\n- 우리 서비스: 텍스트 전용\n\n단기적으로는 문서 이미지(PPT, PDF 시각 요소) 처리 기능을 먼저 추가하고, 중기적으로 음성 입력을 지원하는 로드맵이 현실적입니다."),
            # 박준혁 — 세션 회의 중 채팅
            dict(user_id=U["박준혁"].id, context_type="room", context_id=S["3차 정기회의 — 파트너십 논의"].id,
                 role="user", content="현재 논의 중인 파트너십 후보 3개사의 주요 특징을 요약해줘"),
            dict(user_id=U["박준혁"].id, context_type="room", context_id=S["3차 정기회의 — 파트너십 논의"].id,
                 role="agent", content="이전 회의 자료와 그래프 데이터를 기반으로 파트너십 후보 3개사 요약입니다:\n\n**A사 (데이터 공급):** 의료/바이오 도메인 특화 데이터셋 보유. NDA 협의 완료. 독점 공급 가능.\n\n**B사 (기술 파트너):** MLOps 플랫폼 전문. 우리 파이프라인과 높은 호환성. 지분 투자 관심 표명.\n\n**C사 (배포 채널):** 대기업 그룹사 IT 서비스 총괄. B2B 영업 채널 확보 가능. 단, 수익 배분 협의 필요.\n\n우선순위는 B사 → A사 → C사 순으로 추천드립니다."),
            # 최지은 — 자료 분석 채팅
            dict(user_id=U["최지은"].id, context_type="report", context_id=rpts[4].id,
                 role="user", content="이 스프린트 리뷰 자료에서 개선이 필요한 부분이 뭔지 알려줘"),
            dict(user_id=U["최지은"].id, context_type="report", context_id=rpts[4].id,
                 role="agent", content="업로드된 자료를 분석한 결과입니다:\n\n**부족한 부분:**\n1. 외부 API 장애에 대한 **근본 원인 분석(RCA)** 누락\n2. 재발 방지 대책이 '폴백 구현'으로만 언급되어 구체성 부족\n3. 지연된 2개 항목에 대한 영향도 분석 없음\n\n**보완 권장사항:**\n- 5 Whys 방법론으로 API 장애 원인 심층 분석\n- 폴백 전략 구체화 (프로바이더 우선순위, 자동 전환 임계값)\n- 미완료 항목이 다음 스프린트 목표에 미치는 영향 명시"),
        ]
        for c in chat_data:
            db.add(models.ChatMessage(**c, created_at=ago(days=3)))
        db.commit()
        print(f"✓ 채팅 메시지 {len(chat_data)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # HITL REVIEWS (AI 추출 항목 3개 + 보고서 검토 1개)
        # ─────────────────────────────────────────────────────────────────
        hitl_data = [
            dict(meeting_id=M["AI 제품 전략 회의"].id,
                 session_id=S["1차 정기회의 — Q1 리뷰"].id,
                 target_type="extracted_item", status="APPROVED",
                 reviewer_id=U["김민준"].id,
                 ai_output=json.dumps({"content": "GPU A100 8장 추가 구매 검토", "department": "AI개발팀", "due_date": "2024-06-15"}),
                 human_decision=json.dumps({"approved": True, "comment": "인프라 예산 검토 후 진행"}),
                 comment="Q2 예산 확보 후 구매 결정 예정",
                 reviewed_at=ago(days=25)),
            dict(meeting_id=M["AI 제품 전략 회의"].id,
                 session_id=S["1차 정기회의 — Q1 리뷰"].id,
                 target_type="extracted_item", status="APPROVED",
                 reviewer_id=U["박준혁"].id,
                 ai_output=json.dumps({"content": "vLLM 도입으로 추론 속도 30% 개선 목표 설정", "department": "AI개발팀", "due_date": "2024-07-01"}),
                 human_decision=json.dumps({"approved": True, "comment": "스프린트 #9에 반영"}),
                 comment="스프린트 계획에 포함 완료",
                 reviewed_at=ago(days=24)),
            dict(meeting_id=M["전사 경영 전략 회의"].id,
                 session_id=S["2024 Q1 경영 전략 회의"].id,
                 target_type="extracted_item", status="PENDING",
                 reviewer_id=None,
                 ai_output=json.dumps({"content": "Series B 투자 유치를 위한 IR 자료 작성 착수", "department": "전략기획팀", "due_date": "2024-08-01"}),
                 human_decision=None,
                 comment=None, reviewed_at=None),
            dict(meeting_id=M["AI 제품 전략 회의"].id,
                 session_id=S["2차 정기회의 — 경쟁사 분석"].id,
                 target_type="report", target_id=rpts[1].id,
                 status="REVISED", reviewer_id=U["김민준"].id,
                 ai_output="보고서 검토 결과: 경쟁사 데이터는 충실하나 우리 제품 대비 GAP 분석과 대응 전략 부분이 미흡합니다.",
                 human_decision="GAP 분석 섹션 추가 및 단기/중기/장기 대응 전략 구체화 후 재제출 요청",
                 comment="재제출 기한: 1주 이내", reviewed_at=ago(days=12)),
        ]
        for h in hitl_data:
            db.add(models.HitlReview(**h, created_at=ago(days=5)))
        db.commit()
        print(f"✓ HITL 리뷰 {len(hitl_data)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # AGENT LOGS (성공 기록)
        # ─────────────────────────────────────────────────────────────────
        agent_logs_data = [
            dict(operation="minutes_gen", entity_type="session", entity_id=str(S["1차 정기회의 — Q1 리뷰"].id),
                 status="success", payload={"model": "gpt-4o-mini", "tokens": 1823}),
            dict(operation="report_review", entity_type="report", entity_id="1",
                 status="success", payload={"model": "gpt-4o-mini", "score": 87.5}),
            dict(operation="agenda_extract", entity_type="session", entity_id=str(S["1차 정기회의 — Q1 리뷰"].id),
                 status="success", payload={"extracted_count": 3}),
            dict(operation="sync_meeting", entity_type="meeting", entity_id="1",
                 status="success", payload={"neo4j_node": "Meeting:1"}),
        ]
        for al in agent_logs_data:
            db.add(models.AgentLog(**al, retry_count=0, created_at=ago(days=1), updated_at=ago(days=1)))
        db.commit()
        print(f"✓ 에이전트 로그 {len(agent_logs_data)}개 생성")

        # ─────────────────────────────────────────────────────────────────
        # TOKEN USAGE LOGS
        # ─────────────────────────────────────────────────────────────────
        token_data = [
            dict(user_id=U["김민준"].id, meeting_id=M["AI 제품 전략 회의"].id,
                 operation="minutes_gen", model="gpt-4o-mini",
                 prompt_tokens=1240, completion_tokens=583, total_tokens=1823),
            dict(user_id=U["박준혁"].id, meeting_id=M["AI 제품 전략 회의"].id,
                 operation="report_review", model="gpt-4o-mini",
                 prompt_tokens=3102, completion_tokens=847, total_tokens=3949),
            dict(user_id=U["최지은"].id, meeting_id=M["AI 개발팀 주간 스프린트"].id,
                 operation="chat", model="gpt-4o-mini",
                 prompt_tokens=892, completion_tokens=421, total_tokens=1313),
            dict(user_id=U["정하윤"].id, meeting_id=M["마케팅 브랜드 전략 회의"].id,
                 operation="agenda_extract", model="gpt-4o-mini",
                 prompt_tokens=1567, completion_tokens=312, total_tokens=1879),
            dict(user_id=U["관리자"].id, meeting_id=M["전사 경영 전략 회의"].id,
                 operation="report_review", model="gpt-4o-mini",
                 prompt_tokens=4201, completion_tokens=1023, total_tokens=5224),
            dict(user_id=U["이서연"].id, meeting_id=M["전사 경영 전략 회의"].id,
                 operation="chat", model="gpt-4o-mini",
                 prompt_tokens=654, completion_tokens=289, total_tokens=943),
        ]
        for t in token_data:
            db.add(models.TokenUsageLog(**t, created_at=ago(days=5)))
        db.commit()
        print(f"✓ 토큰 사용 로그 {len(token_data)}개 생성")

        print("\n✅ PostgreSQL 시드 완료!")
        db.expunge_all()
        return users, meetings, sessions, agendas

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 : Neo4j 시드 (PostgreSQL 동기화 + 추가 그래프 데이터)
# ─────────────────────────────────────────────────────────────────────────────

async def seed_neo4j(users, meetings, sessions, agendas):
    from neo4j_sync import run_cypher

    print("\n[Neo4j] 기존 그래프 데이터 초기화 중...")
    await run_cypher("MATCH (n) DETACH DELETE n")

    # ── Organization 노드 ─────────────────────────────────────────────────
    await run_cypher("""
        CREATE (o:Organization {
            id: 'org-workmaite',
            name: '워크메이트',
            org_type: 'IT스타트업',
            founded: '2022',
            description: 'AI 기반 회의 관리 플랫폼'
        })
    """)

    # ── Department 노드 ───────────────────────────────────────────────────
    depts = [
        ("dept-strategy", "전략기획팀",   "STRATEGY"),
        ("dept-ai",       "AI개발팀",     "AI_DEV"),
        ("dept-marketing","마케팅팀",     "MARKETING"),
        ("dept-exec",     "경영진",        "EXEC"),
    ]
    for d_id, d_name, d_code in depts:
        await run_cypher("""
            CREATE (d:Department {id: $id, name: $name, code: $code})
            WITH d
            MATCH (o:Organization {id: 'org-workmaite'})
            CREATE (d)-[:BELONGS_TO]->(o)
        """, {"id": d_id, "name": d_name, "code": d_code})

    # ── PostgreSQL 전체 동기화 ─────────────────────────────────────────────
    print("[Neo4j] PostgreSQL 데이터 동기화 중...")
    from neo4j_sync import sync_all_from_pg
    stats = await sync_all_from_pg()
    print(f"[Neo4j] 동기화 완료: {stats}")

    # ── Person → Department 관계 (부서 소속) ─────────────────────────────
    dept_map = {
        "전략기획팀": "dept-strategy",
        "AI개발팀":   "dept-ai",
        "마케팅팀":   "dept-marketing",
        "경영진":     "dept-exec",
    }
    U = {u.name: u for u in users}
    for user in users:
        dept_id = dept_map.get(user.department)
        if dept_id:
            await run_cypher("""
                MATCH (p:Person {pg_id: $uid}), (d:Department {id: $did})
                MERGE (p)-[:BELONGS_TO]->(d)
            """, {"uid": user.id, "did": dept_id})

    # ── Meeting → Organization 관계 ───────────────────────────────────────
    for m in meetings:
        await run_cypher("""
            MATCH (m:Meeting {pg_id: $mid}), (o:Organization {id: 'org-workmaite'})
            MERGE (m)-[:PART_OF]->(o)
        """, {"mid": m.id})

    # ── 레거시 MeetingGroup 노드 (프론트 시드 데이터 호환용) ──────────────
    mg_data = [
        dict(id="mg-001", title="AI 제품 전략 회의",    meeting_type="WEEKLY",    pg_id=meetings[0].id),
        dict(id="mg-002", title="마케팅 브랜드 전략 회의", meeting_type="MONTHLY",  pg_id=meetings[1].id),
        dict(id="mg-003", title="전사 경영 전략 회의",   meeting_type="QUARTERLY", pg_id=meetings[2].id),
        dict(id="mg-004", title="AI 개발팀 주간 스프린트", meeting_type="WEEKLY",   pg_id=meetings[3].id),
    ]
    for mg in mg_data:
        await run_cypher("""
            MERGE (mg:MeetingGroup {id: $id})
            SET mg.title = $title, mg.meeting_type = $meeting_type,
                mg.status = 'active', mg.pg_id = $pg_id
            WITH mg
            MATCH (o:Organization {id: 'org-workmaite'})
            MERGE (mg)-[:PART_OF]->(o)
        """, mg)

    # MeetingGroup ↔ Person 관계 (기존 id 기반 조회 호환)
    mg_member_map = [
        ("mg-001", "김민준", "ADMIN_OF"),
        ("mg-001", "박준혁", "MEMBER_OF"),
        ("mg-001", "최지은", "MEMBER_OF"),
        ("mg-001", "관리자", "MEMBER_OF"),
        ("mg-002", "정하윤", "ADMIN_OF"),
        ("mg-002", "이서연", "MEMBER_OF"),
        ("mg-002", "한도윤", "MEMBER_OF"),
        ("mg-003", "관리자", "ADMIN_OF"),
        ("mg-003", "김민준", "MEMBER_OF"),
        ("mg-003", "정하윤", "MEMBER_OF"),
        ("mg-003", "이서연", "MEMBER_OF"),
        ("mg-004", "박준혁", "ADMIN_OF"),
        ("mg-004", "최지은", "MEMBER_OF"),
        ("mg-004", "김민준", "MEMBER_OF"),
    ]
    name_to_id = {u.name: u.id for u in users}
    for mg_id, name, rel in mg_member_map:
        uid = name_to_id.get(name)
        if uid:
            await run_cypher(f"""
                MATCH (mg:MeetingGroup {{id: $mg_id}}), (p:Person {{pg_id: $uid}})
                MERGE (p)-[:{rel}]->(mg)
            """, {"mg_id": mg_id, "uid": uid})

    # ── MeetingGroup에 Agenda 노드 연결 ───────────────────────────────────
    for i, a in enumerate(agendas):
        # 어느 MeetingGroup에 속하는지 매핑
        mg_idx = 0
        if a.meeting_id == meetings[1].id: mg_idx = 1
        elif a.meeting_id == meetings[2].id: mg_idx = 2
        elif a.meeting_id == meetings[3].id: mg_idx = 3
        mg_id = mg_data[mg_idx]["id"]
        await run_cypher("""
            MATCH (ag:Agenda {pg_id: $ag_id}), (mg:MeetingGroup {id: $mg_id})
            MERGE (ag)-[:OWNED_BY]->(mg)
        """, {"ag_id": a.id, "mg_id": mg_id})

    # ── Session 노드를 MeetingGroup에도 연결 (기존 레거시 쿼리 호환) ──────
    for s in sessions:
        mg_idx = 0
        if s.meeting_id == meetings[1].id: mg_idx = 1
        elif s.meeting_id == meetings[2].id: mg_idx = 2
        elif s.meeting_id == meetings[3].id: mg_idx = 3
        mg_id = mg_data[mg_idx]["id"]
        await run_cypher("""
            MATCH (s:Session {pg_id: $sid}), (mg:MeetingGroup {id: $mg_id})
            MERGE (s)-[:HELD_BY]->(mg)
        """, {"sid": s.id, "mg_id": mg_id})

    # ── 회의체 간 관계 (PARENT_OF) ────────────────────────────────────────
    await run_cypher("""
        MATCH (m1:Meeting {pg_id: $src}), (m2:Meeting {pg_id: $tgt})
        MERGE (m1)-[:PARENT_OF]->(m2)
    """, {"src": meetings[0].id, "tgt": meetings[3].id})
    await run_cypher("""
        MATCH (mg1:MeetingGroup {id: 'mg-001'}), (mg2:MeetingGroup {id: 'mg-004'})
        MERGE (mg1)-[:PARENT_OF]->(mg2)
    """)

    print("✅ Neo4j 시드 완료!")

    # ── 최종 카운트 확인 ─────────────────────────────────────────────────
    result = await run_cypher("""
        MATCH (n) RETURN labels(n)[0] AS label, count(*) AS cnt
        ORDER BY cnt DESC
    """)
    print("\n[Neo4j 노드 현황]")
    for row in result:
        print(f"  {row['label']:20s}: {row['cnt']}개")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("Workmaite 테스트 데이터 시드 시작")
    print("=" * 60)

    users, meetings, sessions, agendas = seed_postgres()
    await init_vector_index()
    await seed_neo4j(users, meetings, sessions, agendas)

    print("\n" + "=" * 60)
    print("시드 완료. 로그인 정보:")
    print("  admin@workmaite.com  / workmaite123")
    print("  minjun.kim@workmaite.com  / workmaite123")
    print("  junhyuk.park@workmaite.com / workmaite123")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

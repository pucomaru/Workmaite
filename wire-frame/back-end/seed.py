"""
seed.py - DB 초기 데이터 생성 스크립트
실행: python seed.py
"""
from datetime import datetime, timedelta
from database import SessionLocal, engine
from models import Base, User, Meeting, MeetingMember, MeetingSession, MeetingLoop, Minutes, Report, Agenda, Todo
from auth import hash_password as get_password_hash

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# ─── 기존 데이터 확인 ────────────────────────────────────────
if db.query(User).count() > 0:
    print("⚠️  이미 데이터가 있습니다. 중복 실행을 방지합니다.")
    print("   초기화 후 다시 실행하려면 workmate.db 파일을 삭제하세요.")
    db.close()
    exit()

now = datetime.utcnow()

# ─── 사용자 ─────────────────────────────────────────────────
users_data = [
    # 본사
    dict(name="김민준", employee_id="admin@company.com",    password_hash=get_password_hash("1234"), department="기획팀",   organization="본사", position="팀장"),
    dict(name="이수연", employee_id="user1@company.com",    password_hash=get_password_hash("1234"), department="전략팀",   organization="본사", position="대리"),
    dict(name="박지훈", employee_id="user2@company.com",    password_hash=get_password_hash("1234"), department="운영팀",   organization="본사", position="팀장"),
    dict(name="정다은", employee_id="user3@company.com",    password_hash=get_password_hash("1234"), department="개발팀",   organization="본사", position="선임"),
    dict(name="최현우", employee_id="user4@company.com",    password_hash=get_password_hash("1234"), department="개발팀",   organization="본사", position="사원"),
    dict(name="한소희", employee_id="user5@company.com",    password_hash=get_password_hash("1234"), department="마케팅팀", organization="본사", position="대리"),
    dict(name="윤재원", employee_id="user6@company.com",    password_hash=get_password_hash("1234"), department="인사팀",   organization="본사", position="팀장"),
    # 파트너사 A — 테크파트너스(주)
    dict(name="강태양", employee_id="kang@techpartners.co", password_hash=get_password_hash("1234"), department="기술전략팀", organization="테크파트너스(주)", position="이사"),
    dict(name="오지민", employee_id="oh@techpartners.co",   password_hash=get_password_hash("1234"), department="개발팀",     organization="테크파트너스(주)", position="선임연구원"),
    # 파트너사 B — 글로벌마케팅그룹
    dict(name="문세영", employee_id="moon@gmg.com",         password_hash=get_password_hash("1234"), department="캠페인팀",   organization="글로벌마케팅그룹", position="팀장"),
    dict(name="임하늘", employee_id="lim@gmg.com",          password_hash=get_password_hash("1234"), department="데이터분석팀", organization="글로벌마케팅그룹", position="매니저"),
    # 파트너사 C — 스마트로지스틱스
    dict(name="신재호", employee_id="shin@smartlogis.com",  password_hash=get_password_hash("1234"), department="물류기획팀", organization="스마트로지스틱스", position="차장"),
]
users = []
for u in users_data:
    obj = User(**u)
    db.add(obj)
    users.append(obj)
db.flush()

김민준, 이수연, 박지훈, 정다은, 최현우, 한소희, 윤재원, 강태양, 오지민, 문세영, 임하늘, 신재호 = users

# ─── 회의체 ─────────────────────────────────────────────────
meetings_data = [
    dict(title="전략기획위원회",  purpose="중장기 전략 수립 및 경영 방향 결정",       meeting_type="Quarterly", start_date=now - timedelta(days=120), created_by=김민준.id),
    dict(title="운영위원회",      purpose="사업 운영 현황 점검 및 의사결정",            meeting_type="Monthly",   start_date=now - timedelta(days=90),  created_by=박지훈.id),
    dict(title="개발팀 주간회의", purpose="스프린트 계획 및 기술 검토",                 meeting_type="Weekly",    start_date=now - timedelta(days=60),  created_by=정다은.id),
    dict(title="마케팅 전략회의", purpose="Q2 캠페인 기획 및 성과 공유",                meeting_type="Monthly",   start_date=now - timedelta(days=45),  created_by=한소희.id),
    dict(title="인사위원회",      purpose="채용·평가·조직 관련 주요 사안 심의",         meeting_type="Quarterly", start_date=now - timedelta(days=30),  created_by=윤재원.id),
    # 타 조직 협업 회의체
    dict(title="기술협력 조인트 워킹그룹", purpose="본사-테크파트너스 공동 기술 투자 및 플랫폼 연동 협의", meeting_type="Monthly", start_date=now-timedelta(days=50), created_by=김민준.id),
    dict(title="공동 마케팅 TF",           purpose="본사-글로벌마케팅그룹 Q2·Q3 캠페인 공동 기획 및 성과 공유", meeting_type="Monthly", start_date=now-timedelta(days=35), created_by=한소희.id),
    dict(title="공급망 최적화 협의체",     purpose="본사-스마트로지스틱스 물류 효율화 및 리스크 공동 대응",  meeting_type="Quarterly", start_date=now-timedelta(days=40), created_by=박지훈.id),
]
meetings = []
for m in meetings_data:
    obj = Meeting(**m, status="active")
    db.add(obj)
    meetings.append(obj)
db.flush()

전략기획, 운영, 개발주간, 마케팅, 인사, 기술협력TF, 공동마케팅TF, 공급망협의체 = meetings

# ─── 소위원회 (부모 회의체 참조) ─────────────────────────────
sub_meetings_data = [
    # 전략기획위원회 산하
    dict(title="예산심의소위원회",    purpose="예산안 사전 검토 및 심의",             meeting_type="Quarterly", start_date=now-timedelta(days=100), created_by=김민준.id, parent_id=None),
    dict(title="규정개정소위원회",    purpose="내규 및 운영 규정 개정 검토",          meeting_type="Monthly",   start_date=now-timedelta(days=80),  created_by=이수연.id, parent_id=None),
    # 운영위원회 산하
    dict(title="위기관리소위원회",    purpose="사업 리스크 모니터링 및 대응 방안 논의", meeting_type="Monthly",  start_date=now-timedelta(days=70),  created_by=박지훈.id, parent_id=None),
    # 인사위원회 산하
    dict(title="채용심사소위원회",    purpose="서류·면접 심사 결과 검토 및 최종 승인", meeting_type="Quarterly", start_date=now-timedelta(days=25), created_by=윤재원.id, parent_id=None),
]
sub_meetings = []
for sm in sub_meetings_data:
    obj = Meeting(**sm, status="active")
    db.add(obj)
    sub_meetings.append(obj)
db.flush()

예산심의, 규정개정, 위기관리, 채용심사 = sub_meetings
# 부모 연결
예산심의.parent_id  = 전략기획.id
규정개정.parent_id  = 전략기획.id
위기관리.parent_id  = 운영.id
채용심사.parent_id  = 인사.id
db.flush()

# ─── 회의체 멤버 ─────────────────────────────────────────────
member_pairs = [
    (전략기획, 김민준, "admin"),  (전략기획, 이수연, "presenter"),
    (운영,     박지훈, "admin"),  (운영,     김민준, "presenter"), (운영, 이수연, "presenter"),
    (개발주간, 정다은, "admin"),  (개발주간, 최현우, "presenter"),
    (마케팅,   한소희, "admin"),  (마케팅,   이수연, "presenter"),
    (인사,     윤재원, "admin"),  (인사,     김민준, "presenter"),
    # 소위원회 멤버
    (예산심의, 김민준, "admin"),  (예산심의, 이수연, "presenter"), (예산심의, 박지훈, "presenter"),
    (규정개정, 이수연, "admin"),  (규정개정, 김민준, "presenter"),
    (위기관리, 박지훈, "admin"),  (위기관리, 정다은, "presenter"),
    (채용심사, 윤재원, "admin"),  (채용심사, 한소희, "presenter"),
    # 협업 회의체 멤버 (타사 포함)
    (기술협력TF, 김민준, "admin"),   (기술협력TF, 정다은, "presenter"), (기술협력TF, 강태양, "presenter"), (기술협력TF, 오지민, "presenter"),
    (공동마케팅TF, 한소희, "admin"), (공동마케팅TF, 이수연, "presenter"), (공동마케팅TF, 문세영, "presenter"), (공동마케팅TF, 임하늘, "presenter"),
    (공급망협의체, 박지훈, "admin"),  (공급망협의체, 김민준, "presenter"), (공급망협의체, 신재호, "presenter"),
]
for mtg, user, role in member_pairs:
    db.add(MeetingMember(meeting_id=mtg.id, user_id=user.id, role=role))

# ─── MeetingLoop + Session + Minutes ────────────────────────
def add_session(meeting, loop_num, sess_num, title, days_ago, with_minutes=True, minutes_text=None):
    loop = db.query(MeetingLoop).filter_by(meeting_id=meeting.id, loop_number=loop_num).first()
    if not loop:
        loop = MeetingLoop(meeting_id=meeting.id, loop_number=loop_num)
        db.add(loop); db.flush()
    ended = now - timedelta(days=days_ago)
    sess = MeetingSession(
        meeting_id=meeting.id, loop_id=loop.id,
        session_number=sess_num, title=title,
        scheduled_at=ended, started_at=ended,
        ended_at=ended if days_ago > 0 else None,
        status="ended" if days_ago > 0 else "scheduled",
    )
    db.add(sess); db.flush()
    if with_minutes and days_ago > 0:
        text = minutes_text or f"## {title}\n\n**주요 내용:** 정기 회의 진행\n\n**결정 사항:**\n- 다음 회의까지 자료 준비 완료\n\n**과제:**\n- 담당자별 업무 분장 확정"
        db.add(Minutes(session_id=sess.id, content_summary=text, generated_at=ended))
    return sess

# 전략기획위원회
add_session(전략기획, 1, 1, "2025 전략 수립 1차", 90, minutes_text="## 2025 전략 수립 1차\n\n**의사결정:** 3개년 전략 방향 확정\n\n**과제:**\n- 이수연: 전략 실행 로드맵 작성 (2주 내)")
add_session(전략기획, 1, 2, "예산 계획 검토", 60, minutes_text="## 예산 계획 검토\n\n**의사결정:** 2025 예산안 1차 승인\n\n**과제:**\n- 김민준: 부서별 예산 배분안 확정")
add_session(전략기획, 2, 1, "전략 실행 점검",  30)
add_session(전략기획, 2, 2, "2차 전략 수립 회의", -7)  # 예정

# 운영위원회
add_session(운영, 1, 1, "운영 현황 보고 1분기", 75)
add_session(운영, 1, 2, "사업 리스크 점검",     45)
add_session(운영, 2, 1, "2분기 운영 현황 보고",  10)
add_session(운영, 2, 2, "운영 개선 방안 논의",  -3)

# 개발팀 주간회의
for w, d in [(19, 21), (20, 14), (21, 7)]:
    add_session(개발주간, 1, w, f"스프린트 W{w} 회의", d)
add_session(개발주간, 1, 22, f"스프린트 W22 계획", -7)

# 마케팅
add_session(마케팅, 1, 1, "Q1 성과 공유", 40)
add_session(마케팅, 1, 2, "Q2 캠페인 기획", 10)
add_session(마케팅, 1, 3, "Q2 캠페인 중간 점검", -5)

# 인사
add_session(인사, 1, 1, "상반기 채용 계획 심의", 28)
add_session(인사, 1, 2, "채용 심사 2차", -2)

# ─── 소위원회 세션 ────────────────────────────────────────────
add_session(예산심의, 1, 1, "2025 예산안 1차 심의",  85)
add_session(예산심의, 1, 2, "2025 예산안 2차 심의",  55)
add_session(예산심의, 2, 1, "2026 예산 편성 방향 논의", -10)  # 예정

add_session(규정개정, 1, 1, "운영 규정 개정안 검토",  65)
add_session(규정개정, 1, 2, "최종 개정안 확정",       35)

add_session(위기관리, 1, 1, "공급망 리스크 점검",     60)
add_session(위기관리, 1, 2, "대응 방안 수립",         30)
add_session(위기관리, 1, 3, "리스크 모니터링 현황 보고", -5)  # 예정

add_session(채용심사, 1, 1, "서류 심사 결과 검토",    20)
add_session(채용심사, 1, 2, "최종 면접 결과 논의",    -1)  # 예정

# ─── 협업 회의체 세션 ─────────────────────────────────────
add_session(기술협력TF, 1, 1, "협업 범위 및 플랫폼 연동 방안 논의",  40,
    minutes_text="## 협업 범위 및 플랫폼 연동 방안 논의\n\n**가당 조직:** 본사(정다은) + 테크파트너스(강태양, 오지민)\n\n**의사결정:**\n- 포터시티스 API 연동 파일넷 비는 확정\n- 공동 보안 심의 일정: 2주 내\n\n**과제:**\n- 정다은: API 명세서 초안 (1주 내)\n- 강태양: 테크파트너스 플랫폼 요구사항 산츠")
add_session(기술협력TF, 1, 2, "API 명세 검토 및 보안 프레임워크 혁의",  10)
add_session(기술협력TF, 1, 3, "필득 테스트 결과 공유 및 본계화 일정 확정", -8)  # 예정

add_session(공동마케팅TF, 1, 1, "Q2 공동 캔페인 노선 협의",  30,
    minutes_text="## Q2 공동 캔페인 노선 협의\n\n**가당 조직:** 본사(한소희, 이수연) + 글로벌마케팅그룹(문세영, 임하늘)\n\n**의사결정:**\n- 디지털 채널 3종 공동 진행 확정\n- KPI: CTR 3.5% / 전환율 1.8% 목표\n\n**과제:**\n- 임하늘: 데이터 세그먼테이션 분석보고서 (10일 내)")
add_session(공동마케팅TF, 1, 2, "Q2 캔페인 중간 성과점검 및 Q3 주제 논의", -4)  # 예정

add_session(공급망협의체, 1, 1, "물류 프로세스 기술 연동 방안 협의",  35,
    minutes_text="## 물류 프로세스 기술 연동 방안 협의\n\n**가당 조직:** 본사(박지훈, 김민준) + 스마트로지스틱스(신재호)\n\n**의사결정:**\n- WMS-ERP 연동 PoC 실시 (8주 일정)\n- SLA 조건: 납품 정확도 99.5% 이상\n\n**과제:**\n- 박지훈: 연동 요구사항 정리\n- 신재호: 현행 프로세스 맵핑 문서")
add_session(공급망협의체, 1, 2, "PoC 결과 공유 및 본계화 SLA 협의", -12)  # 예정

# ─── 보고서 ─────────────────────────────────────────────────
reports_data = [
    dict(meeting_id=전략기획.id, presenter_id=이수연.id, file_name="2025_전략보고서.pdf",       status="approved", submitted_at=now-timedelta(days=88), approved_at=now-timedelta(days=85)),
    dict(meeting_id=전략기획.id, presenter_id=김민준.id, file_name="예산계획_v1.xlsx",            status="approved", submitted_at=now-timedelta(days=58), approved_at=now-timedelta(days=55)),
    dict(meeting_id=운영.id,     presenter_id=박지훈.id, file_name="1분기_운영현황.pdf",          status="approved", submitted_at=now-timedelta(days=73), approved_at=now-timedelta(days=70)),
    dict(meeting_id=개발주간.id, presenter_id=정다은.id, file_name="기술검토_보고서_W19.pdf",     status="submitted", submitted_at=now-timedelta(days=20)),
    dict(meeting_id=개발주간.id, presenter_id=최현우.id, file_name="스프린트_회고_W20.pdf",       status="draft",     submitted_at=now-timedelta(days=13)),
    dict(meeting_id=마케팅.id,   presenter_id=한소희.id, file_name="Q2_캠페인_기획서.pdf",        status="submitted", submitted_at=now-timedelta(days=9)),
    dict(meeting_id=인사.id,        presenter_id=윤재원.id, file_name="상반기_채용계획_보고서.pdf",  status="approved", submitted_at=now-timedelta(days=26), approved_at=now-timedelta(days=23)),
    # 협업 회의체 보고서
    dict(meeting_id=기술협력TF.id,  presenter_id=정다은.id,  file_name="API_연동_명세서_v1.pdf",         status="approved",  submitted_at=now-timedelta(days=9),  approved_at=now-timedelta(days=7)),
    dict(meeting_id=공동마케팅TF.id, presenter_id=한소희.id, file_name="Q2_공동캔페인_성과보고.pdf",    status="submitted", submitted_at=now-timedelta(days=5)),
    dict(meeting_id=공급망협의체.id, presenter_id=박지훈.id, file_name="WMS-ERP_PoC_결과보고서.pdf",  status="draft",     submitted_at=now-timedelta(days=3)),
]
for r in reports_data:
    db.add(Report(**r, created_at=r.get("submitted_at", now)))

# ─── 아젠다 ─────────────────────────────────────────────────
agendas_data = [
    dict(meeting_id=전략기획.id, department="기획팀",   content="2025 3개년 전략 방향 확정",       agenda_type="scheduled", status="confirmed", presenter_name="김민준", order_num=1),
    dict(meeting_id=전략기획.id, department="전략팀",   content="부서별 실행 로드맵 보고",           agenda_type="scheduled", status="confirmed", presenter_name="이수연", order_num=2),
    dict(meeting_id=운영.id,     department="운영팀",   content="2분기 사업 운영 현황 보고",         agenda_type="scheduled", status="confirmed", presenter_name="박지훈", order_num=1),
    dict(meeting_id=개발주간.id, department="개발팀",   content="W22 스프린트 목표 및 태스크 분배", agenda_type="draft",     status="draft",     presenter_name="정다은", order_num=1),
    dict(meeting_id=마케팅.id,   department="마케팅팀", content="Q2 디지털 캠페인 전략 발표",        agenda_type="scheduled", status="confirmed", presenter_name="한소희", order_num=1),
]
for a in agendas_data:
    db.add(Agenda(**a, created_at=now))

# ─── 과제(Todo) ──────────────────────────────────────────────
todos_data = [
    dict(meeting_id=전략기획.id, user_id=이수연.id, content="전략 실행 로드맵 작성",      assignee_name="이수연", assignee_dept="전략팀", priority="urgent_important", status="in_progress", due_date=now+timedelta(days=5)),
    dict(meeting_id=전략기획.id, user_id=김민준.id, content="부서별 예산 배분안 확정",    assignee_name="김민준", assignee_dept="기획팀", priority="important",        status="pending",     due_date=now+timedelta(days=10)),
    dict(meeting_id=운영.id,     user_id=박지훈.id, content="2분기 운영 리스크 보고서 제출", assignee_name="박지훈", assignee_dept="운영팀", priority="important",     status="pending",     due_date=now+timedelta(days=7)),
    dict(meeting_id=개발주간.id, user_id=정다은.id, content="코드 리뷰 가이드라인 문서화", assignee_name="정다은", assignee_dept="개발팀", priority="normal",          status="done",        due_date=now-timedelta(days=3)),
    dict(meeting_id=개발주간.id, user_id=최현우.id, content="API 성능 최적화 PoC",        assignee_name="최현우", assignee_dept="개발팀", priority="urgent",           status="at_risk",     due_date=now+timedelta(days=2)),
    dict(meeting_id=마케팅.id,   user_id=한소희.id, content="Q2 캠페인 소재 3종 제작",    assignee_name="한소희", assignee_dept="마케팅팀", priority="important",      status="in_progress", due_date=now+timedelta(days=14)),
    dict(meeting_id=인사.id,        user_id=윤재원.id, content="채용 공고 최종안 검토",       assignee_name="윤재원", assignee_dept="인사팀",  priority="urgent_important", status="pending",     due_date=now+timedelta(days=3)),
    # 협업 회의체 과제
    dict(meeting_id=기술협력TF.id,   user_id=정다은.id,  content="API 명세서 초안 작성 및 파트너사 공유",  assignee_name="정다은", assignee_dept="개발팀",   priority="urgent_important", status="in_progress", due_date=now+timedelta(days=4)),
    dict(meeting_id=공동마케팅TF.id,  user_id=한소희.id, content="데이터 세그먼테이션 분석 보고서 구성",  assignee_name="한소희", assignee_dept="마케팅팀", priority="important",        status="in_progress", due_date=now+timedelta(days=8)),
    dict(meeting_id=공급망협의체.id,  user_id=박지훈.id, content="WMS-ERP 연동 요구사항 정리 및 협의",  assignee_name="박지훈", assignee_dept="운영팀",   priority="urgent",           status="pending",     due_date=now+timedelta(days=6)),
]
for t in todos_data:
    db.add(Todo(**t, source_type="meeting_minutes", created_at=now))

db.commit()
db.close()

print("✅ 시드 데이터 생성 완료!")
print(f"   👤 사용자 {len(users_data)}명")
print(f"   🏢 회의체 {len(meetings_data)}개 (타 조직 협업 3개 포함)")
print(f"   🔹 소위원회 {len(sub_meetings_data)}개 (예산심의 / 규정개정 / 위기관리 / 채용심사) — 부모 회의체 parent_id 연결")
print(f"   📝 회의 세션 및 회의록 다수")
print(f"   📄 보고서 {len(reports_data)}건")
print(f"   ✅ 과제 {len(todos_data)}건")
print()
print("🔑 로그인 계정:")
print("   admin@company.com / 1234  (김민준 · 기획팀 팀장)")
print("   user1@company.com / 1234  (이수연 · 전략팀 대리)")
print("   user2@company.com / 1234  (박지훈 · 운영팀 팀장)")

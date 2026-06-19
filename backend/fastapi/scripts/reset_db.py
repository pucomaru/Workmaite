# """DB 초기화 스크립트 — 모든 테이블 DROP 후 전체 재생성.

# 실행 방법 (backend/fastapi 디렉토리에서):
#     python -m scripts.reset_db

# 이 스크립트 하나로 DROP + CREATE 까지 완료됩니다.
# """

# from sqlalchemy import text
# from db.database import engine
# from db import models

# # 모든 테이블 (FK 역순 — 자식 테이블부터 삭제)
# _DROP_ORDER = [
#     "hitl_reviews",
#     "token_usage_logs",
#     "agent_logs",
#     "chat_messages",
#     "archives_combined",
#     "minutes",
#     "stt_segments",
#     "report_criteria",
#     "report_reviews",
#     "reports",  # 구 테이블명 (혹시 남아있을 경우 대비)
#     "agendas",
#     "meeting_relations",
#     "meeting_sessions",
#     "meeting_members",
#     "meetings",
#     "users",
# ]


# def reset():
#     # 1. 전체 DROP
#     with engine.connect() as conn:
#         conn.execute(text("SET session_replication_role = 'replica';"))
#         for tbl in _DROP_ORDER:
#             conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
#             print(f"  dropped: {tbl}")
#         conn.execute(text("SET session_replication_role = 'origin';"))
#         conn.commit()
#     print("\n[1/2] 모든 테이블 삭제 완료")

#     # 2. 전체 CREATE (SQLAlchemy 모델 기준으로 전부 재생성)
#     models.Base.metadata.create_all(bind=engine)
#     print("[2/2] 모든 테이블 생성 완료")


# if __name__ == "__main__":
#     import os

#     # 안전장치 (P7-5): 공유/원격 DB를 향해 실수로 실행하는 것 방지
#     _host = os.environ.get("DB_HOST", "localhost")
#     if (
#         _host not in ("localhost", "127.0.0.1")
#         and os.environ.get("RESET_DB_FORCE") != "yes"
#     ):
#         raise SystemExit(
#             f"[중단] DB_HOST={_host} — localhost가 아닙니다. "
#             "정말 원격/공유 DB를 초기화하려면 RESET_DB_FORCE=yes를 설정하세요."
#         )
#     print("=== Workmaite DB 초기화 ===\n")
#     confirm = input("모든 테이블과 데이터가 삭제됩니다. 계속하시겠습니까? (yes 입력): ")
#     if confirm.strip().lower() != "yes":
#         print("취소됨.")
#     # else:
#     # reset() # 정말 필요한경우에만 주석 제거 후 실행

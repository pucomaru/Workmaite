"""Neo4j 노드 ID 규약 헬퍼 (HC-9).

주의: 함수명에 to_ 프리픽스 — 사용처 파일들에서 agenda_id/session_id 등이
파라미터 이름으로 광범위하게 쓰여 단순 명칭은 섀도잉된다 (1차 자동 치환 시도가
이 충돌로 롤백됨 — 치환은 파일별 수동 검토로 진행할 것).

PG id ↔ Neo4j 문자열 id 변환이 f-string으로 6개 파일에 산재해 있던 것을 단일 모듈로 통일.
규약: Meetings="mg-{pg}", Session="session-{pg}", Agenda="agenda-{pg}",
Report="report-{pg}", Minutes="minutes-{pg}", HumanJudgment="hj-{pg}". User는 pg_id 숫자 키.
"""
import re

_RE_TRAILING_NUM = re.compile(r"(\d+)$")


def to_mg_id(pg_id: int) -> str:
    return f"mg-{pg_id}"


def to_session_id(pg_id: int) -> str:
    return f"session-{pg_id}"


def to_agenda_id(pg_id: int) -> str:
    return f"agenda-{pg_id}"


def to_report_id(pg_id: int) -> str:
    return f"report-{pg_id}"


def to_minutes_id(pg_id: int) -> str:
    return f"minutes-{pg_id}"


def to_hj_id(pg_id: int) -> str:
    return f"hj-{pg_id}"


def parse_pg_id(node_id) -> int | None:
    """'agenda-263', 'mg-12', '263' 등에서 PG 숫자 id를 추출한다. 실패 시 None."""
    s = str(node_id or "")
    m = _RE_TRAILING_NUM.search(s)
    return int(m.group(1)) if m else None

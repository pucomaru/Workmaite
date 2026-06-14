"""AI 파이프라인 튜닝 상수 — 코드 곳곳에 흩어진 매직넘버를 단일 소스로 집약한다.

하드코딩 금지 원칙(AI 서비스): 유사도 임계값·검색 k·컨텍스트 잘림 길이를 환경변수로 외부화해
코드 수정 없이 도메인/임베딩 모델 변경에 맞춰 튜닝할 수 있게 한다. 미설정 시 합리적 기본값 사용.
"""

import os


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# ── 지식 그래프 자동 연결/정제 유사도 임계값 (reconcile_graph / analyze-relationships) ──
AGENDA_LINK_THRESHOLD = _f("AI_AGENDA_LINK_THRESHOLD", 0.80)  # 회의 간 유사 안건 연결
DOC_LINK_THRESHOLD = _f("AI_DOC_LINK_THRESHOLD", 0.78)  # 문서↔안건 연결
LIFECYCLE_LINK_THRESHOLD = _f(
    "AI_LIFECYCLE_LINK_THRESHOLD", 0.72
)  # 회의록→안건 생명주기 연결
ORPHAN_ATTACH_THRESHOLD = _f("AI_ORPHAN_ATTACH_THRESHOLD", 0.78)  # 고아 문서 자동 첨부
PRUNE_THRESHOLD = _f("AI_PRUNE_THRESHOLD", 0.70)  # 저유사도 연결 정제(제거) 기준

# ── 검색 top-k / 컨텍스트 잘림 길이(문자) ──
SEARCH_K_DEFAULT = _i("AI_SEARCH_K", 5)
MAX_DOC_CHARS = _i("AI_MAX_DOC_CHARS", 8000)  # 단일 문서 본문 최대 길이
MAX_PREV_MINUTES_CHARS = _i("AI_MAX_PREV_MINUTES_CHARS", 3000)  # 이전 회의록 컨텍스트
CHAT_HISTORY_LIMIT = _i("AI_CHAT_HISTORY_LIMIT", 20)  # 대화 이력 로드 개수

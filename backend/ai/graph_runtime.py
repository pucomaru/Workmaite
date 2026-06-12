"""LangGraph 체크포인터 런타임 (P3A-1, H-1).

HITL `interrupt()`는 체크포인터 없이는 동작하지 않는다(기존 코드는 compile() 시
체크포인터가 없어 get_state가 'No checkpointer set'으로 실패 — UX-1의 원인).
AsyncPostgresSaver로 영속화해 승인 대기 상태가 재시작·스케일아웃에도 유지되게 한다.

체크포인트 테이블(checkpoints 등)은 LangGraph가 자체 관리(setup())하는 프레임워크
내부 스키마라 Flyway 대상에서 제외한다.
"""
import logging
import os

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None


def _dsn() -> str:
    return (
        f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
    )


async def init_checkpointer() -> None:
    """앱 시작 시 1회 호출 (main.py lifespan)."""
    global _pool, _checkpointer
    if _checkpointer is not None:
        return
    # autocommit: AsyncPostgresSaver.setup()의 CREATE INDEX CONCURRENTLY 요구사항
    _pool = AsyncConnectionPool(
        _dsn(), min_size=1, max_size=5, open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    await _pool.open()
    saver = AsyncPostgresSaver(_pool)
    await saver.setup()
    _checkpointer = saver
    logger.info("[GraphRuntime] AsyncPostgresSaver 초기화 완료")


async def close_checkpointer() -> None:
    global _pool, _checkpointer
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError(
            "체크포인터가 초기화되지 않았습니다 — main.py lifespan에서 init_checkpointer() 필요"
        )
    return _checkpointer

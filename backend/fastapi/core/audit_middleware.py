"""감사 로그 미들웨어 (P1-6, BE-1).

변경성 요청(POST/PATCH/PUT/DELETE)이 성공하면 audit_logs에 "누가-언제-무엇을" 기록한다.
Spring의 @AuditLogged AOP와 같은 테이블을 공유한다. 기록 실패는 본 요청에 영향을 주지 않는다.
"""

import json
import logging

from jose import jwt, JWTError
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from core.auth import SECRET_KEY, ALGORITHMS
from db.database import SessionLocal

logger = logging.getLogger(__name__)

_MUTATING = {"POST", "PATCH", "PUT", "DELETE"}
# 내부 동기화·문서·메트릭은 제외
_EXCLUDE_PREFIXES = ("/metrics", "/api/sync", "/docs", "/openapi", "/redoc")


def _actor_id_from(request) -> int | None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:], SECRET_KEY, algorithms=ALGORITHMS)
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except (JWTError, ValueError):
        return None


def _entity_type_from(path: str) -> str:
    # /api/v1/meetings/3/members → 'meetings', /api/agent/... → 'agent'
    parts = [p for p in path.split("/") if p and p not in ("api", "v1")]
    return (parts[0] if parts else "http")[:40]


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        try:
            path = request.url.path
            if (
                request.method in _MUTATING
                and response.status_code < 400
                and not path.startswith(_EXCLUDE_PREFIXES)
            ):
                detail = json.dumps({"method": request.method, "path": path})
                ip = request.headers.get("x-forwarded-for", "").split(",")[
                    0
                ].strip() or (request.client.host if request.client else None)
                db = SessionLocal()
                try:
                    db.execute(
                        text(
                            "INSERT INTO audit_logs "
                            "(actor_id, action, entity_type, detail, ip_addr, created_at) "
                            "VALUES (:actor, :action, :etype, CAST(:detail AS jsonb), :ip, now())"
                        ),
                        {
                            "actor": _actor_id_from(request),
                            "action": request.method,
                            "etype": _entity_type_from(path),
                            "detail": detail,
                            "ip": ip,
                        },
                    )
                    db.commit()
                finally:
                    db.close()
        except Exception as e:
            logger.warning(f"[Audit] 기록 실패 (요청에는 영향 없음): {e}")
        return response

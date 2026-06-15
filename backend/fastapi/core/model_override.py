"""요청 단위 LLM 모델 오버라이드 미들웨어 (P1 — 모델 전역 적용).

프런트가 보내는 `X-LLM-Model` 헤더를 읽어, pricing.yaml에 등록된 모델일 때만
model_override_var(ContextVar)를 요청 스코프 전체에 설정한다. llm_factory가 이 값을
최우선으로 사용하므로 supervisor뿐 아니라 모든 에이전트/엔드포인트의 LLM 호출이
사용자가 UI에서 고른 모델로 통일된다.

순수 ASGI 미들웨어로 구현한 이유: Starlette BaseHTTPMiddleware는 엔드포인트를 별도
태스크에서 실행해 dispatch에서 설정한 ContextVar가 전파되지 않는다. 최외곽 ASGI
계층에서 설정하면 스트리밍 응답이 만드는 자식 태스크까지 컨텍스트를 상속한다.
"""

import logging

from llm.llm_factory import model_override_var
from llm.pricing import PRICING

logger = logging.getLogger(__name__)

_HEADER = b"x-llm-model"


class ModelOverrideMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        token = None
        for name, value in scope.get("headers") or []:
            if name == _HEADER:
                model = value.decode("latin-1").strip()
                # 등록된(=단가 있는) 모델만 허용 — 임의 모델명 주입 차단
                if model and model in PRICING:
                    token = model_override_var.set(model)
                break

        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                model_override_var.reset(token)

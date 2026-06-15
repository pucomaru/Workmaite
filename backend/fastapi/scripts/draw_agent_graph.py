"""현재 AI Agent(supervisor) 워크플로우를 컴파일하고 그려서 PNG로 내보낸다.

진실의 원천은 graphs/supervisor_graph.py 의 create_react_agent 그래프다. 여기서
재사용하므로 도구·프롬프트가 바뀌면 다이어그램도 자동으로 따라간다.

실행:
    python -m scripts.draw_agent_graph                 # 기본 경로(scripts/agent_graph.png)
    python scripts/draw_agent_graph.py [출력경로.png]   # 직접 실행

산출물:
    <out>.png   Mermaid 렌더 PNG (mermaid.ink API 사용 → 네트워크 필요)
    <out>.mmd   Mermaid 소스 텍스트 (네트워크 불필요, 항상 생성 — PNG 실패 시 폴백)

전제: 레포 루트 .env 에 OPENAI_API_KEY 존재(클라이언트 '생성'에만 필요, 네트워크 호출 없음).
"""

import os
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서 유니코드(✓/✗ 등) 출력 시 UnicodeEncodeError 방지
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# --- import 루트(backend/fastapi)와 .env 셋업 ----------------------------------
# 이 파일: backend/fastapi/scripts/draw_agent_graph.py → import 루트는 그 부모(backend/fastapi)
_FASTAPI_ROOT = Path(__file__).resolve().parent.parent
if str(_FASTAPI_ROOT) not in sys.path:
    sys.path.insert(0, str(_FASTAPI_ROOT))

# main.py 와 동일하게 레포 루트 .env 를 override 로드 (OPENAI_API_KEY 등)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_FASTAPI_ROOT.parent.parent / ".env", override=True)

# LangSmith 트레이싱은 그래프 그리기에 불필요 — 키 없이 켜지면 403 스팸이라 끈다
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else _FASTAPI_ROOT / "scripts" / "agent_graph.png"
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    mmd_path = out.with_suffix(".mmd")

    if not os.environ.get("OPENAI_API_KEY"):
        print("✗ OPENAI_API_KEY 가 없습니다. 레포 루트 .env 를 확인하세요.", file=sys.stderr)
        return 1

    # 1) 현재 워크플로우 컴파일 (create_react_agent 는 컴파일된 그래프를 돌려준다)
    from graphs.supervisor_graph import _get_agent

    agent = _get_agent()

    # 2) 그리기용 그래프 추출. xray=True 로 서브그래프(도구 등) 내부까지 펼친다
    graph = agent.get_graph(xray=True)

    # 3) Mermaid 소스는 항상 저장(네트워크 불필요) + ASCII 미리보기 출력
    mmd_path.write_text(graph.draw_mermaid(), encoding="utf-8")
    print(f"✓ Mermaid 소스 저장: {mmd_path}")
    try:
        print("\n--- 그래프 구조(ASCII) ---")
        print(graph.draw_ascii())
    except Exception as e:  # grandalf 미설치 등 — 치명적이지 않음
        print(f"(ASCII 미리보기 생략: {e})")

    # 4) PNG 렌더 (mermaid.ink API → 네트워크 필요)
    try:
        png_bytes = graph.draw_mermaid_png()
        out.write_bytes(png_bytes)
        print(f"\n✓ PNG 저장: {out}  ({len(png_bytes):,} bytes)")
        return 0
    except Exception as e:
        print(
            f"\n✗ PNG 렌더 실패: {e}\n"
            f"  → Mermaid 소스({mmd_path})는 저장됨. "
            f"https://mermaid.live 에 붙여넣어 PNG로 내보낼 수 있습니다.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

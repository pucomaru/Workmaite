"""Mermaid(.mmd) 소스를 PNG로 렌더한다 (mermaid.ink API → 네트워크 필요).

자동 드로잉(draw_agent_graph.py)으로는 안 나오는 손으로 그린 다이어그램
(예: supervisor_architecture.mmd — LLM 분류 + if/elif 디스패치 전체 구조)을 PNG로 뽑을 때 사용.

실행:
    python scripts/render_mermaid.py scripts/supervisor_architecture.mmd
    python scripts/render_mermaid.py <입력.mmd> [출력.png]
"""

import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "사용법: python scripts/render_mermaid.py <입력.mmd> [출력.png]",
            file=sys.stderr,
        )
        return 1
    src = Path(sys.argv[1]).resolve()
    if not src.exists():
        print(f"✗ 입력 파일 없음: {src}", file=sys.stderr)
        return 1
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src.with_suffix(".png")

    from langchain_core.runnables.graph_mermaid import draw_mermaid_png

    mermaid_syntax = src.read_text(encoding="utf-8")
    try:
        png_bytes = draw_mermaid_png(mermaid_syntax)
        out.write_bytes(png_bytes)
        print(f"✓ PNG 저장: {out}  ({len(png_bytes):,} bytes)")
        return 0
    except Exception as e:
        print(
            f"✗ PNG 렌더 실패: {e}\n"
            f"  → {src} 를 https://mermaid.live 에 붙여넣어 내보낼 수 있습니다.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

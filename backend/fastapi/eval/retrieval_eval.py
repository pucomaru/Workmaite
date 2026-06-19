"""retrieval 스모크 평가 (P6-5, G-8) — self-retrieval recall@k.

실데이터에서 표본 노드의 제목으로 검색해 자기 자신이 top-k에 드는지 측정한다.
G-1(인덱스명 불일치 → 전면 0건) 류의 회귀를 데이터 라벨링 없이 탐지하는 최소 안전망.
사용법: python3 eval/retrieval_eval.py
"""

import asyncio
import json
import os
import sys
from typing import Any
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
os.environ.setdefault("NEO4J_RETRY_INTERVAL_SEC", "300")

K = 5
SAMPLES_PER_LABEL = 5
LABELS = ["Minutes", "Agenda", "Report"]


async def main() -> None:
    from graphdb.neo4j_client import run_cypher
    from graphdb.retrieval_registry import hybrid_search

    out: dict[str, Any] = {"ran_at": datetime.now().isoformat(), "k": K, "labels": {}}
    for label in LABELS:
        title_field = "title" if label != "Report" else "file_name"
        rows = await run_cypher(
            f"MATCH (n:{label}) WHERE n.embedding IS NOT NULL AND n.{title_field} IS NOT NULL "
            f"AND size(n.{title_field}) > 5 "
            f"RETURN n.{title_field} AS title ORDER BY n.updated_at DESC LIMIT {SAMPLES_PER_LABEL}"
        )
        hit = 0
        for r in rows:
            results = await hybrid_search(label, r["title"], k=K)
            titles = [str(x.get("title") or "") for x in results]
            if any(r["title"][:20] in t or t[:20] in r["title"] for t in titles if t):
                hit += 1
        recall = hit / len(rows) if rows else None
        out["labels"][label] = {"n": len(rows), "recall_at_k": recall}
        print(f"{label}: self-retrieval recall@{K} = {hit}/{len(rows)}")
    path = (
        Path(__file__).parent
        / "results"
        / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_retrieval.json"
    )
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("저장:", path)


if __name__ == "__main__":
    asyncio.run(main())

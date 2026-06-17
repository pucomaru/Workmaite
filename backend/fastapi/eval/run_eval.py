"""스모크 eval 하네스 (P6-2/P6-3 축소판).

라우팅 정확도와 아젠다 추출 P/R/F1을 골든셋으로 측정해 JSON으로 기록한다.
프롬프트/모델/아키텍처 변경(예: P3A-5 Supervisor 전환) 전후로 실행해 회귀를 비교한다.

사용법 (backend/fastapi에서):
    python3 eval/run_eval.py            # 전체
    python3 eval/run_eval.py routing    # 라우팅만
    python3 eval/run_eval.py extraction # 추출만
"""

import asyncio
import difflib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
os.environ.setdefault("NEO4J_RETRY_INTERVAL_SEC", "300")

DATASET = Path(__file__).parent / "dataset"
RESULTS = Path(__file__).parent / "results"

# title 부분 일치 임계값 (Plan은 임베딩 ≥0.85를 제시 — 스모크는 무의존 difflib로 시작)
TITLE_SIM_THRESHOLD = 0.55


def _title_match(expected: str, predicted: str) -> bool:
    e, p = expected.replace(" ", ""), (predicted or "").replace(" ", "")
    if e in p or p in e:
        return True
    return difflib.SequenceMatcher(None, e, p).ratio() >= TITLE_SIM_THRESHOLD


async def eval_routing() -> dict:
    from routers.supervisor import classify_intent

    cases = json.loads((DATASET / "routing_cases.json").read_text())["cases"]
    rows, correct = [], 0
    for c in cases:
        agent, *_ = await classify_intent(c["message"], c.get("history"))
        ok = agent in c["expected"]
        correct += ok
        rows.append(
            {
                "id": c["id"],
                "message": c["message"],
                "expected": c["expected"],
                "predicted": agent,
                "ok": ok,
            }
        )
        print(f"  [{'✓' if ok else '✗'}] {c['id']} {c['message'][:30]} → {agent}")
    acc = correct / len(cases)
    print(f"라우팅 정확도: {correct}/{len(cases)} = {acc:.2%}")
    return {
        "metric": "routing_accuracy",
        "accuracy": acc,
        "n": len(cases),
        "rows": rows,
    }


async def eval_extraction() -> dict:
    from agents.task_extractor import extract_agendas_and_todos

    cases = json.loads((DATASET / "extraction_cases.json").read_text())["cases"]
    tp = fp = fn = dept_ok = dept_total = 0
    rows = []
    for c in cases:
        result = await extract_agendas_and_todos(
            content=c["content"], org_dept_list=c["org_dept_list"]
        )
        predicted = result.get("agendas", [])
        matched_pred_idx: set[int] = set()
        case_tp = 0
        for exp in c["expected_agendas"]:
            hit = None
            for i, p in enumerate(predicted):
                if i in matched_pred_idx:
                    continue
                if _title_match(exp["title"], str(p.get("title", ""))):
                    hit = i
                    break
            if hit is not None:
                matched_pred_idx.add(hit)
                case_tp += 1
                dept_total += 1
                if (
                    str(predicted[hit].get("department", "")).strip()
                    == exp["department"]
                ):
                    dept_ok += 1
            else:
                fn += 1
        tp += case_tp
        fp += len(predicted) - len(matched_pred_idx)
        rows.append(
            {
                "id": c["id"],
                "expected": c["expected_agendas"],
                "predicted": [
                    {"title": p.get("title"), "department": p.get("department")}
                    for p in predicted
                ],
            }
        )
        print(
            f"  {c['id']}: 기대 {len(c['expected_agendas'])} / 예측 {len(predicted)} / 일치 {case_tp}"
        )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    dept_acc = dept_ok / dept_total if dept_total else 0.0
    print(
        f"추출 P={precision:.2f} R={recall:.2f} F1={f1:.2f} | 부서 정확도={dept_acc:.2%}"
    )
    return {
        "metric": "extraction",
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "dept_accuracy": dept_acc,
        "rows": rows,
    }


async def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out: dict = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "model": os.environ.get("OPENAI_MODEL", "?"),
    }
    if which in ("all", "routing"):
        print("== 라우팅 ==")
        out["routing"] = await eval_routing()
    if which in ("all", "extraction"):
        print("== 추출 ==")
        out["extraction"] = await eval_extraction()
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{which}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"결과 저장: {path}")


if __name__ == "__main__":
    asyncio.run(main())

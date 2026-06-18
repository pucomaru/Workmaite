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


async def eval_groundedness() -> dict:
    """환각 가드(_Grounding 판정) 판별 정확도. context를 직접 주입해 Neo4j 없이
    hallucination_guard의 판단 코어를 측정한다. 양성 클래스 = '환각'(grounded=false)."""
    from graphs.agent_workflow import _struct, _Grounding, _GROUND_SYS

    cases = json.loads((DATASET / "groundedness_cases.json").read_text())["cases"]
    correct = tp = fp = fn = 0
    rows = []
    for c in cases:
        human = f"[검색된 근거]\n{c['context']}\n\n[답변]\n{c['answer']}"
        v = await _struct(_Grounding, _GROUND_SYS, human)
        pred = bool(v.grounded)
        exp = bool(c["expected_grounded"])
        ok = pred == exp
        correct += ok
        # 환각(=grounded false)을 양성으로 본 탐지 지표
        if not exp and not pred:
            tp += 1
        elif exp and not pred:
            fp += 1
        elif not exp and pred:
            fn += 1
        rows.append({"id": c["id"], "expected": exp, "predicted": pred, "ok": ok})
        print(f"  [{'✓' if ok else '✗'}] {c['id']} 기대={exp} 예측={pred}")
    n = len(cases)
    acc = correct / n
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    print(
        f"환각 가드: 정확도={acc:.2%} | 환각탐지 P={prec:.2f} R={rec:.2f} F1={f1:.2f} (n={n})"
    )
    return {
        "metric": "groundedness_guard",
        "accuracy": acc,
        "halluc_precision": prec,
        "halluc_recall": rec,
        "halluc_f1": f1,
        "n": n,
        "rows": rows,
    }


async def eval_report() -> dict:
    """보고서 AI 채점(review_report → score 0-100) 보정. 밴드 적중률과 tier 순서(강>중>약)를 본다."""
    from agents.report_reviewer import review_report

    cases = json.loads((DATASET / "report_cases.json").read_text())["cases"]
    band_hits = 0
    tier_scores: dict[str, list[int]] = {}
    rows = []
    for c in cases:
        result = await review_report(c["report_content"], agenda=c.get("agenda", ""))
        score = int(result.get("score", 0))
        in_band = c["score_min"] <= score <= c["score_max"]
        band_hits += in_band
        tier_scores.setdefault(c["tier"], []).append(score)
        rows.append(
            {
                "id": c["id"],
                "tier": c["tier"],
                "score": score,
                "band": [c["score_min"], c["score_max"]],
                "in_band": in_band,
            }
        )
        print(
            f"  [{'✓' if in_band else '✗'}] {c['id']} ({c['tier']}) score={score} "
            f"band=[{c['score_min']},{c['score_max']}]"
        )
    means = {t: sum(s) / len(s) for t, s in tier_scores.items()}
    ordering_ok = means.get("strong", 0) > means.get("medium", 0) > means.get("weak", 0)
    n = len(cases)
    band_rate = band_hits / n
    print(
        f"보고서 채점: 밴드적중={band_rate:.2%} | tier평균={{강:{means.get('strong',0):.0f}, "
        f"중:{means.get('medium',0):.0f}, 약:{means.get('weak',0):.0f}}} | 순서일치={ordering_ok}"
    )
    return {
        "metric": "report_scoring",
        "band_hit_rate": band_rate,
        "tier_means": means,
        "ordering_ok": ordering_ok,
        "n": n,
        "rows": rows,
    }


async def eval_latency() -> dict:
    """LLM 첫 토큰 지연(TTFT) 측정. make_llm(streaming=True)로 첫 비어있지 않은 토큰까지의
    시간을 재 p50/p95/평균을 낸다. retrieval·네트워크 제외한 모델 응답성 순수값."""
    import time
    from langchain_core.messages import HumanMessage
    from routers.prompts.common import make_llm

    prompts = json.loads((DATASET / "latency_prompts.json").read_text())["prompts"]
    llm = make_llm(temperature=0.3, streaming=True)
    ttfts: list[float] = []
    for p in prompts:
        t0 = time.perf_counter()
        async for chunk in llm.astream([HumanMessage(content=p)]):
            if chunk.content:
                ttfts.append(time.perf_counter() - t0)
                break
        print(f"  TTFT {ttfts[-1]:.2f}s ← {p[:24]}")

    def _pct(vals: list[float], q: float) -> float:
        s = sorted(vals)
        idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
        return s[idx]

    p50, p95 = _pct(ttfts, 0.50), _pct(ttfts, 0.95)
    mean = sum(ttfts) / len(ttfts)
    print(
        f"TTFT: p50={p50:.2f}s p95={p95:.2f}s 평균={mean:.2f}s 최대={max(ttfts):.2f}s (n={len(ttfts)})"
    )
    return {
        "metric": "chat_ttft_seconds",
        "p50": p50,
        "p95": p95,
        "mean": mean,
        "max": max(ttfts),
        "n": len(ttfts),
        "samples": [round(t, 3) for t in ttfts],
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
    if which in ("all", "groundedness"):
        print("== 환각 가드 ==")
        out["groundedness"] = await eval_groundedness()
    if which in ("all", "report"):
        print("== 보고서 채점 ==")
        out["report"] = await eval_report()
    if which in ("all", "latency"):
        print("== TTFT ==")
        out["latency"] = await eval_latency()
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{which}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"결과 저장: {path}")


if __name__ == "__main__":
    asyncio.run(main())

"""Offline evaluation harness with quality, latency, and cost gates."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sbd_agent.graph import SbDAgent  # noqa: E402
from sbd_agent.models import ProjectRequest  # noqa: E402
from sbd_agent.mlops.promote import check_gates  # noqa: E402


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def _requirement_coverage(predicted_ids: set[str], expected_ids: set[str]) -> float:
    if not expected_ids:
        return 1.0
    return len(predicted_ids & expected_ids) / len(expected_ids)


def _retrieval_recall(retrieved_doc_ids: set[str], relevant: set[str]) -> float:
    if not relevant:
        return 1.0
    return len(retrieved_doc_ids & relevant) / len(relevant)


def _faithfulness(result_citations: list[str], retrieved_citations: set[str]) -> float:
    """Share of requirement citations that appear in retrieved context."""
    if not result_citations:
        return 0.0
    ok = 0
    for cite in result_citations:
        if any(cite == r or cite in r or r in cite for r in retrieved_citations):
            ok += 1
    return ok / len(result_citations)


def _risk_match(predicted: str, expected: str) -> float:
    order = ["low", "medium", "high", "critical"]
    if predicted == expected:
        return 1.0
    # Adjacent levels get partial credit — mirrors realistic eval tolerance
    try:
        return 0.5 if abs(order.index(predicted) - order.index(expected)) == 1 else 0.0
    except ValueError:
        return 0.0


def run_eval(
    golden_path: Path,
    slo_path: Path,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    cases = json.loads(golden_path.read_text(encoding="utf-8"))
    slo = yaml.safe_load(slo_path.read_text(encoding="utf-8"))
    agent = SbDAgent(prompt_version=prompt_version)

    coverages: list[float] = []
    recalls: list[float] = []
    faiths: list[float] = []
    risks: list[float] = []
    latencies: list[float] = []
    costs: list[float] = []
    tokens: list[float] = []
    details: list[dict[str, Any]] = []

    for case in cases:
        request = ProjectRequest.model_validate(case["request"])
        result = agent.analyze(request)
        pred_ids = {r.req_id for r in result.requirements}
        expected_ids = set(case["expected_requirement_ids"])
        retrieved_docs = {c.doc_id.split("#")[0] for c in result.retrieved}
        relevant = set(case["relevant_doc_ids"])
        citations = [r.citation for r in result.requirements]
        retrieved_cites = {c.citation for c in result.retrieved}

        cov = _requirement_coverage(pred_ids, expected_ids)
        rec = _retrieval_recall(retrieved_docs, relevant)
        faith = _faithfulness(citations, retrieved_cites)
        risk = _risk_match(result.risk.level.value, case["expected_risk"])
        latency = float(result.metrics.get("latency_ms", 0))
        cost = float(result.metrics.get("estimated_cost_usd", 0))
        tok = float(result.metrics.get("total_tokens", 0))

        coverages.append(cov)
        recalls.append(rec)
        faiths.append(faith)
        risks.append(risk)
        latencies.append(latency)
        costs.append(cost)
        tokens.append(tok)

        details.append(
            {
                "id": case["id"],
                "requirement_coverage": round(cov, 3),
                "retrieval_recall_at_5": round(rec, 3),
                "faithfulness": round(faith, 3),
                "risk_accuracy": round(risk, 3),
                "predicted_risk": result.risk.level.value,
                "expected_risk": case["expected_risk"],
                "latency_ms": latency,
                "estimated_cost_usd": cost,
                "total_tokens": tok,
                "prompt_version": result.prompt_version,
                "classical_risk": result.metrics.get("risk_classical"),
                "llm_risk": result.metrics.get("risk_llm"),
            }
        )

    report = {
        "suite": "sbd-golden",
        "n_cases": len(cases),
        "prompt_version": agent.prompt_version,
        "agent_version": details[0]["prompt_version"] and agent.prompt_version,
        "quality": {
            "requirement_coverage": round(statistics.mean(coverages), 4),
            "retrieval_recall_at_5": round(statistics.mean(recalls), 4),
            "faithfulness": round(statistics.mean(faiths), 4),
            "risk_accuracy": round(statistics.mean(risks), 4),
        },
        "latency": {
            "p50_ms": round(_percentile(latencies, 50), 2),
            "p95_ms": round(_percentile(latencies, 95), 2),
            "avg_ms": round(statistics.mean(latencies), 2),
        },
        "cost": {
            "avg_usd_per_run": round(statistics.mean(costs), 6),
            "total_usd": round(sum(costs), 6),
            "avg_tokens_per_run": round(statistics.mean(tokens), 2),
        },
        "details": details,
        "slo": slo,
    }

    failures = check_gates(report, slo)
    # Also enforce absolute latency/cost suite caps from SLO
    if report["latency"]["p50_ms"] > slo["latency"]["p50_ms_max"]:
        failures.append("latency_p50")
    if report["cost"]["total_usd"] > slo["cost"]["max_total_usd_per_eval_suite"]:
        failures.append("total_cost")

    report["gates_passed"] = len(failures) == 0
    report["failed_gates"] = failures
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run SbD golden-set evaluation")
    parser.add_argument(
        "--golden",
        type=Path,
        default=ROOT / "data" / "golden" / "cases.json",
    )
    parser.add_argument("--slo", type=Path, default=ROOT / "configs" / "slo.yaml")
    parser.add_argument("--prompt-version", default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "configs" / "agent_versions" / "last_eval_report.json",
    )
    parser.add_argument("--fail-on-gate", action="store_true", default=True)
    parser.add_argument("--no-fail-on-gate", action="store_false", dest="fail_on_gate")
    args = parser.parse_args(argv)

    report = run_eval(args.golden, args.slo, args.prompt_version)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("quality", "latency", "cost", "gates_passed", "failed_gates")}, indent=2))
    print(f"Wrote {args.out}")
    if args.fail_on_gate and not report["gates_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

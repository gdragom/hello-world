"""Agent/prompt version promotion with gate checks."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CONFIGS = ROOT / "configs"
VERSIONS_DIR = CONFIGS / "agent_versions"
SLO_PATH = CONFIGS / "slo.yaml"


def load_slo() -> dict:
    return yaml.safe_load(SLO_PATH.read_text(encoding="utf-8"))


def check_gates(eval_report: dict, slo: dict) -> list[str]:
    failures: list[str] = []
    q = eval_report.get("quality", {})
    lat = eval_report.get("latency", {})
    cost = eval_report.get("cost", {})

    if q.get("requirement_coverage", 0) < slo["quality"]["min_requirement_coverage"]:
        failures.append("requirement_coverage")
    if q.get("retrieval_recall_at_5", 0) < slo["quality"]["min_retrieval_recall_at_5"]:
        failures.append("retrieval_recall_at_5")
    if q.get("risk_accuracy", 0) < slo["quality"]["min_risk_accuracy"]:
        failures.append("risk_accuracy")
    if q.get("faithfulness", 0) < slo["quality"]["min_faithfulness"]:
        failures.append("faithfulness")

    if lat.get("p95_ms", 0) > slo["latency"]["p95_ms_max"]:
        failures.append("latency_p95")
    if cost.get("avg_usd_per_run", 0) > slo["cost"]["max_avg_usd_per_run"]:
        failures.append("avg_cost")
    if cost.get("avg_tokens_per_run", 0) > slo["cost"]["max_avg_tokens_per_run"]:
        failures.append("avg_tokens")
    return failures


def promote(version: str, environment: str, eval_report_path: Path) -> Path:
    slo = load_slo()
    if environment not in slo["promotion"]["environments"]:
        raise SystemExit(f"Unknown environment: {environment}")

    report = json.loads(eval_report_path.read_text(encoding="utf-8"))
    failures = check_gates(report, slo)
    if failures:
        raise SystemExit(f"Promotion blocked; failed gates: {', '.join(failures)}")

    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "version": version,
        "environment": environment,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "eval_report": str(eval_report_path),
        "gates_passed": True,
        "metrics": {
            "quality": report.get("quality"),
            "latency": report.get("latency"),
            "cost": report.get("cost"),
        },
    }
    out = VERSIONS_DIR / f"{environment}-{version}.json"
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")

    # Maintain a pointer file for the active environment version
    pointer = VERSIONS_DIR / f"{environment}-current.json"
    shutil.copyfile(out, pointer)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Promote agent/prompt version after eval gates")
    parser.add_argument("--version", required=True)
    parser.add_argument("--env", required=True, choices=["dev", "staging", "prod"])
    parser.add_argument("--eval-report", type=Path, required=True)
    args = parser.parse_args(argv)
    path = promote(args.version, args.env, args.eval_report)
    print(f"Promoted {args.version} to {args.env}: {path}")


if __name__ == "__main__":
    main()

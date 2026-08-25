# 90-Day Learning Roadmap (Executable)

Confirmed target: **AI Engineer / AI Platform Engineer → AI Tech Lead**.

This portfolio repo is the practice ground. Use it to deepen skills — do not chase new frameworks.

## Days 1–30: Eval, observability, RAG quality

| Skill | Practice in this repo | Stretch |
|-------|----------------------|---------|
| Golden-set eval | Extend `data/golden/cases.json` with failures you care about | Add LLM-as-judge with known pitfalls documented |
| Tracing / cost | Read spans in `AnalysisResult.metrics` | Export to LangSmith or Azure App Insights |
| Hybrid RAG | Tune weights in `HybridRetriever` | Add Azure AI Search + reranker |
| Prompt versioning | Iterate `prompts/versions.yaml` | A/B two versions on the same golden set |

**Exit criteria:** `python -m eval.harness --fail-on-gate` green; you can explain recall@5 vs faithfulness.

## Days 31–60: MLOps + classical vs LLM

| Skill | Practice in this repo | Stretch |
|-------|----------------------|---------|
| CI eval gates | Keep `.github/workflows/eval-gates.yml` green | Wire Azure DevOps + Foundry model deployments |
| Promotion | Use `mlops.promote` staging → prod | Canary traffic on prompt versions |
| Classical baseline | Retrain / expand `risk_classifier` | PEFT/LoRA fine-tune on requirement labeling |
| Reliability | Timeouts/retries in `reliability/retries.py` | Idempotent tools + checkpointing persistence |

**Exit criteria:** Metric report comparing classical vs LLM vs ensemble; staged promote blocked when you intentionally break a gate.

## Days 61–90: Portfolio + positioning

| Skill | Practice | Stretch |
|-------|----------|---------|
| Case study | Keep `docs/CASE_STUDY.md` updated with real numbers from last eval | Internal demo to security + engineering stakeholders |
| Interview narrative | Use positioning line in `CAREER_PATH.md` | Mock system-design: “design an agent platform” |
| Selective security edge | Map threats to OWASP LLM Top 10 in case study | Red-team your own tools allowlist |

**Exit criteria:** One written case study with architecture, threats mitigated, eval metrics, and cost; applications to role targets 1–3.

## What not to do

- More broad security certs
- New agent frameworks beyond LangGraph/Foundry depth
- Research-level DL math unless targeting Applied Scientist
- Generic prompt-engineering courses without eval metrics

## Weekly cadence (suggested)

1. One improvement PR to this repo (metric, RAG, or gate)
2. One page of notes: what failed in eval and why
3. One conversation or design doc practice (build vs buy / when agents are wrong)

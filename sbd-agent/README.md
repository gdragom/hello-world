# Security-by-Design AI Agent Portfolio

Production-shaped **Security-by-Design (SbD)** multi-agent system demonstrating the skills gap between a security architect and an AI Engineer / AI Tech Lead:

- LangGraph multi-agent pipeline (retrieve → requirements → threats → risk → finalize)
- Hybrid RAG (BM25 + TF-IDF) over security standards with citations
- Offline golden-set evaluation (coverage, recall@5, faithfulness, risk accuracy)
- Observability: trace spans, token/cost estimates, latency
- Classical ML risk classifier baseline ensembled with LLM scoring
- Prompt/agent version registry + promotion gates (dev → staging → prod)
- CI/CD: GitHub Actions + Azure DevOps pipelines that **fail on SLO breach**

This is intentionally runnable **without cloud API keys** (deterministic heuristic analyzer) so eval gates work in CI. Swap the analyzer for Azure AI Foundry / Azure OpenAI clients when wiring a live environment.

## Quick start

```bash
cd sbd-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Single analysis
python -m sbd_agent.cli --input data/samples/demo_request.json

# Golden-set eval + SLO gates
python -m eval.harness --fail-on-gate

# Promote version after green gates
python -m sbd_agent.mlops.promote \
  --version v1.1.0 \
  --env staging \
  --eval-report configs/agent_versions/last_eval_report.json

pytest -q
```

## Layout

| Path | Purpose |
|------|---------|
| `src/sbd_agent/graph.py` | LangGraph agent orchestration |
| `src/sbd_agent/rag/` | Chunking + hybrid retrieval |
| `src/sbd_agent/observability/` | Tracing, tokens, cost |
| `src/sbd_agent/risk_classifier/` | Classical baseline vs LLM |
| `src/sbd_agent/prompts/versions.yaml` | Prompt registry |
| `src/sbd_agent/mlops/promote.py` | Version promotion |
| `data/standards/` | RAG corpus |
| `data/golden/cases.json` | Eval golden set |
| `configs/slo.yaml` | Quality / latency / cost SLOs |
| `docs/` | Career path, learning roadmap, case study |

## Docs

- [Confirmed career target](docs/CAREER_PATH.md)
- [90-day learning roadmap](docs/LEARNING_ROADMAP.md)
- [Portfolio case study](docs/CASE_STUDY.md)

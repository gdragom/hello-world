# Case Study: Security-by-Design Multi-Agent System

**Owner:** Jiyong (Max) Shin  
**Positioning:** AI Engineer / AI Platform Engineer → AI Tech Lead (with AI Security Lead as bridge)  
**Stack:** LangGraph-style multi-agent orchestration, hybrid RAG, classical ML baseline, CI eval gates (Microsoft Foundry–ready)

## Problem

Security-by-Design reviews were historically manual (spreadsheets / ad-hoc checklists). Requestors omit critical context; reviewers miss requirements; auditability and KPI tracking suffer. An AI analysis layer must improve coverage **without** becoming an unmeasured chatbot.

## Solution architecture

```text
ProjectRequest
    → Retrieve (hybrid BM25 + TF-IDF over standards corpus)
    → Requirements agent (citation-grounded controls)
    → Threats agent (incl. prompt injection / tool abuse when AI is in scope)
    → Risk ensemble (LLM heuristic + classical logistic regression)
    → Finalize (trace, tokens, cost, prompt/agent versions)
```

Prompts are versioned in `src/sbd_agent/prompts/versions.yaml` and promoted like code via `mlops.promote` only after golden-set gates pass.

## Threats mitigated (AI + classic)

| Threat | Control in design |
|--------|-------------------|
| Prompt injection / tool abuse | Allowlisted analysis tools; no unconstrained code execution; HITL pattern documented in standards |
| Hallucinated policy IDs | Requirements must cite retrieved chunks; faithfulness metric in eval |
| PII leakage via logs/traces | Standards + requirements for log redaction; sample traces omit raw PII fields |
| Silent quality regressions | CI fails on coverage / recall / risk / latency / cost SLO breach |
| Uncontrolled cost | Token accounting + max USD/token gates per suite |

## Evaluation method

Golden set: `data/golden/cases.json` (six scenarios from internal wiki → AI agent → payments).

Metrics:

- **Requirement coverage** — fraction of expected control IDs recovered
- **Retrieval recall@5** — fraction of relevant standard docs retrieved
- **Faithfulness** — requirement citations grounded in retrieved context
- **Risk accuracy** — predicted vs expected inherent risk (adjacent partial credit)
- **Latency p50/p95** and **estimated USD / tokens**

SLOs: `configs/slo.yaml`.

### Latest local results

From `python -m eval.harness` (deterministic offline analyzer, 6 golden cases):

| Metric | SLO | Latest |
|--------|-----|--------|
| Requirement coverage | ≥ 0.75 | **1.00** |
| Retrieval recall@5 | ≥ 0.70 | **0.875** |
| Faithfulness | ≥ 0.80 | **1.00** |
| Risk accuracy | ≥ 0.70 | **0.75** |
| Latency p95 | ≤ 2500 ms | **~3.3 ms** (offline) |
| Avg USD / run | ≤ 0.05 | **~$0.00049** (estimated) |

Gates: **passed**. Prompt/agent version `v1.1.0` promoted to staging and prod pointers under `configs/agent_versions/`.

## Classical vs LLM risk scoring

A small logistic regression baseline (`risk_classifier`) is trained on synthetic SbD feature rows and ensembled with LLM scoring (60/40). This proves fluency with **when not to call a large model** and gives a regression-friendly signal for CI.

## Cost and reliability notes

Offline mode uses heuristic token estimates suitable for CI. In Microsoft Foundry, replace analyzer calls with Azure OpenAI / model router, keep the same metrics schema, and enforce model failover + content safety at the platform boundary.

Reliability primitives: retries with backoff, soft timeouts, idempotent retrieval, explicit prompt/agent version tags on every result.

## Outcome / interview narrative

> Designed and automated Security-by-Design with a multi-agent LangGraph system on Microsoft Foundry patterns, with CI/CD integration, risk scoring, and coverage of security requirements — combining AppSec leadership with agentic AI delivery.

Business impact framing: faster SbD turnaround, fewer missed requirements, auditable AI decisions, and regression-proof prompt changes.

## Next increments

1. Live Foundry model backend behind the same graph interfaces  
2. Azure AI Search hybrid retrieval + cross-encoder rerank  
3. Persistent LangGraph checkpointer for human-in-the-loop reviews  
4. Expand golden set with red-team prompt-injection cases  

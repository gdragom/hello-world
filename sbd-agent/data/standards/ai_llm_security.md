# AI and LLM Security Standard

## AI-01 AI threat modeling
Systems using LLMs or agents must threat-model prompt injection, insecure output handling, and tool abuse
per OWASP LLM Top 10 style risks.

## AI-02 RAG corpus controls
Minimize sensitive data in retrieval indexes. Apply tenant isolation and retention to embeddings and chunks.
Redact PII before indexing when feasible.

## AI-03 Eval gates in CI
Offline evaluation suites (coverage, faithfulness, retrieval recall, safety) must run in CI and block regression.

## AI-04 Secure tool design
Tools exposed to agents must be allowlisted, least privilege, idempotent where possible, and sandboxed.
Human-in-the-loop is required for irreversible high-impact actions.

## AI-05 Observability and cost
Trace prompts/tool calls with redaction. Track token cost and latency against published SLOs.

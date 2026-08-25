"""Unit and integration tests for SbD agent portfolio."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sbd_agent.graph import SbDAgent
from sbd_agent.models import ProjectRequest
from sbd_agent.prompts import list_prompt_versions, load_prompt_bundle
from sbd_agent.rag.retriever import HybridRetriever, chunk_text
from sbd_agent.reliability.retries import RetryError, with_retry
from sbd_agent.risk_classifier.model import ensemble, train_default_model
from sbd_agent.agents.analyzer import score_risk_llm

ROOT = Path(__file__).resolve().parents[1]
STANDARDS = ROOT / "data" / "standards"


def test_chunk_text_overlap():
    text = "a" * 1200
    chunks = chunk_text(text, chunk_size=500, overlap=80)
    assert len(chunks) >= 2


def test_hybrid_retriever_finds_ai_standard():
    retriever = HybridRetriever.from_directory(STANDARDS)
    hits = retriever.retrieve("prompt injection RAG corpus controls for LLM agents", top_k=3)
    doc_ids = {h.doc_id.split("#")[0] for h in hits}
    assert "ai_llm_security" in doc_ids


def test_prompt_versions_load():
    versions = list_prompt_versions()
    assert "v1.1.0" in versions
    bundle = load_prompt_bundle("v1.1.0")
    assert "system" in bundle


def test_retry_eventually_succeeds():
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 2:
            raise RuntimeError("transient")
        return "ok"

    assert with_retry(flaky, retries=2, backoff_ms=1) == "ok"


def test_retry_exhausted():
    def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(RetryError):
        with_retry(always_fail, retries=1, backoff_ms=1)


def test_classical_vs_llm_ensemble():
    model = train_default_model()
    req = ProjectRequest(
        project_id="t1",
        title="AI agent with RAG",
        description="Foundry LangGraph agent over PII corpus",
        data_classification="restricted",
        handles_pii=True,
        internet_facing=True,
        third_party_vendors=["azure-openai"],
        tech_stack=["langgraph", "foundry"],
    )
    llm = score_risk_llm(req)
    classical = model.predict(req)
    combined = ensemble(llm, classical)
    assert combined.method == "ensemble"
    assert combined.level.value in {"high", "critical"}


def test_end_to_end_analyze():
    agent = SbDAgent(standards_dir=STANDARDS, prompt_version="v1.1.0")
    req = ProjectRequest(
        project_id="e2e",
        title="Security-by-Design AI agent",
        description="LangGraph multi-agent on Microsoft Foundry with RAG",
        data_classification="restricted",
        handles_pii=True,
        internet_facing=False,
        third_party_vendors=["azure-openai"],
        tech_stack=["langgraph", "foundry", "python"],
    )
    result = agent.analyze(req)
    assert result.requirements
    assert result.threats
    assert any(r.req_id.startswith("AI-") for r in result.requirements)
    assert "latency_ms" in result.metrics
    assert result.prompt_version == "v1.1.0"
    assert result.metrics["estimated_cost_usd"] >= 0


def test_golden_file_valid():
    cases = json.loads((ROOT / "data" / "golden" / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 5
    for case in cases:
        ProjectRequest.model_validate(case["request"])

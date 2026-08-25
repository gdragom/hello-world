"""LangGraph-style multi-agent Security-by-Design pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from sbd_agent.agents import analyzer
from sbd_agent.models import AnalysisResult, ProjectRequest, RiskAssessment
from sbd_agent.observability.tracing import Tracer
from sbd_agent.prompts import load_prompt_bundle
from sbd_agent.rag.retriever import HybridRetriever
from sbd_agent.reliability.retries import with_retry, with_timeout
from sbd_agent.risk_classifier.model import (
    ClassicalRiskModel,
    ensemble,
    train_default_model,
)

AGENT_VERSION = "0.1.0"
DEFAULT_STANDARDS = (
    Path(__file__).resolve().parents[2] / "data" / "standards"
)


class AgentState(TypedDict, total=False):
    request: dict[str, Any]
    retrieved: list[dict[str, Any]]
    requirements: list[dict[str, Any]]
    threats: list[dict[str, Any]]
    coverage_notes: list[str]
    risk_llm: dict[str, Any]
    risk_classical: dict[str, Any]
    risk: dict[str, Any]
    metrics: dict[str, Any]
    prompt_version: str
    agent_version: str


class SbDAgent:
    def __init__(
        self,
        standards_dir: Path | None = None,
        prompt_version: str | None = None,
        classical_model: ClassicalRiskModel | None = None,
        timeout_ms: float = 5000,
    ) -> None:
        self.retriever = HybridRetriever.from_directory(standards_dir or DEFAULT_STANDARDS)
        self.prompt_bundle = load_prompt_bundle(prompt_version)
        self.prompt_version = self.prompt_bundle["version"]
        self.classical = classical_model or train_default_model()
        self.timeout_ms = timeout_ms
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("requirements", self._requirements)
        graph.add_node("threats", self._threats)
        graph.add_node("risk", self._risk)
        graph.add_node("finalize", self._finalize)
        graph.set_entry_point("retrieve")
        graph.add_edge("retrieve", "requirements")
        graph.add_edge("requirements", "threats")
        graph.add_edge("threats", "risk")
        graph.add_edge("risk", "finalize")
        graph.add_edge("finalize", END)
        return graph.compile()

    def _retrieve(self, state: AgentState) -> AgentState:
        tracer: Tracer = state["metrics"]["_tracer"]  # type: ignore[assignment]
        request = ProjectRequest.model_validate(state["request"])
        with tracer.span("retrieve", top_k=5):
            query = self._build_retrieval_query(request)
            chunks = with_retry(
                lambda: with_timeout(
                    lambda: self.retriever.retrieve(query, top_k=5),
                    self.timeout_ms,
                )
            )
        return {"retrieved": [c.model_dump() for c in chunks]}

    def _requirements(self, state: AgentState) -> AgentState:
        tracer: Tracer = state["metrics"]["_tracer"]  # type: ignore[assignment]
        request = ProjectRequest.model_validate(state["request"])
        from sbd_agent.models import RetrievedChunk

        retrieved = [RetrievedChunk.model_validate(c) for c in state.get("retrieved", [])]
        with tracer.span("requirements"):
            reqs, notes, tin, tout = analyzer.analyze_requirements(
                request, retrieved, self.prompt_bundle
            )
            tracer.add_tokens(tin, tout)
        return {
            "requirements": [r.model_dump() for r in reqs],
            "coverage_notes": notes,
        }

    def _threats(self, state: AgentState) -> AgentState:
        tracer: Tracer = state["metrics"]["_tracer"]  # type: ignore[assignment]
        request = ProjectRequest.model_validate(state["request"])
        from sbd_agent.models import RetrievedChunk

        retrieved = [RetrievedChunk.model_validate(c) for c in state.get("retrieved", [])]
        with tracer.span("threats"):
            threats, tin, tout = analyzer.analyze_threats(
                request, retrieved, self.prompt_bundle
            )
            tracer.add_tokens(tin, tout)
        return {"threats": [t.model_dump() for t in threats]}

    def _risk(self, state: AgentState) -> AgentState:
        tracer: Tracer = state["metrics"]["_tracer"]  # type: ignore[assignment]
        request = ProjectRequest.model_validate(state["request"])
        with tracer.span("risk"):
            llm = analyzer.score_risk_llm(request)
            classical = self.classical.predict(request)
            combined = ensemble(llm, classical)
            tracer.add_tokens(80, 40)
        return {
            "risk_llm": llm.model_dump(),
            "risk_classical": classical.model_dump(),
            "risk": combined.model_dump(),
        }

    def _finalize(self, state: AgentState) -> AgentState:
        tracer: Tracer = state["metrics"]["_tracer"]  # type: ignore[assignment]
        tracer.metrics.prompt_version = self.prompt_version
        tracer.metrics.agent_version = AGENT_VERSION
        metrics = tracer.metrics.to_dict()
        metrics["risk_llm"] = state.get("risk_llm")
        metrics["risk_classical"] = state.get("risk_classical")
        return {
            "metrics": metrics,
            "prompt_version": self.prompt_version,
            "agent_version": AGENT_VERSION,
        }

    @staticmethod
    def _build_retrieval_query(request: ProjectRequest) -> str:
        """Expand structured SbD fields into retrieval terms (metadata-aware RAG)."""
        parts = [
            request.title,
            request.description,
            request.data_classification,
            " ".join(request.tech_stack),
            "authentication authorization identity access MFA",
            "encryption data protection",
            "security logging monitoring",
        ]
        if request.handles_pii:
            parts.append("PII minimization retention log redaction personal data")
        if request.internet_facing:
            parts.append("internet facing WAF edge protection secure SDLC application security testing")
        if request.third_party_vendors:
            parts.append(
                "vendor risk assessment third party "
                + " ".join(request.third_party_vendors)
            )
        blob = f"{request.title} {request.description} {' '.join(request.tech_stack)}".lower()
        if any(k in blob for k in ("ai", "llm", "agent", "rag", "foundry", "langgraph")):
            parts.append("AI LLM prompt injection RAG corpus tool abuse eval gates")
        if any(k in blob for k in ("kubernetes", "k8s", "container")):
            parts.append("kubernetes least privilege containers cloud security")
        return " ".join(parts)

    def analyze(self, request: ProjectRequest) -> AnalysisResult:
        tracer = Tracer()
        initial: AgentState = {
            "request": request.model_dump(),
            "metrics": {"_tracer": tracer},
        }
        final = self.graph.invoke(initial)
        return AnalysisResult(
            project_id=request.project_id,
            requirements=final.get("requirements", []),
            threats=final.get("threats", []),
            risk=RiskAssessment.model_validate(final["risk"]),
            retrieved=final.get("retrieved", []),
            coverage_notes=final.get("coverage_notes", []),
            prompt_version=final.get("prompt_version", self.prompt_version),
            agent_version=final.get("agent_version", AGENT_VERSION),
            metrics={k: v for k, v in final.get("metrics", {}).items() if k != "_tracer"},
        )

"""Heuristic / Foundry-ready LLM stub for offline CI and demos."""

from __future__ import annotations

import re
from typing import Any

from sbd_agent.models import (
    ProjectRequest,
    RetrievedChunk,
    RiskAssessment,
    RiskLevel,
    SecurityRequirement,
    ThreatFinding,
)
from sbd_agent.observability.tracing import estimate_tokens


def _has(text: str, *terms: str) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in terms)


def analyze_requirements(
    request: ProjectRequest,
    retrieved: list[RetrievedChunk],
    prompt_bundle: dict[str, Any],
) -> tuple[list[SecurityRequirement], list[str], int, int]:
    """Map project + retrieved standards into grounded requirements."""
    blob = f"{request.title} {request.description} {' '.join(request.tech_stack)}"
    reqs: list[SecurityRequirement] = []
    notes: list[str] = []

    citation_map = {c.doc_id.split("#")[0]: c.citation for c in retrieved}
    default_cite = retrieved[0].citation if retrieved else "internal-standard"

    def add(req_id: str, title: str, rationale: str, priority: RiskLevel, doc_key: str) -> None:
        reqs.append(
            SecurityRequirement(
                req_id=req_id,
                title=title,
                rationale=rationale,
                citation=citation_map.get(doc_key, default_cite),
                priority=priority,
            )
        )

    add("AUTH-01", "Strong authentication", "All apps need verified identity.", RiskLevel.HIGH, "identity_access")
    add("LOG-01", "Security logging", "Retain auditable security events.", RiskLevel.MEDIUM, "logging_monitoring")
    add("ENC-01", "Encryption in transit and at rest", "Protect data confidentiality.", RiskLevel.HIGH, "data_protection")

    if request.handles_pii or _has(blob, "pii", "personal data", "gdpr"):
        add("PII-01", "PII minimization and retention", "Limit collection and retention of personal data.", RiskLevel.CRITICAL, "data_protection")
        add("PII-02", "Log redaction for PII", "Do not write raw PII into logs or traces.", RiskLevel.HIGH, "logging_monitoring")

    if request.internet_facing:
        add("NET-01", "Edge protection and WAF", "Internet-facing surfaces need abuse protection.", RiskLevel.HIGH, "network_security")
        add("SEC-01", "Secure SDLC / AppSec testing", "SAST/DAST and threat modeling before release.", RiskLevel.HIGH, "secure_sdlc")

    if request.third_party_vendors:
        add("VR-01", "Vendor risk assessment", "Third parties require due diligence and contracts.", RiskLevel.HIGH, "vendor_risk")

    if _has(blob, "ai", "llm", "agent", "rag", "foundry", "langgraph"):
        add("AI-01", "AI threat modeling", "Model prompt injection and tool abuse.", RiskLevel.HIGH, "ai_llm_security")
        add("AI-02", "RAG corpus controls", "Minimize sensitive data in retrieval indexes.", RiskLevel.HIGH, "ai_llm_security")
        add("AI-03", "Eval gates in CI", "Regressions on safety/quality must fail the pipeline.", RiskLevel.MEDIUM, "ai_llm_security")

    if _has(blob, "kubernetes", "k8s", "container"):
        add("K8S-01", "Kubernetes least privilege", "Restrict service accounts and network policies.", RiskLevel.HIGH, "cloud_security")

    if request.data_classification.lower() in {"", "unknown"}:
        notes.append("Missing data classification — coverage gap flagged by prompt policy.")

    # Token accounting from prompt + response heuristic
    prompt_text = prompt_bundle.get("system", "") + blob + "".join(c.text for c in retrieved)
    out_text = " ".join(r.title for r in reqs)
    return reqs, notes, estimate_tokens(prompt_text), estimate_tokens(out_text)


def analyze_threats(
    request: ProjectRequest,
    retrieved: list[RetrievedChunk],
    prompt_bundle: dict[str, Any],
) -> tuple[list[ThreatFinding], int, int]:
    blob = f"{request.title} {request.description}"
    threats: list[ThreatFinding] = []

    threats.append(
        ThreatFinding(
            threat_id="T-AUTH",
            title="Account takeover",
            description="Weak auth or session handling enables impersonation.",
            likelihood=RiskLevel.MEDIUM if request.internet_facing else RiskLevel.LOW,
            impact=RiskLevel.HIGH,
            mitigations=["MFA", "secure session cookies", "anomaly detection"],
        )
    )

    if request.handles_pii:
        threats.append(
            ThreatFinding(
                threat_id="T-EXFIL",
                title="Sensitive data exfiltration",
                description="Misconfigured access or logging leaks PII.",
                likelihood=RiskLevel.MEDIUM,
                impact=RiskLevel.CRITICAL,
                mitigations=["DLP", "encryption", "least privilege", "log redaction"],
            )
        )

    if request.third_party_vendors:
        threats.append(
            ThreatFinding(
                threat_id="T-VENDOR",
                title="Third-party compromise",
                description="Vendor breach impacts confidentiality of shared data.",
                likelihood=RiskLevel.MEDIUM,
                impact=RiskLevel.HIGH,
                mitigations=["vendor assessment", "contractual controls", "scoped credentials"],
            )
        )

    if re.search(r"\b(ai|llm|agent|rag|foundry)\b", blob, re.I):
        threats.append(
            ThreatFinding(
                threat_id="T-INJECT",
                title="Prompt injection / tool abuse",
                description="Untrusted content steers the agent to misuse tools or exfiltrate data.",
                likelihood=RiskLevel.HIGH,
                impact=RiskLevel.HIGH,
                mitigations=["allowlisted tools", "human-in-the-loop", "output filtering", "sandbox"],
            )
        )

    prompt_text = prompt_bundle.get("threat_instructions", "") + blob
    out_text = " ".join(t.title for t in threats)
    return threats, estimate_tokens(prompt_text), estimate_tokens(out_text)


def score_risk_llm(request: ProjectRequest) -> RiskAssessment:
    score = 0.15
    factors: list[str] = []
    if request.internet_facing:
        score += 0.25
        factors.append("internet_facing")
    if request.handles_pii:
        score += 0.3
        factors.append("handles_pii")
    if request.third_party_vendors:
        score += 0.15
        factors.append("third_party_vendors")
    if request.data_classification.lower() in {"confidential", "restricted", "secret"}:
        score += 0.15
        factors.append(f"classification:{request.data_classification}")
    blob = f"{request.title} {request.description}".lower()
    if any(k in blob for k in ("ai", "llm", "agent", "rag")):
        score += 0.1
        factors.append("ai_components")
    score = min(1.0, score)
    if score >= 0.85:
        level = RiskLevel.CRITICAL
    elif score >= 0.65:
        level = RiskLevel.HIGH
    elif score >= 0.4:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW
    return RiskAssessment(level=level, score=score, method="llm", factors=factors)

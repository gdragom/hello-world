"""Shared typed models for SbD analysis."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectRequest(BaseModel):
    """Input from a Security-by-Design project requestor."""

    project_id: str
    title: str
    description: str
    data_classification: str = "internal"
    handles_pii: bool = False
    internet_facing: bool = False
    cloud_provider: str = "azure"
    third_party_vendors: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)


class RetrievedChunk(BaseModel):
    doc_id: str
    title: str
    text: str
    score: float
    citation: str


class SecurityRequirement(BaseModel):
    req_id: str
    title: str
    rationale: str
    citation: str
    priority: RiskLevel = RiskLevel.MEDIUM


class ThreatFinding(BaseModel):
    threat_id: str
    title: str
    description: str
    likelihood: RiskLevel
    impact: RiskLevel
    mitigations: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    level: RiskLevel
    score: float = Field(ge=0.0, le=1.0)
    method: str  # "llm" | "classical" | "ensemble"
    factors: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    project_id: str
    requirements: list[SecurityRequirement]
    threats: list[ThreatFinding]
    risk: RiskAssessment
    retrieved: list[RetrievedChunk]
    coverage_notes: list[str] = Field(default_factory=list)
    prompt_version: str
    agent_version: str
    metrics: dict[str, Any] = Field(default_factory=dict)

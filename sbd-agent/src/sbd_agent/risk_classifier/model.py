"""Classical ML risk classifier baseline vs LLM scoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

from sbd_agent.models import ProjectRequest, RiskAssessment, RiskLevel


FEATURE_KEYS = (
    "internet_facing",
    "handles_pii",
    "vendor_count",
    "tech_count",
    "class_restricted",
    "mentions_ai",
    "mentions_cloud",
    "desc_len_bucket",
)


def _features(request: ProjectRequest) -> dict[str, float]:
    blob = f"{request.title} {request.description}".lower()
    classification = request.data_classification.lower()
    return {
        "internet_facing": float(request.internet_facing),
        "handles_pii": float(request.handles_pii),
        "vendor_count": float(len(request.third_party_vendors)),
        "tech_count": float(len(request.tech_stack)),
        "class_restricted": float(
            classification in {"confidential", "restricted", "secret"}
        ),
        "mentions_ai": float(any(k in blob for k in ("ai", "llm", "agent", "rag", "foundry"))),
        "mentions_cloud": float(any(k in blob for k in ("azure", "aws", "gcp", "k8s", "kubernetes"))),
        "desc_len_bucket": float(min(4, len(request.description) // 80)),
    }


@dataclass
class ClassicalRiskModel:
    pipeline: Pipeline
    labels: LabelEncoder

    def predict(self, request: ProjectRequest) -> RiskAssessment:
        x = _features(request)
        pred = self.pipeline.predict([x])[0]
        proba = self.pipeline.predict_proba([x])[0]
        level = RiskLevel(self.labels.inverse_transform([pred])[0])
        score = float(np.max(proba))
        # Map class confidence into a comparable 0-1 risk score band
        level_weight = {
            RiskLevel.LOW: 0.2,
            RiskLevel.MEDIUM: 0.45,
            RiskLevel.HIGH: 0.7,
            RiskLevel.CRITICAL: 0.9,
        }[level]
        return RiskAssessment(
            level=level,
            score=round(0.5 * score + 0.5 * level_weight, 3),
            method="classical",
            factors=[f"{k}={v}" for k, v in x.items() if v],
        )


def _training_rows() -> list[tuple[ProjectRequest, str]]:
    """Small synthetic set — enough for a reproducible baseline comparison."""
    rows: list[tuple[ProjectRequest, str]] = []

    def R(**kwargs) -> ProjectRequest:
        base = dict(
            project_id="train",
            title="t",
            description="d",
            data_classification="internal",
            handles_pii=False,
            internet_facing=False,
            third_party_vendors=[],
            tech_stack=[],
        )
        base.update(kwargs)
        return ProjectRequest(**base)

    # low
    for i in range(8):
        rows.append(
            (
                R(
                    project_id=f"l{i}",
                    title="Internal wiki",
                    description="Internal documentation site for employees only",
                    tech_stack=["sharepoint"],
                ),
                "low",
            )
        )
    # medium
    for i in range(8):
        rows.append(
            (
                R(
                    project_id=f"m{i}",
                    title="Cloud reporting",
                    description="Azure dashboard for operations metrics",
                    internet_facing=False,
                    tech_stack=["azure", "powerbi"],
                    data_classification="confidential",
                ),
                "medium",
            )
        )
    # high
    for i in range(8):
        rows.append(
            (
                R(
                    project_id=f"h{i}",
                    title="Customer portal",
                    description="Internet facing portal with authentication",
                    internet_facing=True,
                    handles_pii=True,
                    tech_stack=["react", "api"],
                    third_party_vendors=["cdn-vendor"],
                ),
                "high",
            )
        )
    # critical
    for i in range(8):
        rows.append(
            (
                R(
                    project_id=f"c{i}",
                    title="AI agent with RAG",
                    description="LangGraph agent on Foundry retrieving regulated PII corpus",
                    internet_facing=True,
                    handles_pii=True,
                    data_classification="restricted",
                    tech_stack=["langgraph", "azure", "foundry"],
                    third_party_vendors=["model-provider", "vector-db"],
                ),
                "critical",
            )
        )
    return rows


def train_default_model() -> ClassicalRiskModel:
    rows = _training_rows()
    X = [_features(r) for r, _ in rows]
    y_raw = [label for _, label in rows]
    labels = LabelEncoder()
    y = labels.fit_transform(y_raw)
    pipeline = Pipeline(
        [
            ("vec", DictVectorizer(sparse=False)),
            (
                "clf",
                LogisticRegression(max_iter=1000),
            ),
        ]
    )
    pipeline.fit(X, y)
    return ClassicalRiskModel(pipeline=pipeline, labels=labels)


def save_model(model: ClassicalRiskModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": model.pipeline, "labels": model.labels}, path)


def load_model(path: Path) -> ClassicalRiskModel:
    payload = joblib.load(path)
    return ClassicalRiskModel(pipeline=payload["pipeline"], labels=payload["labels"])


def ensemble(llm: RiskAssessment, classical: RiskAssessment) -> RiskAssessment:
    score = 0.6 * llm.score + 0.4 * classical.score
    if score >= 0.85:
        level = RiskLevel.CRITICAL
    elif score >= 0.65:
        level = RiskLevel.HIGH
    elif score >= 0.4:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW
    return RiskAssessment(
        level=level,
        score=round(score, 3),
        method="ensemble",
        factors=sorted(set(llm.factors + classical.factors)),
    )

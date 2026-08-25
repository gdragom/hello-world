"""OpenTelemetry-style tracing, token/cost accounting, prompt version tags."""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

# Heuristic USD per 1K tokens for offline/mock pricing (Foundry GPT-class placeholder).
USD_PER_1K_INPUT = 0.0005
USD_PER_1K_OUTPUT = 0.0015


@dataclass
class SpanRecord:
    name: str
    trace_id: str
    start_ms: float
    end_ms: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.end_ms is None:
            return 0.0
        return self.end_ms - self.start_ms


@dataclass
class RunMetrics:
    trace_id: str
    spans: list[SpanRecord] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    prompt_version: str = ""
    agent_version: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        return (self.input_tokens / 1000.0) * USD_PER_1K_INPUT + (
            self.output_tokens / 1000.0
        ) * USD_PER_1K_OUTPUT

    @property
    def total_latency_ms(self) -> float:
        if not self.spans:
            return 0.0
        starts = [s.start_ms for s in self.spans]
        ends = [s.end_ms or s.start_ms for s in self.spans]
        return max(ends) - min(starts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "latency_ms": round(self.total_latency_ms, 2),
            "prompt_version": self.prompt_version,
            "agent_version": self.agent_version,
            "spans": [
                {
                    "name": s.name,
                    "duration_ms": round(s.duration_ms, 2),
                    "attributes": s.attributes,
                }
                for s in self.spans
            ],
        }


class Tracer:
    def __init__(self) -> None:
        self.metrics = RunMetrics(trace_id=uuid.uuid4().hex)

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[SpanRecord]:
        record = SpanRecord(
            name=name,
            trace_id=self.metrics.trace_id,
            start_ms=time.perf_counter() * 1000,
            attributes=dict(attributes),
        )
        self.metrics.spans.append(record)
        try:
            yield record
        finally:
            record.end_ms = time.perf_counter() * 1000

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.metrics.input_tokens += input_tokens
        self.metrics.output_tokens += output_tokens


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) for offline cost accounting."""
    return max(1, len(text) // 4)

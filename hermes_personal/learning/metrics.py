from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Sequence


@dataclass(frozen=True)
class LearningExecutionMetric:
    metric_id: str
    version_id: str
    workflow_type: str
    success: bool
    corrections_count: int = 0
    approved: bool = True
    latency_ms: float = 0.0
    cost_minor_units: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class VersionEffectivenessSummary:
    version_id: str
    sample_count: int
    status: Literal["insufficient_data", "measured"]
    success_rate: float | None = None
    correction_rate: float | None = None
    approval_rate: float | None = None
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    average_cost_minor_units: float | None = None


def _percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_v[int(k)]
    d0 = sorted_v[int(f)] * (c - k)
    d1 = sorted_v[int(c)] * (k - f)
    return d0 + d1


class LearningMetricsEngine:
    """Aggregates execution metrics by learning version to measure real-world performance without weight modification."""

    def __init__(self) -> None:
        self._metrics: list[LearningExecutionMetric] = []

    def record_metric(self, metric: LearningExecutionMetric) -> None:
        self._metrics.append(metric)

    def calculate_effectiveness(
        self,
        version_id: str,
        min_samples: int = 3,
    ) -> VersionEffectivenessSummary:
        version_samples = [m for m in self._metrics if m.version_id == version_id]
        count = len(version_samples)

        if count < min_samples:
            return VersionEffectivenessSummary(
                version_id=version_id,
                sample_count=count,
                status="insufficient_data",
            )

        successes = sum(1 for m in version_samples if m.success)
        corrections = sum(m.corrections_count for m in version_samples)
        approvals = sum(1 for m in version_samples if m.approved)
        latencies = [m.latency_ms for m in version_samples]
        costs = [m.cost_minor_units for m in version_samples]

        return VersionEffectivenessSummary(
            version_id=version_id,
            sample_count=count,
            status="measured",
            success_rate=successes / count,
            correction_rate=corrections / count,
            approval_rate=approvals / count,
            p50_latency_ms=_percentile(latencies, 50.0),
            p95_latency_ms=_percentile(latencies, 95.0),
            average_cost_minor_units=sum(costs) / count,
        )

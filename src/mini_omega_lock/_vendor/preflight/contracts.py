# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Shared Pydantic contracts for the preflight layer.

These types are the stable interface between the two preflight sub-units
(analytical `mini_antemortem`, empirical `mini_omega_lock`) and the main
`omegaprompt` calibration pipeline. External repositories implementing the
full sub-units must emit records conforming to these shapes.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PreflightSeverity(str, Enum):
    """Severity of a preflight finding.

    BLOCKER findings abort the run under guarded execution profile.
    HIGH findings force an adaptation override (e.g., raise `min_kc4`).
    MEDIUM findings are recorded; adaptation is advisory.
    LOW findings are noted only; no parameter change.
    """

    BLOCKER = "blocker"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PreflightStatus(str, Enum):
    """Overall preflight verdict.

    The verdict is computed deterministically from the collected findings:
    any BLOCKER -> ABORT; any HIGH -> ADAPT; else PROCEED.
    """

    PROCEED = "proceed"
    ADAPT = "adapt"
    ABORT = "abort"


class AnalyticalFinding(BaseModel):
    """One classification produced by the analytical preflight sub-unit.

    Mirrors the shape of :class:`mini_omega_lock._vendor.domain.judge.JudgeResult`'s
    sibling in antemortem-cli: each trap carries a label, a severity, a
    free-form note, and an optional remediation hint the adaptation
    layer consumes.
    """

    model_config = ConfigDict(extra="forbid")

    trap_id: str
    label: str  # REAL / GHOST / NEW / UNRESOLVED
    hypothesis: str
    severity: PreflightSeverity = PreflightSeverity.MEDIUM
    note: str = ""
    remediation: str = ""
    cite: str | None = None  # e.g. "variants.json:3-9"


class JudgeQualityMeasurement(BaseModel):
    """Empirical measurement of judge behaviour on a small probe set."""

    model_config = ConfigDict(extra="forbid")

    consistency: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="1.0 = same input produces same score; 0.0 = random.",
    )
    anchoring_usage: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of the declared scale the judge actually uses.",
    )
    scale_monotonic: bool = Field(
        default=True,
        description="bad < mid < good monotonicity over probe inputs.",
    )
    samples: int = 0


class EndpointMeasurement(BaseModel):
    """Empirical measurement of endpoint / adapter behaviour."""

    model_config = ConfigDict(extra="forbid")

    schema_reliability: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of STRICT_SCHEMA requests that parsed.",
    )
    context_budget_margin: float = Field(
        default=1.0,
        description=(
            "1.0 = largest call uses 0% of context; 0.0 = on the boundary; "
            "negative = overflow."
        ),
    )
    caching_active: bool = False
    silent_degradation_detected: bool = False


class PerformanceMeasurement(BaseModel):
    """Empirical measurement of pipeline performance projections."""

    model_config = ConfigDict(extra="forbid")

    mean_call_latency_ms: float = 0.0
    projected_wall_time_seconds: float = 0.0
    noise_floor: float = Field(
        default=0.0,
        ge=0.0,
        description="Absolute fitness standard deviation from repeating an evaluation at fixed params.",
    )


class PreflightReport(BaseModel):
    """Combined preflight report emitted by the two sub-units."""

    model_config = ConfigDict(extra="forbid")

    analytical_findings: list[AnalyticalFinding] = Field(default_factory=list)
    judge_quality: JudgeQualityMeasurement | None = None
    endpoint: EndpointMeasurement | None = None
    performance: PerformanceMeasurement | None = None

    status: PreflightStatus = PreflightStatus.PROCEED
    blocker_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Empty maps preserve unknown historical measurement state; warnings are
    # human text and must not serve as the machine-readable measurement flag.
    measurement_status: dict[str, Literal[
        "measured", "unmeasured", "insufficient_samples", "failed", "estimated", "not_applicable"
    ]] = Field(default_factory=dict)
    probe_accounting: dict[str, Any] = Field(default_factory=dict)

    def any_real_or_new(self) -> bool:
        return any(f.label in {"REAL", "NEW"} for f in self.analytical_findings)

    def worst_severity(self) -> PreflightSeverity:
        order = {
            PreflightSeverity.LOW: 0,
            PreflightSeverity.MEDIUM: 1,
            PreflightSeverity.HIGH: 2,
            PreflightSeverity.BLOCKER: 3,
        }
        if not self.analytical_findings:
            return PreflightSeverity.LOW
        worst = max(self.analytical_findings, key=lambda f: order[f.severity])
        return worst.severity

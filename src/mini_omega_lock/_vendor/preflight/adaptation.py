# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""AdaptationPlan - the shared contract between preflight and pipeline.

The plan carries parameter overrides that the main calibration consumes
before starting. Each override is derived deterministically from the
preflight measurements and analytical findings; the adaptation layer
never *weakens* the discipline (it may only raise thresholds, reduce
search budget, or narrow rubric weights).

Invariant (enforced by :func:`derive_adaptation_plan`):

- ``min_kc4_override`` is never lower than the caller-supplied default.
- ``max_gap_override`` is never higher than the caller-supplied default.
- ``rubric_weight_overrides`` only zero out dimensions; they do not
  reweight upward.
- ``schema_mode_fallback`` only moves STRICT_SCHEMA -> JSON_OBJECT, never
  the other direction.
- ``unlock_k_override`` is never larger than the caller-supplied default.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mini_omega_lock._vendor.domain.enums import ResponseSchemaMode
from mini_omega_lock._vendor.preflight.contracts import (
    AnalyticalFinding,
    PreflightReport,
    PreflightSeverity,
    PreflightStatus,
)


class ParameterOverride(BaseModel):
    """Record of one parameter override applied by the adaptation layer."""

    model_config = ConfigDict(extra="forbid")

    parameter: str
    default: Any
    applied: Any
    reason: str


class AdaptationPlan(BaseModel):
    """Parameter overrides the main pipeline consumes before running."""

    model_config = ConfigDict(extra="forbid")

    # Walk-forward gate
    min_kc4_override: float | None = None
    max_gap_override: float | None = None

    # Search
    unlock_k_override: int | None = None
    skip_axes: list[str] = Field(default_factory=list)

    # Evaluation
    rescore_count: int = 1
    rubric_weight_overrides: dict[str, float] = Field(default_factory=dict)
    schema_mode_fallback: ResponseSchemaMode | None = None
    judge_ensemble_shift: float | None = None

    # Scheduling
    candidate_budget_cap: int | None = None
    dataset_reorder_for_cache: bool = False

    # Ship gate escalation. Conditions like a small test slice can't be
    # repaired by widening parameters — the right response is to flag
    # the run as needing manual review and to surface a HOLD verdict
    # downstream rather than silently widen max_gap. Each entry is a
    # short reason string keyed off a finding.
    require_manual_review_reasons: list[str] = Field(default_factory=list)

    # Audit
    overrides: list[ParameterOverride] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    preserves_discipline: bool = True

    @property
    def requires_manual_review(self) -> bool:
        """True when the plan flagged any condition that cannot be auto-resolved."""
        return bool(self.require_manual_review_reasons)

    def split_overrides(self) -> tuple[list[ParameterOverride], list[ParameterOverride]]:
        """Partition recorded overrides into ``(applied, advisory)``.

        Reviewer P0: pre-fix every entry on ``self.overrides`` looked
        equally authoritative, but ``runtime.calibrate`` only consumes
        a subset (min_kc4, max_gap, unlock_k via apply_adaptation_plan).
        Other recorded overrides — rescore_count, schema_mode_fallback,
        skip_axes, judge_ensemble_shift, rubric_weight_overrides,
        candidate_budget_cap, dataset_reorder_for_cache — are advisory
        because no consumer wires them through. A reviewer reading the
        artifact can't tell which is which without this split.

        ``applied`` entries reach the search loop. ``advisory`` entries
        are recorded for reviewers but the pipeline behaviour is
        unchanged. Future work that wires an advisory override into
        the pipeline should move it to ``APPLIED_PARAMETERS``.
        """
        applied: list[ParameterOverride] = []
        advisory: list[ParameterOverride] = []
        for ov in self.overrides:
            if ov.parameter in APPLIED_PARAMETERS:
                applied.append(ov)
            else:
                advisory.append(ov)
        return applied, advisory


# Parameters whose AdaptationPlan overrides actually flow through
# ``runtime.calibrate`` -> ``apply_adaptation_plan`` -> the search
# loop or the ship-gate escalation. Anything else recorded on
# ``AdaptationPlan.overrides`` is advisory-only as of v1.x.
APPLIED_PARAMETERS: frozenset[str] = frozenset({
    "min_kc4",
    "max_gap",
    "unlock_k",
    "manual_review",
})


_NOISE_TO_KC4_FLOOR: tuple[tuple[float, float], ...] = (
    (0.05, 0.50),
    (0.15, 0.60),
    (0.25, 0.70),
    (0.35, 0.80),
)


def _adaptive_min_kc4(noise_floor: float, default: float) -> float:
    """Return a recommended KC-4 threshold given an observed noise floor."""
    best = default
    for threshold, kc4 in _NOISE_TO_KC4_FLOOR:
        if noise_floor >= threshold:
            best = max(best, kc4)
    return best


def derive_adaptation_plan(
    *,
    report: PreflightReport,
    default_min_kc4: float = 0.5,
    default_max_gap: float = 0.25,
    default_unlock_k: int = 3,
) -> AdaptationPlan:
    """Convert a :class:`PreflightReport` into a concrete plan.

    The derivation rules are pure functions of the report. Same report
    in, same plan out.
    """

    overrides: list[ParameterOverride] = []
    rationale: list[str] = []
    rubric_weight_overrides: dict[str, float] = {}
    skip_axes: list[str] = []
    schema_mode_fallback: ResponseSchemaMode | None = None
    judge_ensemble_shift: float | None = None

    # Walk-forward gate tightening from noise floor
    noise_floor = (
        report.performance.noise_floor if report.performance is not None else 0.0
    )
    recommended_kc4 = _adaptive_min_kc4(noise_floor, default_min_kc4)
    if recommended_kc4 > default_min_kc4:
        overrides.append(
            ParameterOverride(
                parameter="min_kc4",
                default=default_min_kc4,
                applied=recommended_kc4,
                reason=f"empirical noise floor {noise_floor:.3f} requires stronger Pearson",
            )
        )
        rationale.append(
            f"min_kc4 raised {default_min_kc4:.2f} -> {recommended_kc4:.2f} "
            f"(noise floor {noise_floor:.3f})"
        )

    # Walk-forward gap on small samples: previously we tried to widen
    # max_gap, but the apply step (line ~310) clamps to min(default,
    # override) so the widening was always silently negated. Worse, even
    # if it had landed it would have *weakened* the discipline. The
    # right response to a small test slice is the opposite:
    #
    #   1. don't widen anything — small samples need MORE caution, not
    #      less, around the gap threshold;
    #   2. require manual review so the artifact carries a clear signal
    #      downstream consumers (CI gates, ship recommendation logic)
    #      can key off rather than silently passing;
    #   3. emit a rationale entry recommending a larger held-out slice
    #      or paired/bootstrap validation mode.
    applied_max_gap = default_max_gap
    small_sample_finding = next(
        (
            f
            for f in report.analytical_findings
            if f.trap_id == "small_sample_kc4_power" and f.label in {"REAL", "NEW"}
        ),
        None,
    )
    require_manual_review_reasons: list[str] = []
    for metric, state in report.measurement_status.items():
        if state in {"failed", "insufficient_samples"}:
            require_manual_review_reasons.append(f"{metric}: measurement {state}; no quality pass established")
    if small_sample_finding is not None and small_sample_finding.severity in {
        PreflightSeverity.HIGH,
        PreflightSeverity.BLOCKER,
    }:
        require_manual_review_reasons.append(
            "small_sample_kc4_power: held-out slice is too small for KC-4 to "
            "have meaningful statistical power. Manual review required; "
            "pre-fix this branch widened max_gap, which weakened the "
            "discipline AND was silently clamped back to the default. "
            "Recommended remediation: enlarge held-out slice, or run with "
            "validation_mode='paired' / bootstrap CI on the metric."
        )
        rationale.append(
            "max_gap NOT widened on small sample (would weaken discipline); "
            "added require_manual_review reason instead."
        )

    # Judge noise: rescore_count
    rescore = 1
    if report.judge_quality is not None:
        consistency = report.judge_quality.consistency
        if consistency < 0.60:
            rescore = 3
            overrides.append(
                ParameterOverride(
                    parameter="rescore_count",
                    default=1,
                    applied=3,
                    reason=f"judge consistency {consistency:.2f} < 0.60 - take median of 3",
                )
            )
            rationale.append(f"rescore_count 1 -> 3 (judge consistency {consistency:.2f})")
        elif consistency < 0.80:
            rescore = 2
            overrides.append(
                ParameterOverride(
                    parameter="rescore_count",
                    default=1,
                    applied=2,
                    reason=f"judge consistency {consistency:.2f} < 0.80 - median of 2",
                )
            )
            rationale.append(f"rescore_count 1 -> 2 (judge consistency {consistency:.2f})")

    # Endpoint: schema fallback
    if report.endpoint is not None and report.endpoint.schema_reliability < 0.90:
        schema_mode_fallback = ResponseSchemaMode.JSON_OBJECT
        overrides.append(
            ParameterOverride(
                parameter="schema_mode",
                default=ResponseSchemaMode.STRICT_SCHEMA.value,
                applied=ResponseSchemaMode.JSON_OBJECT.value,
                reason=(
                    f"STRICT_SCHEMA reliability {report.endpoint.schema_reliability:.0%} "
                    "below 90% - fallback to JSON_OBJECT with post-parse validation"
                ),
            )
        )
        rationale.append(
            f"schema_mode STRICT_SCHEMA -> JSON_OBJECT "
            f"(reliability {report.endpoint.schema_reliability:.0%})"
        )

    # Rubric concentration: zero out the over-weighted dimension? No - that's too aggressive.
    # Instead: if a specific dim's scoring is unreliable (finding), zero it.
    # (The current analytical preflight flags concentration but does not name a dim
    # as unreliable. This branch is a hook for future per-dim reliability checks.)

    # Variants too homogeneous: skip the system_prompt axis from sensitivity
    variants_finding = next(
        (
            f
            for f in report.analytical_findings
            if f.trap_id == "variants_homogeneous" and f.label in {"REAL", "NEW"}
        ),
        None,
    )
    if variants_finding is not None:
        skip_axes.append("system_prompt_variant")
        rationale.append(
            "system_prompt_variant axis skipped from sensitivity (variants too homogeneous)"
        )

    # Endpoint: silent degradation detected - no automated override, but warn
    if report.endpoint is not None and report.endpoint.silent_degradation_detected:
        rationale.append(
            "silent capability degradation detected - see endpoint.degraded_capabilities"
        )

    # Judge quality: push ensemble weight toward RuleJudge when LLMJudge is weak
    if (
        report.judge_quality is not None
        and report.judge_quality.consistency < 0.70
    ):
        judge_ensemble_shift = 0.40
        overrides.append(
            ParameterOverride(
                parameter="judge_ensemble_shift",
                default=0.0,
                applied=0.40,
                reason=(
                    f"judge consistency {report.judge_quality.consistency:.2f} - "
                    "raise RuleJudge weight to 40%"
                ),
            )
        )
        rationale.append(
            f"judge_ensemble_shift 0.00 -> 0.40 "
            f"(judge consistency {report.judge_quality.consistency:.2f})"
        )

    # Wall-time cap: reduce unlock_k if projection is extreme
    unlock_override = default_unlock_k
    if (
        report.performance is not None
        and report.performance.projected_wall_time_seconds > 4 * 3600
        and default_unlock_k > 1
    ):
        unlock_override = max(1, default_unlock_k - 1)
        overrides.append(
            ParameterOverride(
                parameter="unlock_k",
                default=default_unlock_k,
                applied=unlock_override,
                reason=(
                    f"projected wall-time {report.performance.projected_wall_time_seconds/3600:.1f}h "
                    f"exceeds 4h - reduce unlock_k"
                ),
            )
        )
        rationale.append(
            f"unlock_k {default_unlock_k} -> {unlock_override} "
            f"(wall-time {report.performance.projected_wall_time_seconds/3600:.1f}h)"
        )

    plan = AdaptationPlan(
        min_kc4_override=recommended_kc4 if recommended_kc4 != default_min_kc4 else None,
        max_gap_override=applied_max_gap if applied_max_gap != default_max_gap else None,
        unlock_k_override=unlock_override if unlock_override != default_unlock_k else None,
        skip_axes=skip_axes,
        rescore_count=rescore,
        rubric_weight_overrides=rubric_weight_overrides,
        schema_mode_fallback=schema_mode_fallback,
        judge_ensemble_shift=judge_ensemble_shift,
        require_manual_review_reasons=require_manual_review_reasons,
        overrides=overrides,
        rationale=rationale,
        preserves_discipline=True,
    )
    return plan


def apply_adaptation_plan(
    plan: AdaptationPlan,
    *,
    min_kc4: float,
    max_gap: float,
    unlock_k: int,
) -> tuple[float, float, int]:
    """Apply the plan's walk-forward and search overrides to the caller's defaults.

    Returns the (min_kc4, max_gap, unlock_k) the main pipeline should
    actually use. Invariants are enforced here: the plan never weakens
    the discipline relative to the caller's configuration.
    """
    applied_kc4 = max(min_kc4, plan.min_kc4_override or min_kc4)
    applied_gap = min(max_gap, plan.max_gap_override or max_gap)
    applied_unlock = min(unlock_k, plan.unlock_k_override or unlock_k)
    return applied_kc4, applied_gap, applied_unlock

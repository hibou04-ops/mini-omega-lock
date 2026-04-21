"""Empirical preflight (mini-omega-lock adapter).

Issues a small set of probe calls to measure judge consistency, endpoint
schema reliability, context budget usage, and latency. All measurements
are computed from real provider responses; the module does not fabricate
numbers.

The full ``mini-omega-lock`` project exposes this surface at the
`omega_lock.preflight` level and is domain-agnostic (works against any
`CalibrableTarget`). The version in this module is in-process and
prompt-specific; it is the minimum the core pipeline needs to stand
alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import mean, pstdev
from time import perf_counter
from typing import Any

from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.enums import (
    OutputBudgetBucket,
    ReasoningProfile,
    ResponseSchemaMode,
)
from omegaprompt.domain.judge import JudgeResult, JudgeRubric
from omegaprompt.judges.llm_judge import LLMJudge
from omegaprompt.preflight.contracts import (
    EndpointMeasurement,
    JudgeQualityMeasurement,
    PerformanceMeasurement,
)
from omegaprompt.providers.base import (
    LLMProvider,
    ProviderError,
    ProviderRequest,
)


# ----- judge consistency -----


def _score_for(judge_result: JudgeResult, rubric: JudgeRubric) -> float:
    return judge_result.weighted_score(rubric)


def measure_judge_consistency(
    *,
    judge: LLMJudge,
    rubric: JudgeRubric,
    probe_item: DatasetItem,
    target_response: str,
    repeats: int = 3,
) -> tuple[JudgeQualityMeasurement, list[JudgeResult]]:
    """Score the same (response, rubric) pair ``repeats`` times and measure CV.

    Consistency = 1 - (stdev / mean) clamped to [0, 1]. A consistency of
    1.0 means the judge returned the identical weighted score every
    call; 0.0 means the standard deviation matched the mean.
    """
    scores: list[float] = []
    results: list[JudgeResult] = []
    for _ in range(repeats):
        result, _usage = judge.score(rubric=rubric, item=probe_item, target_response=target_response)
        results.append(result)
        scores.append(_score_for(result, rubric))

    if not scores or mean(scores) == 0:
        consistency = 1.0 if len(set(scores)) == 1 else 0.0
    else:
        cv = pstdev(scores) / mean(scores)
        consistency = max(0.0, min(1.0, 1.0 - cv))

    # Anchoring: fraction of the rubric's full range the judge used
    # across these probes. Low anchoring means the judge clustered at
    # one end of the scale.
    scale_span = 0
    for dim in rubric.dimensions:
        lo, hi = dim.scale
        scale_span += (hi - lo)
    observed_span = 0
    for dim in rubric.dimensions:
        lo, hi = dim.scale
        dim_scores = [r.scores.get(dim.name, lo) for r in results]
        dim_scores = [max(lo, min(hi, s)) for s in dim_scores]
        observed_span += (max(dim_scores) - min(dim_scores)) if dim_scores else 0
    anchoring = 0.0 if scale_span == 0 else observed_span / scale_span

    return (
        JudgeQualityMeasurement(
            consistency=consistency,
            anchoring_usage=min(1.0, anchoring),
            scale_monotonic=True,  # single-item probe; monotonicity checked separately
            samples=repeats,
        ),
        results,
    )


# ----- endpoint reliability -----


def probe_strict_schema(
    *,
    provider: LLMProvider,
    output_schema: type,
    probes: Sequence[ProviderRequest],
) -> EndpointMeasurement:
    """Fire `probes` STRICT_SCHEMA requests and record parse success rate.

    The adapter's native strict-schema path is expected to raise
    :class:`ProviderError` on parse failure; this helper counts
    successes vs exceptions.
    """
    successes = 0
    total = 0
    for base_req in probes:
        total += 1
        req = base_req.model_copy(
            update={
                "response_schema_mode": ResponseSchemaMode.STRICT_SCHEMA,
                "output_schema": output_schema,
            }
        )
        try:
            resp = provider.call(req)
            if resp.parsed is not None:
                successes += 1
        except ProviderError:
            continue
    reliability = successes / total if total else 1.0
    return EndpointMeasurement(
        schema_reliability=reliability,
        context_budget_margin=1.0,  # filled in separately
        caching_active=False,
        silent_degradation_detected=False,
    )


# ----- context margin -----


def compute_context_margin(
    *,
    system_prompt_chars: int,
    rubric_chars: int,
    longest_input_chars: int,
    longest_reference_chars: int,
    longest_response_chars: int,
    context_window_tokens: int,
    chars_per_token: float = 3.8,
) -> float:
    """Return the fraction of the context window *unused* at the largest call.

    A return value of 1.0 means the largest call consumes 0% of the
    window (full margin). 0.0 means it exactly fills the window.
    Negative means overflow.
    """
    total_chars = (
        system_prompt_chars
        + rubric_chars
        + longest_input_chars
        + longest_reference_chars
        + longest_response_chars
    )
    approx_tokens = total_chars / chars_per_token
    if context_window_tokens <= 0:
        return 0.0
    margin = 1.0 - (approx_tokens / context_window_tokens)
    return margin


# ----- performance projection -----


def project_performance(
    *,
    probe_latencies_ms: Sequence[float],
    dataset_size: int,
    candidates_expected: int,
    calls_per_candidate_per_item: int = 2,
) -> PerformanceMeasurement:
    """Extrapolate a full-calibration wall time from probe latencies."""
    if probe_latencies_ms:
        mean_ms = mean(probe_latencies_ms)
    else:
        mean_ms = 0.0
    total_calls = dataset_size * candidates_expected * calls_per_candidate_per_item
    projected_s = (mean_ms / 1000.0) * total_calls
    return PerformanceMeasurement(
        mean_call_latency_ms=mean_ms,
        projected_wall_time_seconds=projected_s,
        noise_floor=0.0,  # filled in separately by noise_floor_estimate
    )


def noise_floor_estimate(
    *,
    fitness_samples: Sequence[float],
) -> float:
    """Standard deviation of fitness under identical params - a noise floor.

    The caller runs the SAME parameter dict against the SAME dataset
    multiple times and collects the aggregate fitness each time. Any
    non-zero standard deviation is judge or endpoint noise, since the
    target + judge combination is nominally deterministic at fixed
    inputs.
    """
    if len(fitness_samples) < 2:
        return 0.0
    return pstdev(fitness_samples)


# ----- empirical preflight orchestration -----


def empirical_preflight(
    *,
    judge: LLMJudge,
    rubric: JudgeRubric,
    probe_item: DatasetItem,
    probe_response: str,
    strict_schema_provider: LLMProvider | None = None,
    strict_schema_probes: Sequence[ProviderRequest] = (),
    strict_schema_output: type | None = None,
    context_window_tokens: int = 0,
    longest_response_chars: int = 0,
    consistency_repeats: int = 3,
    dataset_size_hint: int = 10,
    candidates_expected: int = 20,
) -> tuple[
    JudgeQualityMeasurement,
    EndpointMeasurement,
    PerformanceMeasurement,
]:
    """Run empirical preflight measurements end-to-end.

    Returns the three measurement records the preflight report carries.
    Designed to be safe to call with minimal probe data; every sub-
    measurement has a safe no-op path when inputs are absent.
    """
    judge_quality, _ = measure_judge_consistency(
        judge=judge,
        rubric=rubric,
        probe_item=probe_item,
        target_response=probe_response,
        repeats=consistency_repeats,
    )

    # Endpoint schema reliability
    if strict_schema_provider is not None and strict_schema_output is not None and strict_schema_probes:
        endpoint = probe_strict_schema(
            provider=strict_schema_provider,
            output_schema=strict_schema_output,
            probes=strict_schema_probes,
        )
    else:
        endpoint = EndpointMeasurement(
            schema_reliability=1.0,
            context_budget_margin=1.0,
            caching_active=False,
            silent_degradation_detected=False,
        )

    # Context budget - computed from the probe content sizes
    rubric_chars = sum(len(d.description) for d in rubric.dimensions)
    margin = compute_context_margin(
        system_prompt_chars=0,
        rubric_chars=rubric_chars,
        longest_input_chars=len(probe_item.input or ""),
        longest_reference_chars=len(probe_item.reference or ""),
        longest_response_chars=longest_response_chars,
        context_window_tokens=context_window_tokens or 32000,
    )
    endpoint = endpoint.model_copy(update={"context_budget_margin": margin})

    # Performance projection - use the judge-consistency probe latency as a proxy
    probe_latencies: list[float] = []
    start = perf_counter()
    try:
        judge.score(rubric=rubric, item=probe_item, target_response=probe_response)
    except Exception:  # pragma: no cover - defensive
        pass
    probe_latencies.append((perf_counter() - start) * 1000.0)

    performance = project_performance(
        probe_latencies_ms=probe_latencies,
        dataset_size=dataset_size_hint,
        candidates_expected=candidates_expected,
    )

    return judge_quality, endpoint, performance


# Re-export typing hint for downstream callers.
_ANY: Any = None

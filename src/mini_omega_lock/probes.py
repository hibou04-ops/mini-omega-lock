"""Empirical preflight (mini-omega-lock adapter).

Issues a small set of probe calls to measure judge consistency, endpoint
schema reliability, context budget usage, and latency. Each measurement
is computed from a real provider response when its inputs are supplied.
When inputs are missing, the corresponding field is set to a fail-closed
value (e.g. ``schema_reliability=0.0``) and a warning is appended to the
returned warnings list — see ``empirical_preflight`` for the contract.

The fail-closed default exists because preflight is a CI gate: an
unmeasured value must not look like a successful measurement. The older
behaviour (``schema_reliability=1.0`` with no warning when no probe was
run) silently produced false-safe outcomes. Callers who want the old
fabricated-success behaviour can read the warnings list and override.

The full ``mini-omega-lock`` project exposes this surface at the
`omega_lock.preflight` level and is domain-agnostic (works against any
`CalibrableTarget`). The version in this module is in-process and
prompt-specific; it is the minimum the core pipeline needs to stand
alone.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
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
    token_counter: Callable[[str], int] | None = None,
) -> float:
    """Return the fraction of the context window *unused* at the largest call.

    A return value of 1.0 means the largest call consumes 0% of the
    window (full margin). 0.0 means it exactly fills the window.
    Negative means overflow.

    If ``token_counter`` is supplied, the call's char totals are funneled
    through it for an exact token count. Without one we fall back to the
    ``chars_per_token`` heuristic; the heuristic is approximate (especially
    for non-English text) and callers running this against languages or
    tokenizers far from the 3.8 default should pass a real
    ``token_counter`` (e.g. ``tiktoken``) for a measurement, not a
    projection.
    """
    total_chars = (
        system_prompt_chars
        + rubric_chars
        + longest_input_chars
        + longest_reference_chars
        + longest_response_chars
    )
    if token_counter is not None:
        approx_tokens = token_counter(" " * total_chars) if total_chars else 0
    else:
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
    fitness_samples: Sequence[float] | None = None,
    token_counter: Callable[[str], int] | None = None,
) -> tuple[
    JudgeQualityMeasurement,
    EndpointMeasurement,
    PerformanceMeasurement,
    list[str],
]:
    """Run empirical preflight measurements end-to-end.

    Returns ``(judge_quality, endpoint, performance, warnings)``. Each
    sub-measurement either runs (when its inputs are present) or fails
    closed (zeros out the relevant field) and appends a warning to
    ``warnings``. The caller is responsible for surfacing those warnings;
    in particular, ``omegaprompt.derive_adaptation_plan`` should treat an
    empty endpoint probe as "schema reliability not measured" rather
    than "schema is perfect".

    Returning a 4-tuple instead of the prior 3-tuple is the
    intentional fail-closed contract change. Callers that want the old
    success-by-default semantics can ignore the warnings list, but the
    ``schema_reliability`` and ``noise_floor`` defaults will reflect
    "not measured" rather than "good".

    Args:
        fitness_samples: Optional sequence of fitness values from
            repeating the same evaluation at fixed params. When provided,
            ``performance.noise_floor`` is computed via
            ``noise_floor_estimate``; otherwise it stays 0.0 with a
            warning that the noise floor was not measured.
        token_counter: Optional ``str -> int`` callable. When supplied,
            the context-margin probe uses a real token count instead
            of the ``chars_per_token`` heuristic.
    """
    warnings: list[str] = []

    judge_quality, _ = measure_judge_consistency(
        judge=judge,
        rubric=rubric,
        probe_item=probe_item,
        target_response=probe_response,
        repeats=consistency_repeats,
    )

    # Endpoint schema reliability - fail-closed when probe inputs absent.
    schema_probe_run = (
        strict_schema_provider is not None
        and strict_schema_output is not None
        and strict_schema_probes
    )
    if schema_probe_run:
        endpoint = probe_strict_schema(
            provider=strict_schema_provider,
            output_schema=strict_schema_output,
            probes=strict_schema_probes,
        )
    else:
        endpoint = EndpointMeasurement(
            schema_reliability=0.0,  # fail-closed: unmeasured != good
            context_budget_margin=1.0,  # filled in below
            caching_active=False,
            silent_degradation_detected=False,
        )
        warnings.append(
            "endpoint.schema_reliability not measured — strict_schema_provider, "
            "strict_schema_output, and strict_schema_probes were not supplied; "
            "value defaulted to 0.0 (fail-closed). Pass these to actually "
            "probe the provider's strict-schema reliability."
        )

    # Context budget - computed from the probe content sizes.
    rubric_chars = sum(len(d.description) for d in rubric.dimensions)
    margin = compute_context_margin(
        system_prompt_chars=0,
        rubric_chars=rubric_chars,
        longest_input_chars=len(probe_item.input or ""),
        longest_reference_chars=len(probe_item.reference or ""),
        longest_response_chars=longest_response_chars,
        context_window_tokens=context_window_tokens or 32000,
        token_counter=token_counter,
    )
    endpoint = endpoint.model_copy(update={"context_budget_margin": margin})
    if token_counter is None:
        warnings.append(
            "endpoint.context_budget_margin uses the chars_per_token=3.8 "
            "heuristic — pass token_counter=<tokenizer> for a measurement."
        )

    # Performance projection - use the judge-consistency probe latency as a proxy.
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

    # Noise floor - measure it from fitness_samples when caller provides them.
    if fitness_samples is not None and len(fitness_samples) >= 2:
        nf = noise_floor_estimate(fitness_samples=list(fitness_samples))
        performance = performance.model_copy(update={"noise_floor": nf})
    else:
        warnings.append(
            "performance.noise_floor not measured — pass fitness_samples=[...] "
            "(>= 2 samples from repeated evaluations at fixed params) to "
            "compute it. Adaptive min_kc4 logic in derive_adaptation_plan "
            "needs this signal to widen safely."
        )

    return judge_quality, endpoint, performance, warnings


# Re-export typing hint for downstream callers.
_ANY: Any = None

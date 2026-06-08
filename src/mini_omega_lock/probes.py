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

The broader sibling project, omega-lock (parameter-calibration
framework), tackles the domain-agnostic calibration surface (it works
against any ``CalibrableTarget``). The version in this module is
in-process and prompt-specific; it is the minimum the core pipeline
needs to stand alone.
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


def measure_gate_flip_rate(
    *,
    judge: LLMJudge,
    rubric: JudgeRubric,
    probe_item: DatasetItem,
    target_response: str,
    repeats: int = 5,
) -> dict[str, dict[str, float | int | bool]]:
    """Measure how often a hard gate flips on the same (response, rubric).

    Reviewer A-3#5 emphasis: in Prompt CI, soft score noise is annoying
    but a flipping hard gate is catastrophic — a candidate that
    sometimes passes and sometimes fails the same gate makes the whole
    ship verdict random. ``measure_judge_consistency`` only sees the
    weighted score, so a judge whose gate decisions wobble while
    keeping the score stable would look "consistent". This metric
    surfaces that gap directly.

    For each judge-mode hard gate the rubric declares, calls the judge
    ``repeats`` times on the same input and counts the fraction of
    consecutive call pairs where the gate's boolean outcome flipped.
    A flip rate of 0.0 means the gate is rock-solid; 1.0 means it
    flips every single call.

    Returns a dict keyed by gate name. Each entry has:

    - ``flip_rate``: fraction of the (repeats - 1) consecutive
      transitions that changed (0.0 - 1.0).
    - ``samples``: number of calls inspected (== ``repeats``).
    - ``majority``: True iff the gate passed in > half of the calls.
      Useful as a "what verdict would majority-vote produce" signal.
    - ``passes``: count of true outcomes across the calls.

    Defaults to 5 repeats (vs 3 in measure_judge_consistency) because
    detecting flip patterns needs more data than estimating a mean.
    """
    judge_gates = [g.name for g in rubric.hard_gates if g.evaluator == "judge"]
    if not judge_gates:
        return {}

    histories: dict[str, list[bool]] = {gate: [] for gate in judge_gates}
    for _ in range(max(2, repeats)):
        result, _usage = judge.score(
            rubric=rubric, item=probe_item, target_response=target_response
        )
        for gate in judge_gates:
            value = result.gate_results.get(gate)
            if value is None:
                # Treat absence as False — a missing gate is a structural
                # judge failure, not a passing gate. (LLMJudge from PR1
                # raises on this earlier; here we belt-and-brace in case
                # a future judge implementation skips the check.)
                value = False
            histories[gate].append(bool(value))

    out: dict[str, dict[str, float | int | bool]] = {}
    for gate, history in histories.items():
        n = len(history)
        flips = sum(
            1 for i in range(1, n) if history[i] != history[i - 1]
        )
        flip_rate = flips / max(1, n - 1)
        passes = sum(1 for v in history if v)
        out[gate] = {
            "flip_rate": flip_rate,
            "samples": n,
            "majority": passes * 2 > n,
            "passes": passes,
        }
    return out


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
            # Fail-closed: a single-item consistency probe CANNOT measure
            # bad < mid < good monotonicity. The pre-fix value was a
            # hardcoded True, which rubber-stamped a property that was
            # never tested. Use ``measure_scale_monotonicity`` against an
            # ordered fixture (or pass ``monotonic_examples=`` to
            # ``empirical_preflight``) to actually measure this.
            scale_monotonic=False,
            samples=repeats,
        ),
        results,
    )


def measure_scale_monotonicity(
    *,
    judge: LLMJudge,
    rubric: JudgeRubric,
    ordered_examples: Sequence[tuple[DatasetItem, str]],
) -> bool:
    """Verify the judge preserves a known bad < mid < good ordering.

    ``ordered_examples`` is a sequence of ``(item, response)`` pairs in
    ascending quality order — index 0 is the worst, index -1 the best.
    The judge scores each pair once; this function returns ``True``
    iff the resulting weighted scores are non-decreasing in the
    declared order.

    Two examples (bad < good) is the minimum but produces a weak signal;
    three or more (bad < mid < good) is recommended.

    Returns:
        bool. ``True`` iff scores are non-decreasing across the ordering.
        ``False`` if any earlier example outscored a later one — that
        means the judge's ordering disagrees with the declared scale.
    """
    if len(ordered_examples) < 2:
        raise ValueError(
            "measure_scale_monotonicity requires at least 2 ordered_examples "
            "(ideally 3+: bad < mid < good)."
        )
    scores: list[float] = []
    for item, response in ordered_examples:
        result, _ = judge.score(rubric=rubric, item=item, target_response=response)
        scores.append(_score_for(result, rubric))
    return all(scores[i] <= scores[i + 1] for i in range(len(scores) - 1))


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

    Raises:
        ValueError: When ``probes`` is empty. A library helper that
            silently returns ``reliability=1.0`` for "no measurement"
            would be exactly the false-safe default the package is
            built to avoid. ``empirical_preflight`` catches the empty
            case earlier and converts it into a fail-closed warning;
            direct callers must hand in at least one probe.
    """
    if not probes:
        raise ValueError(
            "probe_strict_schema requires at least one ProviderRequest in `probes`. "
            "An empty list cannot be measured — call empirical_preflight() instead "
            "if you want a fail-closed default + warning, or supply real probes."
        )
    successes = 0
    total = 0
    none_count = 0
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
            else:
                # A response that came back WITHOUT raising ProviderError
                # but with parsed=None is a *silent* degradation: the
                # endpoint accepted the strict-schema request, returned
                # 200-shaped output, yet produced nothing parseable. This
                # is exactly the false-safe the package exists to catch —
                # it is NOT the same as an explicit ProviderError (which
                # is a loud, expected failure already reflected in the
                # reliability rate).
                none_count += 1
        except ProviderError:
            continue
    reliability = successes / total
    return EndpointMeasurement(
        schema_reliability=reliability,
        context_budget_margin=1.0,  # filled in separately
        caching_active=False,
        # Flip to True only when at least one probe silently returned
        # parsed=None without raising. The unprobed / fail-closed path in
        # empirical_preflight keeps this False but warns that degradation
        # was not probed.
        silent_degradation_detected=none_count > 0,
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
    """Length-based projection of fraction of the context window unused.

    A return value of 1.0 means the largest call consumes 0% of the
    window (full margin). 0.0 means it exactly fills the window.
    Negative means overflow.

    This is a **projection**, not a tokenizer-exact measurement. The
    char counts are divided by ``chars_per_token`` (default 3.8). The
    heuristic is approximate — especially for non-English text, code,
    numerics, and mixed scripts (Korean + English). For an exact
    measurement, call :func:`compute_context_margin_from_texts` with a
    real tokenizer.

    Note:
        ``token_counter`` is accepted for backwards compatibility but is
        applied to a synthetic whitespace string of length ``total_chars``,
        which is **not** equivalent to tokenizing real text. If supplied,
        it is now ignored; pass real texts to
        :func:`compute_context_margin_from_texts` instead.
    """
    if token_counter is not None:
        # Pre-fix behaviour ran ``token_counter(" " * total_chars)`` which
        # produces tokens-of-spaces, not the actual text the caller cares
        # about. Silently giving them that number was worse than ignoring
        # the counter — they would think it was tokenizer-exact when it
        # was not. Direction: ignore here, route to *_from_texts for real
        # tokenization. (No exception so existing callers keep running;
        # the *_from_texts variant is documented in the docstring.)
        pass
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


def compute_context_margin_from_texts(
    *,
    system_prompts: Sequence[str] = (),
    rubric_text: str = "",
    inputs: Sequence[str] = (),
    references: Sequence[str] = (),
    candidate_responses: Sequence[str] = (),
    context_window_tokens: int,
    token_counter: Callable[[str], int],
) -> float:
    """Tokenizer-exact context margin from the actual texts of the largest call.

    Each ``Sequence[str]`` argument is a population; the function picks
    the largest member of each (by token count) and sums them. This
    matches the worst-case "longest variant" framing of
    :func:`compute_context_margin` while using real tokenization rather
    than a chars-per-token heuristic.

    Args:
        system_prompts: Population of system prompt variants under test.
            The longest is treated as the worst case.
        rubric_text: Concatenated rubric body (dimensions + hard gates +
            descriptions). One-shot, not a population.
        inputs: Dataset input texts. Largest used.
        references: Dataset reference texts. Largest used; can be empty.
        candidate_responses: Observed candidate response texts. Largest
            used; can be empty if no responses sampled yet.
        context_window_tokens: Provider context window in tokens.
        token_counter: Real ``str -> int`` tokenizer (e.g. ``tiktoken``,
            ``anthropic``'s tokenizer, ``transformers`` AutoTokenizer).
            Required — this function exists *because* the caller has one.

    Returns:
        ``1 - (longest_call_tokens / context_window_tokens)``. Negative
        means overflow.
    """
    if context_window_tokens <= 0:
        return 0.0

    def _largest(texts: Sequence[str]) -> int:
        if not texts:
            return 0
        return max(token_counter(t) for t in texts)

    prompt_tokens = _largest(system_prompts)
    input_tokens = _largest(inputs)
    reference_tokens = _largest(references)
    response_tokens = _largest(candidate_responses)
    rubric_tokens = token_counter(rubric_text) if rubric_text else 0
    total = prompt_tokens + rubric_tokens + input_tokens + reference_tokens + response_tokens
    return 1.0 - (total / context_window_tokens)


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
    system_prompts: Sequence[str] = (),
    monotonic_examples: Sequence[tuple[DatasetItem, str]] | None = None,
    gate_flip_repeats: int = 5,
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

    # Reviewer item #6: consistency probe and latency probe are the
    # same physical calls; reuse the elapsed time. Wrapped in try/except
    # so a probe failure doesn't (a) crash empirical_preflight at the
    # first measurement, and (b) doesn't poison the latency mean with
    # failed-call wall time. On failure we record a warning and fall
    # back to fail-closed JudgeQualityMeasurement defaults.
    consistency_t0 = perf_counter()
    try:
        judge_quality, _ = measure_judge_consistency(
            judge=judge,
            rubric=rubric,
            probe_item=probe_item,
            target_response=probe_response,
            repeats=consistency_repeats,
        )
        consistency_succeeded = True
    except Exception as exc:
        warnings.append(
            f"judge_quality.consistency probe failed: "
            f"{type(exc).__name__}: {exc}; defaulted to fail-closed "
            f"JudgeQualityMeasurement (consistency=0.0). The failed "
            f"probe latency is NOT included in the performance "
            f"projection — only successful probe latency is used."
        )
        judge_quality = JudgeQualityMeasurement(
            consistency=0.0,
            anchoring_usage=0.0,
            scale_monotonic=False,
            samples=0,
        )
        consistency_succeeded = False
    consistency_elapsed_ms = (perf_counter() - consistency_t0) * 1000.0
    # Only count probe wall time as a latency sample when the probe
    # actually succeeded. A 30s timeout from a failed call must not
    # flow into mean_call_latency_ms as if it were a successful sample.
    avg_call_latency_ms = (
        consistency_elapsed_ms / max(1, consistency_repeats)
        if consistency_succeeded and consistency_repeats > 0 else 0.0
    )

    # Hard-gate flip rate — surface a stability number that weighted
    # consistency cannot see. A judge whose score is stable but whose
    # gate flips True/False randomises the ship verdict. Measured here
    # only if the rubric declares judge-mode gates.
    judge_gates = [g for g in rubric.hard_gates if g.evaluator == "judge"]
    if judge_gates and gate_flip_repeats > 0:
        try:
            flip_results = measure_gate_flip_rate(
                judge=judge,
                rubric=rubric,
                probe_item=probe_item,
                target_response=probe_response,
                repeats=gate_flip_repeats,
            )
            max_flip = max(
                (float(r["flip_rate"]) for r in flip_results.values()),
                default=0.0,
            )
            if max_flip > 0.0:
                worst = max(
                    flip_results.items(),
                    key=lambda kv: float(kv[1]["flip_rate"]),
                )
                warnings.append(
                    f"judge gate '{worst[0]}' flipped on "
                    f"{float(worst[1]['flip_rate']):.2f} of consecutive call pairs "
                    f"(over {int(worst[1]['samples'])} repeats); ship verdict will "
                    f"be unstable. Re-spec the gate or raise rescore_count."
                )
        except Exception as exc:
            warnings.append(
                f"judge_quality.gate_flip_rate probe failed: "
                f"{type(exc).__name__}: {exc}"
            )
    elif not judge_gates:
        # No judge-mode gates -> nothing to measure; not a warning.
        pass

    # Scale monotonicity — single-item consistency cannot measure this.
    # If the caller passed an ordered fixture, run it; otherwise warn.
    if monotonic_examples is not None and len(monotonic_examples) >= 2:
        try:
            mono = measure_scale_monotonicity(
                judge=judge,
                rubric=rubric,
                ordered_examples=monotonic_examples,
            )
            judge_quality = judge_quality.model_copy(update={"scale_monotonic": mono})
            if not mono:
                warnings.append(
                    "judge_quality.scale_monotonic = False — judge ranking "
                    "disagrees with the supplied bad < good ordering."
                )
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(
                f"judge_quality.scale_monotonic probe failed: "
                f"{type(exc).__name__}: {exc}; defaulted to False."
            )
    else:
        warnings.append(
            "judge_quality.scale_monotonic not measured — pass "
            "monotonic_examples=[(bad_item, bad_resp), ..., (good_item, good_resp)] "
            "to verify bad < mid < good ordering. Defaulted to False (fail-closed)."
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
        if endpoint.silent_degradation_detected:
            warnings.append(
                "endpoint.silent_degradation_detected = True — at least one "
                "strict-schema probe returned parsed=None WITHOUT raising a "
                "ProviderError. The endpoint accepted the request but produced "
                "unparseable output (a silent capability degradation). Treat "
                "schema_reliability as suspect and inspect the raw responses."
            )
    else:
        endpoint = EndpointMeasurement(
            schema_reliability=0.0,  # fail-closed: unmeasured != good
            context_budget_margin=1.0,  # filled in below
            caching_active=False,
            # Fail-closed: with no probe we cannot observe silent
            # degradation. Keep False but warn it was NOT probed, so an
            # agent never reads "False" as "measured: no degradation".
            silent_degradation_detected=False,
        )
        warnings.append(
            "endpoint.schema_reliability not measured — strict_schema_provider, "
            "strict_schema_output, and strict_schema_probes were not supplied; "
            "value defaulted to 0.0 (fail-closed). Pass these to actually "
            "probe the provider's strict-schema reliability."
        )
        warnings.append(
            "endpoint.silent_degradation_detected = False but schema degradation "
            "not probed — no strict-schema probe was run, so a parsed=None "
            "silent degradation could not be observed. The False here means "
            "'not measured', not 'measured: clean'."
        )

    # Context budget - computed from the probe content sizes.
    if token_counter is not None:
        # Tokenizer-exact path. Build text populations from what we have
        # in scope; system_prompts is provided when the caller knows the
        # full prompt variant set.
        rubric_text = " ".join(d.description for d in rubric.dimensions if d.description)
        margin = compute_context_margin_from_texts(
            system_prompts=tuple(system_prompts) if system_prompts else (),
            rubric_text=rubric_text,
            inputs=(probe_item.input,) if probe_item.input else (),
            references=(probe_item.reference,) if probe_item.reference else (),
            candidate_responses=(probe_response,) if probe_response else (),
            context_window_tokens=context_window_tokens or 32000,
            token_counter=token_counter,
        )
        if not system_prompts:
            warnings.append(
                "endpoint.context_budget_margin computed without a "
                "system_prompts population — system prompt overhead not "
                "accounted for. Pass system_prompts=[...] when known."
            )
    else:
        rubric_chars = sum(len(d.description) for d in rubric.dimensions)
        margin = compute_context_margin(
            system_prompt_chars=0,
            rubric_chars=rubric_chars,
            longest_input_chars=len(probe_item.input or ""),
            longest_reference_chars=len(probe_item.reference or ""),
            longest_response_chars=longest_response_chars,
            context_window_tokens=context_window_tokens or 32000,
        )
        warnings.append(
            "endpoint.context_budget_margin uses the chars_per_token=3.8 "
            "heuristic — pass token_counter=<tokenizer> for a measurement."
        )
    endpoint = endpoint.model_copy(update={"context_budget_margin": margin})

    # Performance projection — reuse the consistency probe's average
    # call latency rather than issuing a fresh probe call. The pre-fix
    # version made one extra call AND swallowed its exception, then
    # appended the failure latency to the sample list; that double-
    # billed the user and could put failed-call elapsed times into the
    # mean. Now we rely on the work we already paid for, and item #6
    # of the audit review further separates success vs failure: only
    # successful probe latency reaches ``probe_latencies_ms``. If the
    # consistency probe failed, ``avg_call_latency_ms`` is 0 and the
    # mean falls back to 0 with no spurious "30s typical call" claim.
    performance = project_performance(
        probe_latencies_ms=[avg_call_latency_ms] if avg_call_latency_ms > 0 else [],
        dataset_size=dataset_size_hint,
        candidates_expected=candidates_expected,
    )
    if not consistency_succeeded:
        warnings.append(
            "performance.mean_call_latency_ms not measured — the "
            "consistency probe failed. Treat the projected wall time "
            "as 'not estimated' rather than 'fast'."
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

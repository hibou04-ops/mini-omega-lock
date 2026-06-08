# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""FastMCP server wrapping mini-omega-lock's five probes.

Each tool accepts JSON-friendly input (dicts, primitives, sequences) and
returns the underlying Pydantic measurement serialized as a dict. The
LLM-using probes (`empirical_preflight`, `measure_judge_consistency`)
build the provider / judge inline from a `provider` arg, so agents do
not need to wire an LLMJudge themselves.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from mcp.server.fastmcp import FastMCP

from mini_omega_lock import (
    compute_context_margin as _compute_context_margin,
    compute_context_margin_from_texts as _compute_context_margin_from_texts,
    empirical_preflight as _empirical_preflight,
    measure_gate_flip_rate as _measure_gate_flip_rate,
    measure_judge_consistency as _measure_judge_consistency,
    measure_scale_monotonicity as _measure_scale_monotonicity,
    noise_floor_estimate as _noise_floor_estimate,
    probe_strict_schema as _probe_strict_schema,
    project_performance as _project_performance,
)


# ---------------------------------------------------------------------------
# Workspace boundary
# ---------------------------------------------------------------------------
#
# Reviewer item #7: MCP tools accept rubric paths from agent input. Without a
# boundary, an agent prompt could include ``"rubric": "/etc/passwd"`` (or any
# absolute path / ``..`` traversal) and the rubric loader would dutifully read
# it, leaking arbitrary file contents into the JSON-decode error message in
# the MCP response. Bound the path resolution to a workspace root so paths
# outside it raise a structured error before any disk read.
#
# The root comes from ``MINI_OMEGA_WORKSPACE_ROOT``. When unset we default to
# the current working directory (the standard "agent invokes from project
# root" case) so existing single-project setups keep working unchanged.


def _workspace_root() -> Path:
    """The directory all rubric path inputs must resolve inside.

    Reads ``MINI_OMEGA_WORKSPACE_ROOT`` lazily so tests can monkeypatch it
    per-call. Resolves to an absolute path so the comparison below is
    stable across symlinks and relative inputs.
    """
    raw = os.environ.get("MINI_OMEGA_WORKSPACE_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.cwd().resolve()


def _validate_workspace_path(candidate: Path) -> Path:
    """Reject paths that escape the configured workspace root.

    Raises ``ValueError`` (caught and surfaced as a structured MCP error)
    when ``candidate`` resolves outside ``_workspace_root()``. Returns the
    resolved path on success so the caller can use it directly.
    """
    root = _workspace_root()
    resolved = candidate.expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"path {str(candidate)!r} resolves to {str(resolved)!r}, "
            f"which is outside the configured workspace root "
            f"{str(root)!r}. Set MINI_OMEGA_WORKSPACE_ROOT to widen the "
            f"boundary, or pass an inline dict for the rubric instead "
            f"of a path."
        ) from exc
    return resolved

mcp_app = FastMCP(
    name="mini-omega-lock",
    instructions=(
        "Empirical preflight probes for omegaprompt calibration. Use these "
        "tools BEFORE running a full calibrate() to verify the runtime "
        "environment is ship-grade: judge consistency (does the same input "
        "produce the same score?), endpoint reliability, context-budget "
        "margin, latency / wall-time projection, noise floor."
    ),
)


def _resolve_rubric(r):
    from omegaprompt.domain import JudgeRubric

    if isinstance(r, JudgeRubric):
        return r
    if isinstance(r, dict):
        return JudgeRubric.model_validate(r)
    if isinstance(r, (str, Path)):
        # Reviewer item #7: bound rubric path inputs to the workspace
        # root before reading from disk. Inline dicts skip this path
        # (no filesystem access), so they remain unrestricted.
        safe_path = _validate_workspace_path(Path(r))
        return JudgeRubric.from_json(safe_path)
    raise TypeError(f"Unsupported rubric input: {type(r).__name__}")


def _resolve_item(i):
    from omegaprompt.domain import DatasetItem

    if isinstance(i, DatasetItem):
        return i
    if isinstance(i, dict):
        return DatasetItem.model_validate(i)
    raise TypeError(f"Unsupported item input: {type(i).__name__}")


def _build_judge(provider):
    from omegaprompt.judges import LLMJudge
    from omegaprompt.providers import make_provider

    if isinstance(provider, str):
        provider_obj = make_provider(provider)
    elif isinstance(provider, dict):
        provider_obj = make_provider(
            provider["name"],
            model=provider.get("model"),
            base_url=provider.get("base_url"),
        )
    else:
        provider_obj = provider
    return LLMJudge(provider=provider_obj)


def _resolve_token_counter(spec):
    """Resolve a JSON-friendly tokenizer spec into a ``str -> int`` callable.

    FAIL LOUD: if the requested tokenizer backend is unavailable, RAISE.
    Never silently fall back to the chars/token heuristic — an agent that
    asks for an exact token count and silently gets an approximation is
    exactly the false-safe this package exists to prevent. Pass ``None``
    to deliberately use the heuristic path (which emits its own warning).

    Supported specs:
        ``None``                 -> heuristic path (no tokenizer)
        ``"tiktoken"``           -> tiktoken with ``cl100k_base``
        ``"tiktoken:<encoding>"``-> tiktoken with the named encoding
    """
    if spec is None:
        return None
    if not isinstance(spec, str):
        raise ValueError(
            f"token_counter must be a tokenizer spec string or null, got "
            f"{type(spec).__name__}."
        )
    spec = spec.strip()
    if spec.startswith("tiktoken"):
        try:
            import tiktoken  # type: ignore
        except ImportError as exc:  # fail loud, do NOT degrade silently
            raise RuntimeError(
                "token_counter='tiktoken' requested but the 'tiktoken' package "
                "is not installed. Install it or pass token_counter=null to use "
                "the chars_per_token heuristic (which warns explicitly). "
                "Refusing to silently fall back to the heuristic."
            ) from exc
        _, _, enc_name = spec.partition(":")
        enc_name = enc_name or "cl100k_base"
        try:
            enc = tiktoken.get_encoding(enc_name)
        except Exception as exc:  # unknown encoding -> loud, not silent
            raise RuntimeError(
                f"token_counter tiktoken encoding {enc_name!r} is unavailable: "
                f"{exc}. Refusing to silently fall back to the heuristic."
            ) from exc
        return lambda text: len(enc.encode(text))
    raise RuntimeError(
        f"unknown token_counter spec {spec!r}. Supported: 'tiktoken' or "
        f"'tiktoken:<encoding>', or null for the heuristic path."
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp_app.tool()
def empirical_preflight(
    rubric: str | dict,
    probe_item: dict,
    probe_response: str,
    provider: str | dict,
    context_window_tokens: int = 0,
    longest_response_chars: int = 0,
    consistency_repeats: int = 3,
    dataset_size_hint: int = 10,
    candidates_expected: int = 20,
    strict_schema_probe_messages: list[str] | None = None,
    strict_schema_provider: str | dict | None = None,
    fitness_samples: list[float] | None = None,
    monotonic_examples: list[dict] | None = None,
    token_counter: str | None = None,
    system_prompts: list[str] | None = None,
    gate_flip_repeats: int = 5,
) -> dict:
    """Run the combined judge / endpoint / performance preflight probe.

    Use BEFORE a full omegaprompt calibration to verify the runtime is
    ship-grade. Costs ``consistency_repeats`` LLM calls on the probe item,
    plus ``len(strict_schema_probe_messages)`` calls when the strict-schema
    probe is requested.

    Args:
        rubric: Path to a JudgeRubric JSON, or an inline rubric dict.
        probe_item: Inline DatasetItem dict ``{"id":..., "input":...,
            "reference":...}`` representing a typical input on the task.
        probe_response: A canonical correct response string for the probe
            item; used to test judge stability.
        provider: Provider for the LLM judge. String name or
            ``{"name":..., "model":..., "base_url":...}`` dict.
        context_window_tokens: Model context window in tokens (e.g. 200000
            for Claude, 128000 for GPT-4o). Used for the context-margin probe.
        longest_response_chars: Longest expected response in chars. Used
            with context_window_tokens to compute headroom.
        consistency_repeats: How many times to re-judge the probe to measure
            consistency. Default 3.
        dataset_size_hint: Estimated dataset size for performance projection.
        candidates_expected: Estimated number of search candidates for
            performance projection.
        strict_schema_probe_messages: Optional list of user messages to send
            via strict-schema mode against ``strict_schema_provider`` (or the
            judge provider when omitted). When supplied, ``endpoint.schema_reliability``
            reflects the actual parse-success rate. When omitted, schema
            reliability is fail-closed at 0.0 with an explicit warning so
            the calling agent can tell "not measured" from "measured zero."
        strict_schema_provider: Optional separate provider for the strict-
            schema probe. Defaults to the judge provider when not given —
            useful when the target and judge are different vendors and you
            want to probe the target's schema reliability rather than the
            judge's.
        fitness_samples: Optional list of fitness floats from repeated
            evaluations at fixed params. When supplied (>=2 samples),
            ``performance.noise_floor`` reflects the actual variance.
        monotonic_examples: Optional ordered ``[{"item": {...},
            "response": "..."}, ...]`` list in ascending quality order
            (index 0 = worst). When supplied (>=2), ``scale_monotonic`` is
            actually measured instead of fail-closed to False.
        token_counter: Optional tokenizer spec ('tiktoken' or
            'tiktoken:<encoding>') for an EXACT context margin. Omit / null
            for the chars_per_token heuristic. An unavailable tokenizer
            RAISES — it never silently falls back to the heuristic.
        system_prompts: Optional list of system-prompt variants; the
            longest is used as the worst case for the tokenizer-exact
            context-margin computation.
        gate_flip_repeats: How many times to repeat the hard-gate flip
            probe (default 5). Set 0 to skip it.

    Returns:
        Dict with ``judge_quality``, ``endpoint``, ``performance``, and a
        ``warnings`` list. Agents should read ``warnings`` before treating
        any value as "good" — fail-closed defaults look numerically clean
        but mean "we didn't measure this".
    """
    rubric_obj = _resolve_rubric(rubric)
    item_obj = _resolve_item(probe_item)
    judge = _build_judge(provider)
    token_counter_fn = _resolve_token_counter(token_counter)

    monotonic_pairs = None
    if monotonic_examples:
        monotonic_pairs = [
            (_resolve_item(pair["item"]), pair["response"]) for pair in monotonic_examples
        ]

    schema_provider_obj = None
    schema_probes_seq: tuple = ()
    schema_output_type: type | None = None
    if strict_schema_probe_messages:
        from omegaprompt.domain.enums import (
            OutputBudgetBucket,
            ReasoningProfile,
            ResponseSchemaMode,
        )
        from omegaprompt.domain.judge import JudgeResult
        from omegaprompt.providers import make_provider as _mp
        from omegaprompt.providers.base import ProviderRequest

        if strict_schema_provider is None:
            schema_provider_obj = judge.provider
        elif isinstance(strict_schema_provider, str):
            schema_provider_obj = _mp(strict_schema_provider)
        elif isinstance(strict_schema_provider, dict):
            schema_provider_obj = _mp(
                strict_schema_provider["name"],
                model=strict_schema_provider.get("model"),
                base_url=strict_schema_provider.get("base_url"),
            )
        else:
            schema_provider_obj = strict_schema_provider

        schema_output_type = JudgeResult
        schema_probes_seq = tuple(
            ProviderRequest(
                system_prompt="Strict-schema probe.",
                user_message=msg,
                response_schema_mode=ResponseSchemaMode.FREEFORM,
                output_budget_bucket=OutputBudgetBucket.SMALL,
                reasoning_profile=ReasoningProfile.OFF,
            )
            for msg in strict_schema_probe_messages
        )

    judge_q, endpoint, perf, warnings = _empirical_preflight(
        judge=judge,
        rubric=rubric_obj,
        probe_item=item_obj,
        probe_response=probe_response,
        context_window_tokens=context_window_tokens,
        longest_response_chars=longest_response_chars,
        consistency_repeats=consistency_repeats,
        dataset_size_hint=dataset_size_hint,
        candidates_expected=candidates_expected,
        strict_schema_provider=schema_provider_obj,
        strict_schema_probes=schema_probes_seq,
        strict_schema_output=schema_output_type,
        fitness_samples=fitness_samples,
        token_counter=token_counter_fn,
        system_prompts=tuple(system_prompts) if system_prompts else (),
        monotonic_examples=monotonic_pairs,
        gate_flip_repeats=gate_flip_repeats,
    )
    return {
        "judge_quality": judge_q.model_dump(mode="json"),
        "endpoint": endpoint.model_dump(mode="json"),
        "performance": perf.model_dump(mode="json"),
        # Surface fail-closed warnings: agents must read this to know
        # whether schema_reliability=0.0 means "measured zero" or
        # "not measured (defaulted to 0)".
        "warnings": warnings,
    }


@mcp_app.tool()
def measure_judge_consistency(
    rubric: str | dict,
    probe_item: dict,
    target_response: str,
    provider: str | dict,
    repeats: int = 3,
) -> dict:
    """Probe judge consistency across repeated calls on the same input.

    Returns the JudgeQualityMeasurement (consistency 0-1, anchoring_usage,
    scale_monotonic, samples) plus the raw judge results for inspection.

    Args:
        rubric: Path or inline dict for the JudgeRubric.
        probe_item: Inline DatasetItem dict.
        target_response: The candidate response to grade repeatedly.
        provider: Provider for the LLM judge.
        repeats: Number of grading repeats. Default 3.

    Returns:
        Dict with ``judge_quality`` and ``raw_results`` (list of JudgeResult).
    """
    rubric_obj = _resolve_rubric(rubric)
    item_obj = _resolve_item(probe_item)
    judge = _build_judge(provider)

    measurement, raw = _measure_judge_consistency(
        judge=judge,
        rubric=rubric_obj,
        probe_item=item_obj,
        target_response=target_response,
        repeats=repeats,
    )
    return {
        "judge_quality": measurement.model_dump(mode="json"),
        "raw_results": [r.model_dump(mode="json") for r in raw],
    }


@mcp_app.tool()
def measure_gate_flip_rate(
    rubric: str | dict,
    probe_item: dict,
    target_response: str,
    provider: str | dict,
    repeats: int = 5,
) -> dict:
    """Measure how often a hard gate flips on the same input across repeats.

    In Prompt CI a flipping hard gate is more catastrophic than soft-score
    noise: a candidate that sometimes passes and sometimes fails the same
    gate makes the ship verdict random. ``measure_judge_consistency``
    only sees the weighted score, so a judge whose gate decisions wobble
    while the score is stable looks "consistent" — this metric closes
    that gap.

    Returns a dict keyed by gate name. Each entry has ``flip_rate``,
    ``samples``, ``majority``, and ``passes``. A flip_rate of 0.0 means
    rock-solid; 1.0 means flips every call.

    Args:
        rubric: Path or inline dict for the JudgeRubric.
        probe_item: Inline DatasetItem dict.
        target_response: The candidate response to grade repeatedly.
        provider: Provider for the LLM judge.
        repeats: Number of grading repeats. Default 5 (vs 3 for
            consistency, since detecting flip patterns needs more data).

    Returns:
        Dict with ``gate_flip_rates`` (per-gate flip rate dict) and
        ``max_flip_rate`` (the worst gate's flip rate, 0-1, useful for
        downstream gating).
    """
    rubric_obj = _resolve_rubric(rubric)
    item_obj = _resolve_item(probe_item)
    judge = _build_judge(provider)
    per_gate = _measure_gate_flip_rate(
        judge=judge,
        rubric=rubric_obj,
        probe_item=item_obj,
        target_response=target_response,
        repeats=repeats,
    )
    max_flip = max((v["flip_rate"] for v in per_gate.values()), default=0.0)
    return {
        "gate_flip_rates": per_gate,
        "max_flip_rate": max_flip,
    }


@mcp_app.tool()
def compute_context_margin(
    system_prompt_chars: int,
    rubric_chars: int,
    longest_input_chars: int,
    longest_reference_chars: int,
    longest_response_chars: int,
    context_window_tokens: int,
    chars_per_token: float = 3.8,
) -> dict:
    """Deterministically compute context-budget headroom (no LLM call).

    Returns 1.0 when the largest call uses 0% of context, 0.0 when it sits
    on the boundary, and a negative value when projected to overflow.

    Args:
        system_prompt_chars: Char count of the longest system prompt variant.
        rubric_chars: Char count of the rubric (judge prompt expansion).
        longest_input_chars: Longest dataset input.
        longest_reference_chars: Longest dataset reference.
        longest_response_chars: Longest expected target response.
        context_window_tokens: Model context window (e.g. 200000).
        chars_per_token: Conversion factor. Default 3.8 (English-heavy).

    Returns:
        Dict with ``margin`` (float, 0-1 or negative on overflow).
    """
    margin = _compute_context_margin(
        system_prompt_chars=system_prompt_chars,
        rubric_chars=rubric_chars,
        longest_input_chars=longest_input_chars,
        longest_reference_chars=longest_reference_chars,
        longest_response_chars=longest_response_chars,
        context_window_tokens=context_window_tokens,
        chars_per_token=chars_per_token,
    )
    return {"margin": margin}


@mcp_app.tool()
def noise_floor_estimate(fitness_samples: Sequence[float]) -> dict:
    """Estimate fitness variance from repeated evaluations at fixed params.

    Use the resulting noise floor as a minimum-detectable-effect threshold:
    differences smaller than the noise floor are not statistically meaningful.

    Args:
        fitness_samples: List of fitness values from repeated evaluations
            of the same param config (e.g. 5+ samples).

    Returns:
        Dict with ``noise_floor`` (non-negative float).
    """
    return {"noise_floor": _noise_floor_estimate(fitness_samples=list(fitness_samples))}


@mcp_app.tool()
def project_performance(
    probe_latencies_ms: Sequence[float],
    dataset_size: int,
    candidates_expected: int,
    calls_per_candidate_per_item: int = 2,
) -> dict:
    """Project full-pipeline wall-time from probe latencies.

    Args:
        probe_latencies_ms: List of measured per-call latencies (ms).
        dataset_size: Number of items in the dataset.
        candidates_expected: Expected number of search candidates.
        calls_per_candidate_per_item: 1 if rule-only judge, 2 if
            target+LLM-judge per item. Default 2.

    Returns:
        PerformanceMeasurement dict (mean_call_latency_ms,
        projected_wall_time_seconds, noise_floor).
    """
    perf = _project_performance(
        probe_latencies_ms=list(probe_latencies_ms),
        dataset_size=dataset_size,
        candidates_expected=candidates_expected,
        calls_per_candidate_per_item=calls_per_candidate_per_item,
    )
    return perf.model_dump(mode="json")


@mcp_app.tool()
def measure_scale_monotonicity(
    rubric: str | dict,
    ordered_examples: list[dict],
    provider: str | dict,
) -> dict:
    """Verify the judge preserves a known bad < mid < good ordering.

    ``ordered_examples`` is a list of ``{"item": {...}, "response":
    "..."}`` dicts in ASCENDING quality order — index 0 is the worst,
    index -1 the best. The judge scores each pair once; the result is
    ``True`` iff the weighted scores are non-decreasing in that order.

    Two examples (bad < good) is the minimum; three or more
    (bad < mid < good) is recommended for a stronger signal.

    Args:
        rubric: Path or inline dict for the JudgeRubric.
        ordered_examples: ``[{"item": <DatasetItem dict>, "response":
            <str>}, ...]`` in ascending quality order.
        provider: Provider for the LLM judge.

    Returns:
        Dict with ``scale_monotonic`` (bool). True = the judge's ranking
        agrees with the declared ordering.
    """
    rubric_obj = _resolve_rubric(rubric)
    judge = _build_judge(provider)
    pairs = [(_resolve_item(p["item"]), p["response"]) for p in ordered_examples]
    monotonic = _measure_scale_monotonicity(
        judge=judge,
        rubric=rubric_obj,
        ordered_examples=pairs,
    )
    return {"scale_monotonic": monotonic}


@mcp_app.tool()
def probe_strict_schema(
    strict_schema_probe_messages: list[str],
    provider: str | dict,
) -> dict:
    """Fire STRICT_SCHEMA probes and report parse success + silent degradation.

    Sends each message via STRICT_SCHEMA mode against ``provider`` and
    records the parse-success rate. A response that comes back WITHOUT a
    ProviderError but with no parseable payload is a *silent* degradation
    and is surfaced via ``silent_degradation_detected``.

    Args:
        strict_schema_probe_messages: User messages to send (>=1).
        provider: Provider whose strict-schema reliability is probed.

    Returns:
        EndpointMeasurement dict (``schema_reliability``,
        ``context_budget_margin`` placeholder, ``caching_active``,
        ``silent_degradation_detected``).
    """
    from omegaprompt.domain.enums import (
        OutputBudgetBucket,
        ReasoningProfile,
        ResponseSchemaMode,
    )
    from omegaprompt.domain.judge import JudgeResult
    from omegaprompt.providers import make_provider as _mp
    from omegaprompt.providers.base import ProviderRequest

    if isinstance(provider, str):
        provider_obj = _mp(provider)
    elif isinstance(provider, dict):
        provider_obj = _mp(
            provider["name"],
            model=provider.get("model"),
            base_url=provider.get("base_url"),
        )
    else:
        provider_obj = provider

    probes = tuple(
        ProviderRequest(
            system_prompt="Strict-schema probe.",
            user_message=msg,
            response_schema_mode=ResponseSchemaMode.FREEFORM,
            output_budget_bucket=OutputBudgetBucket.SMALL,
            reasoning_profile=ReasoningProfile.OFF,
        )
        for msg in strict_schema_probe_messages
    )
    endpoint = _probe_strict_schema(
        provider=provider_obj,
        output_schema=JudgeResult,
        probes=probes,
    )
    return endpoint.model_dump(mode="json")


@mcp_app.tool()
def compute_context_margin_from_texts(
    context_window_tokens: int,
    token_counter: str,
    system_prompts: list[str] | None = None,
    rubric_text: str = "",
    inputs: list[str] | None = None,
    references: list[str] | None = None,
    candidate_responses: list[str] | None = None,
) -> dict:
    """Tokenizer-EXACT context margin from the actual texts of the largest call.

    Unlike ``compute_context_margin`` (chars heuristic), this uses a real
    tokenizer. The ``token_counter`` spec MUST resolve to an available
    tokenizer — an unavailable one RAISES rather than silently falling
    back to the heuristic (that would be a false-safe).

    Args:
        context_window_tokens: Provider context window in tokens.
        token_counter: Tokenizer spec — 'tiktoken' or 'tiktoken:<encoding>'.
        system_prompts: System-prompt variants; longest used.
        rubric_text: Concatenated rubric body.
        inputs: Dataset input texts; largest used.
        references: Dataset reference texts; largest used.
        candidate_responses: Observed candidate responses; largest used.

    Returns:
        Dict with ``margin`` (float; negative on projected overflow).
    """
    counter = _resolve_token_counter(token_counter)
    if counter is None:
        # token_counter is required for this tool; null is not allowed.
        raise ValueError(
            "compute_context_margin_from_texts requires a token_counter spec "
            "(e.g. 'tiktoken'); for the heuristic use compute_context_margin."
        )
    margin = _compute_context_margin_from_texts(
        system_prompts=tuple(system_prompts) if system_prompts else (),
        rubric_text=rubric_text,
        inputs=tuple(inputs) if inputs else (),
        references=tuple(references) if references else (),
        candidate_responses=tuple(candidate_responses) if candidate_responses else (),
        context_window_tokens=context_window_tokens,
        token_counter=counter,
    )
    return {"margin": margin}


@mcp_app.tool()
def derive_adaptation_plan(
    judge_quality: dict | None = None,
    endpoint: dict | None = None,
    performance: dict | None = None,
) -> dict:
    """Convert preflight measurements into a concrete omegaprompt AdaptationPlan.

    Closes the measure -> plan -> act loop entirely within MCP: feed the
    ``judge_quality`` / ``endpoint`` / ``performance`` dicts returned by
    ``empirical_preflight`` (or the individual probe tools) and get back
    the plan omegaprompt's pipeline applies.

    Args:
        judge_quality: JudgeQualityMeasurement dict, or null if unmeasured.
        endpoint: EndpointMeasurement dict, or null if unmeasured.
        performance: PerformanceMeasurement dict, or null if unmeasured.

    Returns:
        AdaptationPlan dict (``plan.model_dump()``).
    """
    from omegaprompt.preflight import PreflightReport, derive_adaptation_plan as _dap
    from omegaprompt.preflight.contracts import (
        EndpointMeasurement,
        JudgeQualityMeasurement,
        PerformanceMeasurement,
    )

    report = PreflightReport(
        judge_quality=JudgeQualityMeasurement.model_validate(judge_quality) if judge_quality else None,
        endpoint=EndpointMeasurement.model_validate(endpoint) if endpoint else None,
        performance=PerformanceMeasurement.model_validate(performance) if performance else None,
    )
    plan = _dap(report=report)
    return plan.model_dump(mode="json")

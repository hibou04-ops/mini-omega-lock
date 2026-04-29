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

from pathlib import Path
from typing import Sequence

from mcp.server.fastmcp import FastMCP

from mini_omega_lock import (
    compute_context_margin as _compute_context_margin,
    empirical_preflight as _empirical_preflight,
    measure_judge_consistency as _measure_judge_consistency,
    noise_floor_estimate as _noise_floor_estimate,
    project_performance as _project_performance,
)

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
        return JudgeRubric.from_json(Path(r))
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
) -> dict:
    """Run the combined judge / endpoint / performance preflight probe.

    Use BEFORE a full omegaprompt calibration to verify the runtime is
    ship-grade. Costs ``consistency_repeats`` LLM calls on the probe item.

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

    Returns:
        Dict with ``judge_quality`` (consistency, anchoring_usage,
        scale_monotonic, samples), ``endpoint`` (schema_reliability, etc.),
        ``performance`` (mean_call_latency_ms, projected_wall_time_seconds,
        noise_floor).
    """
    rubric_obj = _resolve_rubric(rubric)
    item_obj = _resolve_item(probe_item)
    judge = _build_judge(provider)

    judge_q, endpoint, perf = _empirical_preflight(
        judge=judge,
        rubric=rubric_obj,
        probe_item=item_obj,
        probe_response=probe_response,
        context_window_tokens=context_window_tokens,
        longest_response_chars=longest_response_chars,
        consistency_repeats=consistency_repeats,
        dataset_size_hint=dataset_size_hint,
        candidates_expected=candidates_expected,
    )
    return {
        "judge_quality": judge_q.model_dump(mode="json"),
        "endpoint": endpoint.model_dump(mode="json"),
        "performance": perf.model_dump(mode="json"),
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

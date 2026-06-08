"""Reviewer C: real MCP tool execution tests for mini-omega-lock.

The pre-existing test_mcp_server.py covered tool registration shape and
one deterministic execution (compute_context_margin). This file calls
the registered MCP tool functions directly with stubbed providers and
asserts the *executed* return-value contract — particularly that
fail-closed warnings surface end-to-end through the MCP boundary.
"""

from __future__ import annotations

import json

import pytest

# mcp is an optional extra; skip the whole file if it isn't installed
# so the default `pytest -q` (without `--extra mcp`) doesn't error out.
pytest.importorskip("mcp")

from omegaprompt.domain.judge import Dimension, HardGate, JudgeResult, JudgeRubric
from omegaprompt.providers.base import (
    CapabilityTier,
    ProviderCapabilities,
    ProviderResponse,
)


@pytest.fixture
def mcp_server():
    from mini_omega_lock.mcp import server as srv

    return srv


# ---------------------------------------------------------------------------
# Stub provider used so empirical_preflight stays offline.
# ---------------------------------------------------------------------------


class _ScriptedProvider:
    name = "anthropic"
    model = "scripted"

    def __init__(self):
        self._cursor = 0

    def call(self, request):
        self._cursor += 1
        return ProviderResponse(
            parsed=JudgeResult(
                scores={"acc": 4},
                gate_results={"no_refusal": True},
            ),
            usage={"input_tokens": 50, "output_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            latency_ms=5.0,
        )

    def capabilities(self):
        return ProviderCapabilities(
            provider="anthropic",
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=True,
            supports_llm_judge=True,
            ship_grade_judge=True,
        )


def _patch_make_provider(monkeypatch):
    """Force the MCP wrapper to use the scripted provider regardless of name."""
    monkeypatch.setattr(
        "omegaprompt.providers.make_provider",
        lambda *a, **kw: _ScriptedProvider(),
    )


def _rubric_dict() -> dict:
    return {
        "dimensions": [
            {"name": "acc", "description": "is correct", "weight": 1.0},
        ],
        "hard_gates": [
            {"name": "no_refusal", "description": "must try", "evaluator": "judge"}
        ],
    }


# ---------------------------------------------------------------------------
# empirical_preflight execution.
# ---------------------------------------------------------------------------


def test_mcp_empirical_preflight_returns_warnings_when_no_schema_probe(mcp_server, monkeypatch):
    """Pre-fix this would have silently returned schema_reliability=1.0
    with no warning. Post-fix the agent gets an explicit fail-closed
    indicator + a warnings list naming what wasn't measured."""
    _patch_make_provider(monkeypatch)
    result = mcp_server.empirical_preflight(
        rubric=_rubric_dict(),
        probe_item={"id": "p1", "input": "ping", "reference": "pong"},
        probe_response="pong",
        provider="anthropic",
        consistency_repeats=1,
    )
    json.dumps(result)  # must be JSON-encodable
    assert result["endpoint"]["schema_reliability"] == 0.0
    assert "warnings" in result
    assert any("schema_reliability" in w for w in result["warnings"])


def test_mcp_empirical_preflight_runs_schema_probe_when_messages_supplied(mcp_server, monkeypatch):
    """When the new MCP kwargs from PR #2 are supplied, schema_reliability
    is the actual measured rate, not the fail-closed default."""
    _patch_make_provider(monkeypatch)
    result = mcp_server.empirical_preflight(
        rubric=_rubric_dict(),
        probe_item={"id": "p1", "input": "ping", "reference": "pong"},
        probe_response="pong",
        provider="anthropic",
        consistency_repeats=1,
        strict_schema_probe_messages=["probe one", "probe two", "probe three"],
        strict_schema_provider="anthropic",
    )
    # Stubbed provider returns a parsed JudgeResult on every call -> 100%.
    assert result["endpoint"]["schema_reliability"] == 1.0
    # No "schema_reliability not measured" warning when it actually was:
    assert not any("schema_reliability not measured" in w for w in result["warnings"])


def test_mcp_empirical_preflight_runs_noise_floor_when_fitness_samples_supplied(mcp_server, monkeypatch):
    _patch_make_provider(monkeypatch)
    result = mcp_server.empirical_preflight(
        rubric=_rubric_dict(),
        probe_item={"id": "p1", "input": "ping"},
        probe_response="x",
        provider="anthropic",
        consistency_repeats=1,
        fitness_samples=[0.80, 0.85, 0.90],
    )
    assert result["performance"]["noise_floor"] > 0
    assert not any("noise_floor not measured" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# measure_judge_consistency execution.
# ---------------------------------------------------------------------------


def test_mcp_measure_judge_consistency_executes(mcp_server, monkeypatch):
    _patch_make_provider(monkeypatch)
    result = mcp_server.measure_judge_consistency(
        rubric=_rubric_dict(),
        probe_item={"id": "p1", "input": "x"},
        target_response="response",
        provider="anthropic",
        repeats=2,
    )
    assert "judge_quality" in result
    assert result["judge_quality"]["samples"] == 2
    assert "raw_results" in result
    assert len(result["raw_results"]) == 2


# ---------------------------------------------------------------------------
# Pure deterministic tools — fast smoke through the MCP wrapper.
# ---------------------------------------------------------------------------


def test_mcp_compute_context_margin_returns_float(mcp_server):
    result = mcp_server.compute_context_margin(
        system_prompt_chars=100,
        rubric_chars=200,
        longest_input_chars=1000,
        longest_reference_chars=0,
        longest_response_chars=500,
        context_window_tokens=200000,
    )
    assert "margin" in result
    assert 0.0 < result["margin"] <= 1.0


def test_mcp_noise_floor_estimate_returns_zero_for_identical_samples(mcp_server):
    result = mcp_server.noise_floor_estimate(fitness_samples=[0.85, 0.85, 0.85])
    assert result["noise_floor"] == 0.0


def test_mcp_project_performance_returns_extrapolated_walltime(mcp_server):
    result = mcp_server.project_performance(
        probe_latencies_ms=[200.0, 250.0, 300.0],
        dataset_size=10,
        candidates_expected=5,
        calls_per_candidate_per_item=2,
    )
    assert "mean_call_latency_ms" in result
    assert "projected_wall_time_seconds" in result


# ---------------------------------------------------------------------------
# H2: new MCP tools round-trip.
# ---------------------------------------------------------------------------


def test_mcp_measure_scale_monotonicity_executes(mcp_server, monkeypatch):
    _patch_make_provider(monkeypatch)
    result = mcp_server.measure_scale_monotonicity(
        rubric=_rubric_dict(),
        ordered_examples=[
            {"item": {"id": "bad", "input": "x"}, "response": "bad answer"},
            {"item": {"id": "good", "input": "x"}, "response": "good answer"},
        ],
        provider="anthropic",
    )
    # Scripted provider returns the same score every call -> non-decreasing
    # -> monotonic holds.
    assert result["scale_monotonic"] is True


def test_mcp_probe_strict_schema_executes(mcp_server, monkeypatch):
    _patch_make_provider(monkeypatch)
    result = mcp_server.probe_strict_schema(
        strict_schema_probe_messages=["probe one", "probe two"],
        provider="anthropic",
    )
    json.dumps(result)
    assert result["schema_reliability"] == 1.0
    assert result["silent_degradation_detected"] is False


def test_mcp_probe_strict_schema_flags_silent_degradation(mcp_server, monkeypatch):
    """A provider returning parsed=None without raising -> silent degradation."""
    from omegaprompt.providers.base import ProviderResponse

    class _NoneProvider:
        name = "anthropic"
        model = "scripted"

        def call(self, request):
            return ProviderResponse(parsed=None, usage={})

        def capabilities(self):
            return ProviderCapabilities(
                provider="anthropic",
                tier=CapabilityTier.CLOUD,
                supports_strict_schema=True,
                supports_llm_judge=False,
                ship_grade_judge=False,
            )

    monkeypatch.setattr(
        "omegaprompt.providers.make_provider",
        lambda *a, **kw: _NoneProvider(),
    )
    result = mcp_server.probe_strict_schema(
        strict_schema_probe_messages=["probe one"],
        provider="anthropic",
    )
    assert result["silent_degradation_detected"] is True
    assert result["schema_reliability"] == 0.0


def test_mcp_derive_adaptation_plan_executes(mcp_server):
    result = mcp_server.derive_adaptation_plan(
        judge_quality={
            "consistency": 1.0,
            "anchoring_usage": 0.5,
            "scale_monotonic": True,
            "samples": 3,
        },
        endpoint={
            "schema_reliability": 0.0,
            "context_budget_margin": 0.9,
            "caching_active": False,
            "silent_degradation_detected": False,
        },
        performance={
            "mean_call_latency_ms": 10.0,
            "projected_wall_time_seconds": 1.0,
            "noise_floor": 0.0,
        },
    )
    json.dumps(result)
    # schema_reliability 0.0 -> the plan must apply the json_object fallback.
    assert result["schema_mode_fallback"] == "json_object"


def test_mcp_compute_context_margin_from_texts_requires_tokenizer(mcp_server):
    """token_counter must be available; an unknown spec RAISES (fail loud),
    never silently degrades to the chars/token heuristic."""
    with pytest.raises((RuntimeError, ValueError)):
        mcp_server.compute_context_margin_from_texts(
            context_window_tokens=200000,
            token_counter="definitely-not-a-real-tokenizer",
            inputs=["hello world"],
        )


def test_mcp_empirical_preflight_token_counter_unavailable_raises(mcp_server, monkeypatch):
    """The new empirical_preflight token_counter param fails loud on an
    unavailable tokenizer rather than silently using the heuristic."""
    _patch_make_provider(monkeypatch)
    with pytest.raises((RuntimeError, ValueError)):
        mcp_server.empirical_preflight(
            rubric=_rubric_dict(),
            probe_item={"id": "p1", "input": "ping"},
            probe_response="pong",
            provider="anthropic",
            consistency_repeats=1,
            token_counter="not-a-real-tokenizer",
        )


def test_mcp_empirical_preflight_monotonic_examples_measured(mcp_server, monkeypatch):
    """Supplying monotonic_examples lets scale_monotonic be actually measured
    (no 'not measured' warning)."""
    _patch_make_provider(monkeypatch)
    result = mcp_server.empirical_preflight(
        rubric=_rubric_dict(),
        probe_item={"id": "p1", "input": "ping"},
        probe_response="pong",
        provider="anthropic",
        consistency_repeats=1,
        monotonic_examples=[
            {"item": {"id": "bad", "input": "x"}, "response": "bad"},
            {"item": {"id": "good", "input": "x"}, "response": "good"},
        ],
    )
    assert result["judge_quality"]["scale_monotonic"] is True
    assert not any("scale_monotonic not measured" in w for w in result["warnings"])

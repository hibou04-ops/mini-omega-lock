"""Reviewer A-3#5: gate_flip_rate is the judge metric Prompt CI cares
most about.

A judge that scores stably (low CV) but flips a hard gate true/false on
every other call still produces a random ship verdict. ``1 - CV``
treats this judge as consistent because the score doesn't move much.
``measure_gate_flip_rate`` makes the gate-level instability directly
observable.

Tests pin:
- 0.0 flip rate when every call returns the same gate values
- 1.0 flip rate when consecutive calls always disagree
- per-gate independence (one stable + one unstable -> mixed)
- empty dict when rubric declares no judge-mode hard gates
- majority vote / passes count surface for downstream consumers
- MCP tool execution end-to-end
"""

from __future__ import annotations

import pytest

from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.judge import Dimension, HardGate, JudgeResult, JudgeRubric
from omegaprompt.judges.llm_judge import LLMJudge
from omegaprompt.providers.base import (
    CapabilityTier,
    ProviderCapabilities,
    ProviderResponse,
)

from mini_omega_lock.probes import measure_gate_flip_rate


def _rubric(judge_gates: list[str], rule_gates: list[str] | None = None) -> JudgeRubric:
    return JudgeRubric(
        dimensions=[Dimension(name="acc", description="x", weight=1.0, scale=(1, 5))],
        hard_gates=[
            *[HardGate(name=g, description="g", evaluator="judge") for g in judge_gates],
            *[HardGate(name=g, description="g", evaluator="rule") for g in (rule_gates or [])],
        ],
    )


def _item() -> DatasetItem:
    return DatasetItem(id="t1", input="ping", reference=None)


class _ScriptedProvider:
    """Returns gate values from a scripted sequence — one dict per call."""

    name = "anthropic"
    model = "scripted"

    def __init__(self, gate_sequences: dict[str, list[bool]], dim_score: int = 4):
        self._gate_sequences = gate_sequences
        self._dim_score = dim_score
        self._cursor = 0

    def call(self, request):
        idx = self._cursor
        self._cursor += 1
        gate_results = {
            gate: seq[idx % len(seq)]
            for gate, seq in self._gate_sequences.items()
        }
        return ProviderResponse(
            parsed=JudgeResult(
                scores={"acc": self._dim_score},
                gate_results=gate_results,
            ),
            usage={"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            latency_ms=1.0,
        )

    def capabilities(self):
        return ProviderCapabilities(
            provider="anthropic",
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=True,
            supports_llm_judge=True,
            ship_grade_judge=True,
        )


def _judge(seq: dict[str, list[bool]]) -> LLMJudge:
    return LLMJudge(provider=_ScriptedProvider(seq))


# ---------------------------------------------------------------------------
# Pure metric.
# ---------------------------------------------------------------------------


def test_gate_flip_rate_zero_for_stable_gate():
    out = measure_gate_flip_rate(
        judge=_judge({"no_refusal": [True, True, True, True, True]}),
        rubric=_rubric(["no_refusal"]),
        probe_item=_item(),
        target_response="x",
        repeats=5,
    )
    assert out["no_refusal"]["flip_rate"] == 0.0
    assert out["no_refusal"]["majority"] is True
    assert out["no_refusal"]["passes"] == 5


def test_gate_flip_rate_one_for_alternating_gate():
    out = measure_gate_flip_rate(
        judge=_judge({"unstable": [True, False, True, False, True]}),
        rubric=_rubric(["unstable"]),
        probe_item=_item(),
        target_response="x",
        repeats=5,
    )
    assert out["unstable"]["flip_rate"] == 1.0
    # 3 trues out of 5 -> majority True
    assert out["unstable"]["majority"] is True


def test_gate_flip_rate_isolates_per_gate():
    out = measure_gate_flip_rate(
        judge=_judge(
            {
                "stable": [True, True, True, True, True],
                "wobble": [True, False, True, True, False],
            }
        ),
        rubric=_rubric(["stable", "wobble"]),
        probe_item=_item(),
        target_response="x",
        repeats=5,
    )
    assert out["stable"]["flip_rate"] == 0.0
    # transitions in [True, False, True, True, False] -> True->False, False->True,
    # True->True, True->False = 3 flips out of 4 transitions -> 0.75
    assert out["wobble"]["flip_rate"] == pytest.approx(0.75)


def test_gate_flip_rate_empty_dict_when_no_judge_gates():
    """No judge-mode hard gates means nothing to measure."""
    out = measure_gate_flip_rate(
        judge=_judge({}),
        rubric=_rubric([], rule_gates=["no_refusal"]),  # only rule gate
        probe_item=_item(),
        target_response="x",
        repeats=5,
    )
    assert out == {}


def test_gate_flip_rate_treats_missing_gate_as_false():
    """If a future judge implementation skips populating a gate, treat
    absence as False — a missing gate is a structural failure, not a
    silent pass. (PR1's LLMJudge raises before we get here, but this
    guards against regressions in alternate Judge implementations.)"""
    class _AbsentGateProvider(_ScriptedProvider):
        def call(self, request):
            self._cursor += 1
            return ProviderResponse(
                parsed=JudgeResult(scores={"acc": 4}, gate_results={}),
                usage={},
                latency_ms=0.0,
            )

    class _MinimalJudge:
        name = "minimal"

        def __init__(self):
            self._cursor = 0

        def score(self, *, rubric, item, target_response):
            self._cursor += 1
            return JudgeResult(scores={"acc": 4}, gate_results={}), {}

    out = measure_gate_flip_rate(
        judge=_MinimalJudge(),
        rubric=_rubric(["missing"]),
        probe_item=_item(),
        target_response="x",
        repeats=4,
    )
    assert out["missing"]["flip_rate"] == 0.0  # always False, no flips
    assert out["missing"]["majority"] is False
    assert out["missing"]["passes"] == 0


def test_gate_flip_rate_repeats_clamped_to_two_minimum():
    """Need at least 2 calls for a transition to exist."""
    out = measure_gate_flip_rate(
        judge=_judge({"g": [True, False]}),
        rubric=_rubric(["g"]),
        probe_item=_item(),
        target_response="x",
        repeats=1,  # too low -> clamped to 2
    )
    assert out["g"]["samples"] == 2
    assert out["g"]["flip_rate"] == 1.0  # one transition, T->F


# ---------------------------------------------------------------------------
# MCP wrapper.
# ---------------------------------------------------------------------------


def test_mcp_measure_gate_flip_rate_returns_max_flip_rate(monkeypatch):
    """End-to-end MCP execution returns per-gate dict + max."""
    from mini_omega_lock.mcp import server as srv

    class _Stub:
        name = "anthropic"
        model = "stub"

        def __init__(self):
            self._cursor = 0
            self._sequence = [True, False, True, False, True]

        def call(self, request):
            v = self._sequence[self._cursor % len(self._sequence)]
            self._cursor += 1
            return ProviderResponse(
                parsed=JudgeResult(scores={"acc": 4}, gate_results={"g": v}),
                usage={"input_tokens": 5, "output_tokens": 2, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
                latency_ms=1.0,
            )

        def capabilities(self):
            return ProviderCapabilities(
                provider="anthropic",
                tier=CapabilityTier.CLOUD,
                supports_strict_schema=True,
                supports_llm_judge=True,
                ship_grade_judge=True,
            )

    monkeypatch.setattr(
        "omegaprompt.providers.make_provider",
        lambda *a, **kw: _Stub(),
    )

    result = srv.measure_gate_flip_rate(
        rubric={
            "dimensions": [{"name": "acc", "description": "x", "weight": 1.0}],
            "hard_gates": [
                {"name": "g", "description": "g", "evaluator": "judge"},
            ],
        },
        probe_item={"id": "p1", "input": "x"},
        target_response="x",
        provider="anthropic",
        repeats=5,
    )
    assert "gate_flip_rates" in result
    assert "max_flip_rate" in result
    assert result["max_flip_rate"] == 1.0
    assert result["gate_flip_rates"]["g"]["flip_rate"] == 1.0

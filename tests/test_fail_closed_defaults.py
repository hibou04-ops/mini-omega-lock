"""Reviewer 1순위: empirical_preflight must not fabricate success defaults
when a probe wasn't actually run.

The pre-fix behaviour was that ``schema_reliability`` defaulted to 1.0
when no strict-schema probe inputs were supplied — a CI gate built on
that default would silently rubber-stamp providers with broken schema
support. The fix flips the default to 0.0 (fail-closed) and surfaces a
warning so the agent / pipeline can tell "measured zero" apart from
"not measured (defaulted to zero)".

This file pins both halves of the contract:

- Default values are fail-closed when inputs are absent.
- The returned warnings list explicitly names every unmeasured field.
"""

from __future__ import annotations

from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.judge import Dimension, HardGate, JudgeResult, JudgeRubric
from omegaprompt.judges.llm_judge import LLMJudge
from omegaprompt.providers.base import (
    CapabilityTier,
    ProviderCapabilities,
    ProviderResponse,
)

from mini_omega_lock.probes import empirical_preflight


def _rubric() -> JudgeRubric:
    return JudgeRubric(
        dimensions=[
            Dimension(name="accuracy", description="is the answer correct", weight=1.0, scale=(1, 5)),
        ],
        hard_gates=[HardGate(name="no_refusal", description="r", evaluator="judge")],
    )


def _probe_item() -> DatasetItem:
    return DatasetItem(id="probe", input="2+2?", reference="4")


class _ScriptedJudgeProvider:
    name = "anthropic"
    model = "scripted"

    def __init__(self, scores=(4, 4, 4)):
        self._scores = list(scores)
        self._cursor = 0

    def call(self, request):
        score = self._scores[self._cursor % len(self._scores)]
        self._cursor += 1
        return ProviderResponse(
            parsed=JudgeResult(
                scores={"accuracy": score},
                gate_results={"no_refusal": True},
            ),
            usage={"input_tokens": 50, "output_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            latency_ms=10.0,
        )

    def capabilities(self):
        return ProviderCapabilities(
            provider="anthropic",
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=True,
            supports_llm_judge=True,
            ship_grade_judge=True,
        )


def _make_judge() -> LLMJudge:
    return LLMJudge(provider=_ScriptedJudgeProvider())


# ---------------------------------------------------------------------------
# Schema reliability fail-closed default.
# ---------------------------------------------------------------------------


def test_schema_reliability_defaults_to_zero_when_probe_inputs_absent():
    """Pre-fix this returned 1.0 — fail-open. Now it returns 0.0."""
    judge_q, endpoint, perf, warnings = empirical_preflight(
        judge=_make_judge(),
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="The answer is 4.",
        # NO strict_schema_provider / output / probes -> fail-closed.
    )
    assert endpoint.schema_reliability == 0.0
    assert any("schema_reliability not measured" in w for w in warnings)


def test_schema_reliability_default_is_distinguishable_from_measured_zero():
    """Without warnings the agent can't tell 'measured zero schema
    reliability' from 'we never ran the probe'. The warning must be
    explicit enough to filter."""
    _, _, _, warnings = empirical_preflight(
        judge=_make_judge(),
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="The answer is 4.",
    )
    # Warning text must explicitly name the field that was unmeasured.
    assert any("schema_reliability" in w for w in warnings)


# ---------------------------------------------------------------------------
# Noise floor fail-closed default.
# ---------------------------------------------------------------------------


def test_noise_floor_defaults_to_zero_with_warning_when_no_samples():
    _, _, perf, warnings = empirical_preflight(
        judge=_make_judge(),
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="x",
    )
    assert perf.noise_floor == 0.0
    assert any("noise_floor not measured" in w for w in warnings)


def test_noise_floor_populated_when_fitness_samples_provided():
    _, _, perf, warnings = empirical_preflight(
        judge=_make_judge(),
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="x",
        fitness_samples=[0.80, 0.85, 0.90],
    )
    assert perf.noise_floor > 0
    # No warning about noise floor when it was actually measured:
    assert not any("noise_floor" in w for w in warnings)


def test_noise_floor_warning_when_too_few_samples():
    """1 sample isn't enough — pstdev needs >= 2."""
    _, _, perf, warnings = empirical_preflight(
        judge=_make_judge(),
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="x",
        fitness_samples=[0.85],  # only one sample
    )
    assert perf.noise_floor == 0.0
    assert any("noise_floor not measured" in w for w in warnings)


# ---------------------------------------------------------------------------
# Context margin heuristic warning.
# ---------------------------------------------------------------------------


def test_context_margin_warns_when_using_chars_per_token_heuristic():
    """README claims 'no fabricated numbers'. The chars_per_token=3.8
    fallback IS a heuristic — surface it so the agent knows."""
    _, _, _, warnings = empirical_preflight(
        judge=_make_judge(),
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="x",
    )
    assert any("chars_per_token" in w and "heuristic" in w for w in warnings)


def test_context_margin_no_heuristic_warning_when_token_counter_supplied():
    def real_tokens(s: str) -> int:
        return max(1, len(s) // 4)

    _, _, _, warnings = empirical_preflight(
        judge=_make_judge(),
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="x",
        token_counter=real_tokens,
    )
    # No chars_per_token warning when a real counter was used:
    assert not any("chars_per_token" in w for w in warnings)


# ---------------------------------------------------------------------------
# Backward-compat verification: callers that ignore warnings still work.
# ---------------------------------------------------------------------------


def test_empirical_preflight_returns_4_tuple_not_3_tuple():
    """The signature change from 3-tuple to 4-tuple is intentional —
    existing pre-0.4 callers must update their unpacking."""
    result = empirical_preflight(
        judge=_make_judge(),
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="x",
    )
    assert len(result) == 4
    judge_q, endpoint, perf, warnings = result
    # The four parts must each be the right shape:
    assert hasattr(judge_q, "consistency")
    assert hasattr(endpoint, "schema_reliability")
    assert hasattr(perf, "mean_call_latency_ms")
    assert isinstance(warnings, list)

"""Empirical preflight tests - judge consistency, schema reliability,
context margin, performance projection, noise floor."""

from __future__ import annotations

from unittest.mock import MagicMock

from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.enums import (
    OutputBudgetBucket,
    ReasoningProfile,
    ResponseSchemaMode,
)
from omegaprompt.domain.judge import Dimension, HardGate, JudgeResult, JudgeRubric
from omegaprompt.judges.llm_judge import LLMJudge
from mini_omega_lock.probes import (
    compute_context_margin,
    empirical_preflight,
    measure_judge_consistency,
    noise_floor_estimate,
    probe_strict_schema,
    project_performance,
)
from omegaprompt.providers.base import (
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)


def _rubric() -> JudgeRubric:
    return JudgeRubric(
        dimensions=[
            Dimension(name="accuracy", description="is the answer correct", weight=1.0, scale=(1, 5)),
        ],
        hard_gates=[HardGate(name="no_refusal", description="r", evaluator="judge")],
    )


def _probe_item() -> DatasetItem:
    return DatasetItem(id="probe", input="compute 2+2", reference="4")


class _ScriptedJudgeProvider:
    name = "anthropic"
    model = "scripted"

    def __init__(self, scores):
        self._scores = list(scores)
        self._cursor = 0

    def call(self, request):
        score = self._scores[self._cursor % len(self._scores)]
        self._cursor += 1
        result = JudgeResult(
            scores={"accuracy": score},
            gate_results={"no_refusal": True},
            notes="scripted",
        )
        return ProviderResponse(
            parsed=result,
            usage={"input_tokens": 100, "output_tokens": 30, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            latency_ms=50.0,
        )

    def capabilities(self):
        from omegaprompt.providers.base import CapabilityTier, ProviderCapabilities

        return ProviderCapabilities(
            provider="anthropic",
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=True,
            supports_llm_judge=True,
            ship_grade_judge=True,
        )


# --------------------------- judge consistency ---------------------------


def test_measure_judge_consistency_identical_scores_max_consistency():
    judge = LLMJudge(provider=_ScriptedJudgeProvider(scores=[4, 4, 4]))
    measurement, _ = measure_judge_consistency(
        judge=judge,
        rubric=_rubric(),
        probe_item=_probe_item(),
        target_response="the answer is 4",
        repeats=3,
    )
    assert measurement.consistency == 1.0
    assert measurement.samples == 3


def test_measure_judge_consistency_high_variance_low_consistency():
    judge = LLMJudge(provider=_ScriptedJudgeProvider(scores=[1, 5, 3]))
    measurement, _ = measure_judge_consistency(
        judge=judge,
        rubric=_rubric(),
        probe_item=_probe_item(),
        target_response="the answer is 4",
        repeats=3,
    )
    # scores normalised to 0.0 / 1.0 / 0.5 -> mean 0.5, stdev ~0.41 -> CV ~0.82 -> consistency ~0.18
    assert 0.0 <= measurement.consistency < 0.5


def test_measure_judge_consistency_anchoring_usage():
    judge = LLMJudge(provider=_ScriptedJudgeProvider(scores=[1, 5, 3]))
    measurement, _ = measure_judge_consistency(
        judge=judge,
        rubric=_rubric(),
        probe_item=_probe_item(),
        target_response="resp",
        repeats=3,
    )
    # Observed span across repeats on dim 'accuracy' = 5-1 = 4; scale span = 4; anchoring = 1.0
    assert measurement.anchoring_usage == 1.0


# --------------------------- schema reliability ---------------------------


def _strict_request_ok() -> ProviderRequest:
    return ProviderRequest(
        system_prompt="SP",
        user_message="probe",
        response_schema_mode=ResponseSchemaMode.FREEFORM,
        output_budget_bucket=OutputBudgetBucket.SMALL,
        reasoning_profile=ReasoningProfile.OFF,
    )


def test_probe_strict_schema_all_success():
    provider = MagicMock()
    provider.call.return_value = ProviderResponse(
        parsed=JudgeResult(scores={"accuracy": 4}, gate_results={"no_refusal": True}),
        usage={},
    )
    m = probe_strict_schema(
        provider=provider,
        output_schema=JudgeResult,
        probes=[_strict_request_ok(), _strict_request_ok(), _strict_request_ok()],
    )
    assert m.schema_reliability == 1.0


def test_probe_strict_schema_mixed_failures():
    provider = MagicMock()
    provider.call.side_effect = [
        ProviderResponse(
            parsed=JudgeResult(scores={"accuracy": 4}, gate_results={"no_refusal": True}),
            usage={},
        ),
        ProviderError("parse failed"),
        ProviderResponse(parsed=None, usage={}),
    ]
    m = probe_strict_schema(
        provider=provider,
        output_schema=JudgeResult,
        probes=[_strict_request_ok(), _strict_request_ok(), _strict_request_ok()],
    )
    # only 1 of 3 passed (parsed object present, no exception)
    assert m.schema_reliability == pytest_approx(1.0 / 3.0)


def pytest_approx(x, rel=1e-6):  # lightweight helper
    import pytest as _pytest

    return _pytest.approx(x, rel=rel)


# --------------------------- context margin ---------------------------


def test_compute_context_margin_negative_on_overflow():
    margin = compute_context_margin(
        system_prompt_chars=50000,
        rubric_chars=20000,
        longest_input_chars=20000,
        longest_reference_chars=10000,
        longest_response_chars=20000,
        context_window_tokens=8000,
    )
    # 120k chars / 3.8 ~ 31.5k tokens vs 8k window -> overflow, margin < 0
    assert margin < 0


def test_compute_context_margin_positive_in_spacious_window():
    margin = compute_context_margin(
        system_prompt_chars=2000,
        rubric_chars=500,
        longest_input_chars=300,
        longest_reference_chars=0,
        longest_response_chars=1000,
        context_window_tokens=32000,
    )
    # ~3.8k chars / 3.8 ~ 1k tokens vs 32k window -> ~97% free
    assert 0.9 < margin <= 1.0


def test_compute_context_margin_zero_window():
    margin = compute_context_margin(
        system_prompt_chars=100,
        rubric_chars=100,
        longest_input_chars=100,
        longest_reference_chars=0,
        longest_response_chars=100,
        context_window_tokens=0,
    )
    assert margin == 0.0


# --------------------------- performance projection ---------------------------


def test_project_performance_extrapolates_from_probes():
    m = project_performance(
        probe_latencies_ms=[500.0, 550.0, 600.0],  # mean 550ms
        dataset_size=10,
        candidates_expected=20,
        calls_per_candidate_per_item=2,
    )
    assert m.mean_call_latency_ms == 550.0
    # 20 candidates * 10 items * 2 calls = 400 calls * 0.55s = 220s
    assert m.projected_wall_time_seconds == pytest_approx(220.0)


def test_project_performance_handles_empty_probes():
    m = project_performance(
        probe_latencies_ms=[],
        dataset_size=10,
        candidates_expected=20,
    )
    assert m.projected_wall_time_seconds == 0.0


# --------------------------- noise floor ---------------------------


def test_noise_floor_zero_when_samples_identical():
    assert noise_floor_estimate(fitness_samples=[0.85, 0.85, 0.85]) == 0.0


def test_noise_floor_positive_when_samples_vary():
    nf = noise_floor_estimate(fitness_samples=[0.80, 0.85, 0.90])
    assert nf > 0


def test_noise_floor_zero_when_too_few_samples():
    assert noise_floor_estimate(fitness_samples=[0.85]) == 0.0
    assert noise_floor_estimate(fitness_samples=[]) == 0.0


# --------------------------- C2: silent degradation -----------------------
#
# A strict-schema probe that returns parsed=None WITHOUT raising a
# ProviderError is a *silent* capability degradation: the endpoint
# accepted the request, returned 200-shaped output, yet produced nothing
# parseable. probe_strict_schema must surface this via
# EndpointMeasurement.silent_degradation_detected (consumed downstream by
# omegaprompt.preflight.adaptation). Pre-fix it was hardcoded False.


def test_probe_strict_schema_sets_silent_degradation_on_parsed_none():
    """RED-if-hardcoded guard: one parsed=None outcome (no ProviderError)
    MUST flip silent_degradation_detected to True.

    This is the assertion that would FAIL if the field were still the
    pre-fix hardcoded ``silent_degradation_detected=False``.
    """
    provider = MagicMock()
    provider.call.side_effect = [
        ProviderResponse(
            parsed=JudgeResult(scores={"accuracy": 4}, gate_results={"no_refusal": True}),
            usage={},
        ),
        ProviderResponse(parsed=None, usage={}),  # silent degradation
    ]
    m = probe_strict_schema(
        provider=provider,
        output_schema=JudgeResult,
        probes=[_strict_request_ok(), _strict_request_ok()],
    )
    assert m.silent_degradation_detected is True
    # schema_reliability still reflects the 1/2 parse-success rate.
    assert m.schema_reliability == pytest_approx(0.5)


def test_probe_strict_schema_no_silent_degradation_when_all_parse():
    """A clean run (all parsed, or explicit ProviderError) must NOT flag
    silent degradation — ProviderError is a loud failure, not silent."""
    provider = MagicMock()
    provider.call.side_effect = [
        ProviderResponse(
            parsed=JudgeResult(scores={"accuracy": 4}, gate_results={"no_refusal": True}),
            usage={},
        ),
        ProviderError("loud failure"),  # explicit error, not silent
    ]
    m = probe_strict_schema(
        provider=provider,
        output_schema=JudgeResult,
        probes=[_strict_request_ok(), _strict_request_ok()],
    )
    assert m.silent_degradation_detected is False


def test_empirical_preflight_warns_on_silent_degradation():
    """When the schema probe runs and observes a parsed=None outcome,
    empirical_preflight flips the field True and emits a warning."""

    class _NoneOnSecondProvider:
        name = "anthropic"
        model = "scripted"

        def __init__(self):
            self._n = 0

        def call(self, request):
            self._n += 1
            if self._n == 2:
                return ProviderResponse(parsed=None, usage={})
            return ProviderResponse(
                parsed=JudgeResult(scores={"accuracy": 4}, gate_results={"no_refusal": True}),
                usage={},
                latency_ms=5.0,
            )

        def capabilities(self):
            from omegaprompt.providers.base import CapabilityTier, ProviderCapabilities

            return ProviderCapabilities(
                provider="anthropic",
                tier=CapabilityTier.CLOUD,
                supports_strict_schema=True,
                supports_llm_judge=False,
                ship_grade_judge=False,
            )

    judge = LLMJudge(provider=_ScriptedJudgeProvider(scores=[4, 4, 4]))
    _, endpoint, _, warnings = empirical_preflight(
        judge=judge,
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="4",
        consistency_repeats=1,
        strict_schema_provider=_NoneOnSecondProvider(),
        strict_schema_output=JudgeResult,
        strict_schema_probes=[_strict_request_ok(), _strict_request_ok()],
    )
    assert endpoint.silent_degradation_detected is True
    assert any("silent_degradation_detected = True" in w for w in warnings)


def test_empirical_preflight_unprobed_path_warns_not_probed():
    """Fail-closed/unprobed path: no schema probe supplied. The field
    stays False BUT a warning must say degradation was NOT probed, so
    'False' is never misread as 'measured: clean'."""
    judge = LLMJudge(provider=_ScriptedJudgeProvider(scores=[4, 4, 4]))
    _, endpoint, _, warnings = empirical_preflight(
        judge=judge,
        rubric=_rubric(),
        probe_item=_probe_item(),
        probe_response="4",
        consistency_repeats=1,
        # No strict_schema_* args -> fail-closed path.
    )
    assert endpoint.silent_degradation_detected is False
    assert any("schema degradation" in w and "not probed" in w for w in warnings)

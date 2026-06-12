"""Tests for the headline summary + scorecard helpers (0.7.0).

Covers:
  * ``judge_noise_floor`` = 1 - consistency, clamped, dict + model input.
  * ``build_summary`` shape, schema_version, unmeasured-field extraction,
    timing fields excluded (byte-stability), additive-only contract.
  * ``render_scorecard`` md/html stdlib-only, deterministic (no timestamp),
    headline number present, bad-format raises.
  * Determinism: two identical inputs render byte-identical scorecards.
"""

from __future__ import annotations

import pytest

from mini_omega_lock import build_summary, judge_noise_floor, render_scorecard
from mini_omega_lock.summary import (
    SUMMARY_SCHEMA_VERSION,
    summary_json,
)


_JQ = {"consistency": 0.8, "anchoring_usage": 0.25, "scale_monotonic": True, "samples": 3}
_EP = {
    "schema_reliability": 0.95,
    "context_budget_margin": 0.6,
    "caching_active": False,
    "silent_degradation_detected": False,
}
_PF = {"mean_call_latency_ms": 12.3, "projected_wall_time_seconds": 45.6, "noise_floor": 0.04}


# ---------------------------------------------------------------------------
# judge_noise_floor
# ---------------------------------------------------------------------------


def test_judge_noise_floor_is_one_minus_consistency():
    assert judge_noise_floor({"consistency": 0.8}) == pytest.approx(0.2)
    assert judge_noise_floor({"consistency": 1.0}) == 0.0
    assert judge_noise_floor({"consistency": 0.0}) == 1.0


def test_judge_noise_floor_clamps_out_of_range():
    assert judge_noise_floor({"consistency": 1.5}) == 0.0
    assert judge_noise_floor({"consistency": -0.5}) == 1.0


def test_judge_noise_floor_accepts_pydantic_model():
    from omegaprompt.preflight.contracts import JudgeQualityMeasurement

    m = JudgeQualityMeasurement(
        consistency=0.75, anchoring_usage=0.0, scale_monotonic=False, samples=3
    )
    assert judge_noise_floor(m) == pytest.approx(0.25)


def test_judge_noise_floor_rejects_garbage():
    with pytest.raises(TypeError):
        judge_noise_floor(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------


def test_build_summary_shape_and_schema_version():
    s = build_summary(_JQ, _EP, _PF, warnings=[])
    assert s["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert s["judge_noise_floor"] == pytest.approx(0.2)
    assert s["judge_consistency"] == pytest.approx(0.8)
    assert s["schema_reliability"] == pytest.approx(0.95)
    assert s["context_budget_margin"] == pytest.approx(0.6)
    assert s["fitness_noise_floor"] == pytest.approx(0.04)
    assert s["scale_monotonic"] is True
    assert s["all_fields_measured"] is True
    assert s["unmeasured_fields"] == []


def test_build_summary_excludes_timing_fields():
    """Timing must NOT leak into the summary (byte-stability across machines)."""
    s = build_summary(_JQ, _EP, _PF, warnings=[])
    assert "mean_call_latency_ms" not in s
    assert "projected_wall_time_seconds" not in s


def test_build_summary_extracts_unmeasured_fields_from_warnings():
    warnings = [
        "endpoint.schema_reliability not measured — strict probe absent",
        "performance.noise_floor not measured — pass fitness_samples",
        "judge_quality.scale_monotonic not measured — pass monotonic_examples",
    ]
    s = build_summary(_JQ, _EP, _PF, warnings=warnings)
    assert s["all_fields_measured"] is False
    assert "schema_reliability" in s["unmeasured_fields"]
    assert "fitness_noise_floor" in s["unmeasured_fields"]
    assert "scale_monotonic" in s["unmeasured_fields"]
    assert s["warning_count"] == 3


def test_build_summary_is_deterministic_for_same_input():
    a = build_summary(_JQ, _EP, _PF, warnings=["x not measured"])
    b = build_summary(_JQ, _EP, _PF, warnings=["x not measured"])
    assert summary_json(a) == summary_json(b)


# ---------------------------------------------------------------------------
# render_scorecard
# ---------------------------------------------------------------------------


def test_scorecard_markdown_contains_headline():
    s = build_summary(_JQ, _EP, _PF)
    md = render_scorecard(s, "md")
    assert "# mini-omega-lock preflight scorecard" in md
    assert "Judge noise floor" in md
    assert SUMMARY_SCHEMA_VERSION in md


def test_scorecard_html_is_self_contained_and_escaped():
    s = build_summary(_JQ, _EP, _PF)
    page = render_scorecard(s, "html")
    assert page.startswith("<!doctype html>")
    assert "<style>" in page  # inline CSS, no external asset
    assert "http://" not in page and "https://" not in page  # no external links
    assert "Judge noise floor" in page


def test_scorecard_bad_format_raises():
    s = build_summary(_JQ, _EP, _PF)
    with pytest.raises(ValueError):
        render_scorecard(s, "pdf")


def test_scorecard_is_deterministic_no_timestamp():
    """Two renders of the same summary must be byte-identical (no clock)."""
    s = build_summary(_JQ, _EP, _PF)
    assert render_scorecard(s, "md") == render_scorecard(s, "md")
    assert render_scorecard(s, "html") == render_scorecard(s, "html")


def test_scorecard_accepts_markdown_alias():
    s = build_summary(_JQ, _EP, _PF)
    assert render_scorecard(s, "markdown") == render_scorecard(s, "md")


# ---------------------------------------------------------------------------
# Integration with empirical_preflight (offline scripted judge)
# ---------------------------------------------------------------------------


def test_summary_from_real_empirical_preflight():
    from omegaprompt.domain.dataset import DatasetItem
    from omegaprompt.domain.judge import Dimension, HardGate, JudgeResult, JudgeRubric
    from omegaprompt.judges.llm_judge import LLMJudge
    from omegaprompt.providers.base import (
        CapabilityTier,
        ProviderCapabilities,
        ProviderResponse,
    )

    from mini_omega_lock import empirical_preflight

    class _Scripted:
        name = "scripted"
        model = "scripted"

        def call(self, request):  # noqa: ANN001
            return ProviderResponse(
                parsed=JudgeResult(scores={"accuracy": 4}, gate_results={"no_refusal": True}),
                usage={"input_tokens": 5, "output_tokens": 2},
                latency_ms=5.0,
            )

        def capabilities(self):
            return ProviderCapabilities(
                provider="scripted",
                tier=CapabilityTier.CLOUD,
                supports_strict_schema=True,
                supports_llm_judge=True,
                ship_grade_judge=True,
            )

    rubric = JudgeRubric(
        dimensions=[Dimension(name="accuracy", description="x", weight=1.0, scale=(1, 5))],
        hard_gates=[HardGate(name="no_refusal", description="g", evaluator="judge")],
    )
    jq, ep, pf, warnings = empirical_preflight(
        judge=LLMJudge(provider=_Scripted()),
        rubric=rubric,
        probe_item=DatasetItem(id="p", input="2+2", reference="4"),
        probe_response="4",
        consistency_repeats=3,
    )
    s = build_summary(jq, ep, pf, warnings)
    # Scripted judge returns the same score each call -> consistency 1.0 ->
    # noise floor 0.0.
    assert s["judge_noise_floor"] == 0.0
    assert s["judge_consistency"] == 1.0
    # Schema probe not supplied in this call -> fail-closed + flagged.
    assert "schema_reliability" in s["unmeasured_fields"]
    assert s["all_fields_measured"] is False

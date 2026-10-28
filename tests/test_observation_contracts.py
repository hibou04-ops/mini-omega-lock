"""Actual observations, sample reuse and failure cost have explicit provenance."""
import pytest
from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.judge import Dimension, HardGate, JudgeResult, JudgeRubric

from mini_omega_lock.probes import empirical_preflight, noise_floor_estimate
from mini_omega_lock.summary import build_summary


class Judge:
    def __init__(self, fail_at=None):
        self.calls=0
        self.fail_at=fail_at

    def score(self, **kwargs):
        self.calls+=1
        if self.calls == self.fail_at: raise RuntimeError("scripted failure")
        return JudgeResult(scores={"q":4},gate_results={"g":self.calls%2==1}), {"input_tokens":10,"output_tokens":2}


def run(judge, **kwargs):
    return empirical_preflight(judge=judge,
        rubric=JudgeRubric(dimensions=[Dimension(name="q",description="q",weight=1)],
            hard_gates=[HardGate(name="g",description="g",evaluator="judge")]),
        probe_item=DatasetItem(id="p",input="question"), probe_response="answer", **kwargs)


@pytest.mark.parametrize("consistency,gates,expected", [(3,5,5),(7,3,7),(3,0,3)])
def test_shared_batch_has_real_repeats_and_no_double_count(consistency,gates,expected):
    judge=Judge()
    jq,ep,pf,warnings=run(judge, consistency_repeats=consistency,gate_flip_repeats=gates)
    assert isinstance(warnings,list)
    assert judge.calls == warnings.probe_accounting["attempted_calls"] == expected
    assert jq.samples == consistency
    batch=warnings.probe_accounting["observation_batches"]["shared_judge"]
    assert batch["consistency_samples"] == consistency
    assert batch["gate_samples"] == gates
    assert warnings.probe_accounting["successful_usage"]["input_tokens"] == expected*10
    if gates:
        assert warnings.probe_accounting["gate_flip_rates"]["g"]["samples"] == gates
        assert warnings.probe_accounting["gate_flip_rates"]["g"]["flip_rate"] == 1


def test_partial_failure_records_paid_attempt_and_timing_without_false_measurement():
    jq,ep,pf,warnings=run(Judge(fail_at=2))
    accounting=warnings.probe_accounting
    assert accounting["attempted_calls"] == 2
    assert accounting["successful_calls"] == accounting["failed_calls"] == 1
    assert accounting["elapsed_ms"] > 0
    assert accounting["total_elapsed_ms"] >= accounting["elapsed_ms"]
    assert accounting["failed_call_usage_unknown"] is True
    assert accounting["provider_internal_retries"] is None
    assert warnings.measurement_status["judge_consistency"] == "failed"
    assert pf.mean_call_latency_ms == 0
    # Machine status survives changed/localized warning strings.
    warnings.clear()
    summary=build_summary(jq,ep,pf,warnings)
    assert summary["all_fields_measured"] is False
    assert "judge_consistency" in summary["unmeasured_fields"]


def test_single_sample_and_context_projection_are_not_measured_quality():
    jq,ep,pf,warnings=run(Judge(),consistency_repeats=1,gate_flip_repeats=0)
    assert jq.samples == 1
    assert warnings.measurement_status["judge_consistency"] == "insufficient_samples"
    assert warnings.measurement_status["context_budget_margin"] == "estimated"
    assert warnings.measurement_status["schema_reliability"] == "unmeasured"


def test_zero_mean_cv_uses_explicit_convention_not_measured_relative_variability():
    class ZeroJudge(Judge):
        def score(self, **kwargs):
            self.calls+=1
            return JudgeResult(scores={"q":1},gate_results={"g":True}), {}
    jq,ep,pf,warnings=run(ZeroJudge())
    assert jq.consistency == 1.0
    assert warnings.measurement_status["judge_consistency"] == "estimated"
    assert "CV is undefined" in " ".join(warnings)


def test_mcp_fitness_standard_deviation_does_not_claim_ab_significance():
    from mini_omega_lock.mcp.server import noise_floor_estimate as tool
    result=tool([0.5])
    assert result["noise_floor"] == 0
    assert result["measurement_status"] == "insufficient_samples"
    assert result["quality_assessment"] == "not_requested"
    assert tool([0.4,0.6])["measurement_status"] == "measured"


@pytest.mark.parametrize("value", [float("nan"),float("inf"),-float("inf")])
def test_nonfinite_fitness_is_rejected(value):
    with pytest.raises(ValueError,match="finite"): noise_floor_estimate(fitness_samples=[0.1,value])


@pytest.mark.parametrize("repeats", [0,-1,True,1.5])
def test_invalid_repeat_counts_do_not_call_provider(repeats):
    judge=Judge()
    with pytest.raises(ValueError): run(judge,consistency_repeats=repeats)
    assert judge.calls == 0

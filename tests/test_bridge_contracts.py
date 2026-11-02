"""Optional integration against actual parent contracts, without live providers.

The leaf's required dependencies stay unchanged. Missing omegaprompt skips this
module; an installed parent with broken imports or changed contracts fails.
"""

from __future__ import annotations

from dataclasses import fields
import importlib
import importlib.util
import json

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError

from mini_omega_lock._vendor.domain import dataset, enums, judge, profiles
from mini_omega_lock._vendor.judges import base as judge_base
from mini_omega_lock._vendor.judges.llm_judge import LLMJudge
from mini_omega_lock._vendor.preflight import adaptation, contracts
from mini_omega_lock._vendor.providers import base as provider_base
from mini_omega_lock.bridge import adapt_omegaprompt_provider, to_omegaprompt_report


if importlib.util.find_spec("omegaprompt") is None:
    pytest.skip("optional [bridge] integration requires omegaprompt", allow_module_level=True)

parent_dataset = importlib.import_module("omegaprompt.domain.dataset")
parent_enums = importlib.import_module("omegaprompt.domain.enums")
parent_judge = importlib.import_module("omegaprompt.domain.judge")
parent_profiles = importlib.import_module("omegaprompt.domain.profiles")
parent_judge_base = importlib.import_module("omegaprompt.judges.base")
parent_llm_judge = importlib.import_module("omegaprompt.judges.llm_judge")
parent_provider = importlib.import_module("omegaprompt.providers.base")
parent_contracts = importlib.import_module("omegaprompt.preflight.contracts")
parent_adaptation = importlib.import_module("omegaprompt.preflight.adaptation")
pytestmark = pytest.mark.bridge

ITEM = {"id": "probe", "input": "검증 😀", "reference": None,
        "metadata": {"nested": [1, None, {"trusted": False}]}, "external_tag": "retained"}
DIMENSION = {"name": "quality", "description": "정확성", "weight": 1.0, "scale": [0, 4]}
GATE = {"name": "format", "description": "valid format", "evaluator": "judge"}
RUBRIC = {"dimensions": [DIMENSION], "hard_gates": [GATE]}
RESULT = {"scores": {"quality": 4}, "gate_results": {"format": True}, "notes": "근거 — 😀"}
FINDING = {"trap_id": "train_test_id_overlap", "label": "UNRESOLVED", "hypothesis": "check inputs",
           "severity": "high", "note": "보류 — 😀", "remediation": "supply a holdout", "cite": None}
EVENT = {"capability": "strict_schema", "requested": "strict_schema", "applied": "json_object_parse",
         "reason": "offline fixture", "user_visible_note": "검증 강도 감소", "affects_guarded_boundary": True}
CAPABILITIES = {"provider": "scripted", "tier": "tier_2_cloud_grade", "supports_strict_schema": True,
                "supports_json_object": True, "supports_reasoning_profiles": False,
                "supports_usage_accounting": True, "supports_llm_judge": True, "ship_grade_judge": True,
                "supports_tools": False, "experimental": False, "placeholder": False, "notes": ["offline 😀"]}
REQUEST = {"system_prompt": "Judge fairly", "user_message": "검증", "few_shots": [{"input": "1+1", "output": "2"}],
           "reasoning_profile": "deep", "output_budget_bucket": "large", "response_schema_mode": "json_object",
           "tool_policy_variant": "tool_required", "execution_profile": "expedition", "output_schema": None}
RESPONSE = {"text": "응답", "parsed": None, "usage": {"input_tokens": 7, "output_tokens": 3},
            "finish_reason": "stop", "latency_ms": 12.5, "degraded_capabilities": [EVENT], "capability_notes": ["offline"]}
QUALITY = {"consistency": 0.8, "anchoring_usage": 0.6, "scale_monotonic": False, "samples": 5}
ENDPOINT = {"schema_reliability": 0.25, "context_budget_margin": -0.2, "caching_active": True,
            "silent_degradation_detected": True}
PERFORMANCE = {"mean_call_latency_ms": 12.5, "projected_wall_time_seconds": 123.0, "noise_floor": 0.12}
REPORT = {"analytical_findings": [FINDING], "judge_quality": QUALITY, "endpoint": ENDPOINT,
          "performance": PERFORMANCE, "status": "adapt", "blocker_reasons": ["manual review"],
          "warnings": ["warning — 😀"],
          "measurement_status": {"a": "measured", "b": "unmeasured", "c": "insufficient_samples",
                                 "d": "failed", "e": "estimated", "f": "not_applicable"},
          "probe_accounting": {"calls": 5, "failed_tokens": None, "details": {"attempts": [1, 2]}}}
OVERRIDE = {"parameter": "min_kc4", "default": 0.7, "applied": 0.9, "reason": "measured noise"}
PLAN = {"min_kc4_override": 0.9, "max_gap_override": 0.1, "unlock_k_override": 3, "skip_axes": ["output_budget"],
        "rescore_count": 2, "rubric_weight_overrides": {"quality": 0.0}, "schema_mode_fallback": "json_object",
        "judge_ensemble_shift": 0.1, "candidate_budget_cap": 12, "dataset_reorder_for_cache": True,
        "require_manual_review_reasons": ["independent evidence needed"], "overrides": [OVERRIDE],
        "rationale": ["보수적 권고"], "preserves_discipline": True}

MODEL_CASES = [
    (dataset.DatasetItem, parent_dataset.DatasetItem, ITEM),
    (dataset.Dataset, parent_dataset.Dataset, {"items": [ITEM]}),
    (judge.Dimension, parent_judge.Dimension, DIMENSION),
    (judge.HardGate, parent_judge.HardGate, GATE),
    (judge.JudgeRubric, parent_judge.JudgeRubric, RUBRIC),
    (judge.HardGateFlags, parent_judge.HardGateFlags, {"no_refusal": False, "format_valid": True, "no_safety_violation": True}),
    (judge.JudgeResult, parent_judge.JudgeResult, RESULT),
    (profiles.BoundaryWarning, parent_profiles.BoundaryWarning,
     {"code": "review", "category": "validation strength", "severity": "critical", "summary": "review needed",
      "detail": "근거 부족", "affects_guarded_boundary": False}),
    (profiles.RelaxedSafeguard, parent_profiles.RelaxedSafeguard,
     {"name": "budget", "reason": "bounded experiment", "increased_risk": "weaker validation"}),
    (provider_base.CapabilityEvent, parent_provider.CapabilityEvent, EVENT),
    (provider_base.ProviderCapabilities, parent_provider.ProviderCapabilities, CAPABILITIES),
    (provider_base.ProviderRequest, parent_provider.ProviderRequest, REQUEST),
    (provider_base.ProviderResponse, parent_provider.ProviderResponse, RESPONSE),
    (contracts.AnalyticalFinding, parent_contracts.AnalyticalFinding, FINDING),
    (contracts.JudgeQualityMeasurement, parent_contracts.JudgeQualityMeasurement, QUALITY),
    (contracts.EndpointMeasurement, parent_contracts.EndpointMeasurement, ENDPOINT),
    (contracts.PerformanceMeasurement, parent_contracts.PerformanceMeasurement, PERFORMANCE),
    (contracts.PreflightReport, parent_contracts.PreflightReport, REPORT),
    (adaptation.ParameterOverride, parent_adaptation.ParameterOverride, OVERRIDE),
    (adaptation.AdaptationPlan, parent_adaptation.AdaptationPlan, PLAN),
]


def _semantic_schema(value):
    """Remove schema prose only; field names, defaults and enum data are intact."""
    if not isinstance(value, dict):
        return value
    result = {key: item for key, item in value.items() if key != "description"}
    for keyword in ("properties", "$defs", "definitions", "patternProperties", "dependentSchemas"):
        if isinstance(result.get(keyword), dict):
            result[keyword] = {name: _semantic_schema(schema) for name, schema in result[keyword].items()}
    for keyword in ("items", "additionalProperties", "unevaluatedProperties", "contains",
                    "propertyNames", "not", "if", "then", "else", "contentSchema"):
        if keyword in result:
            result[keyword] = _semantic_schema(result[keyword])
    for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
        if isinstance(result.get(keyword), list):
            result[keyword] = [_semantic_schema(schema) for schema in result[keyword]]
    return result


def test_schema_comparison_retains_description_fields_and_arbitrary_default_data():
    schema = {
        "description": "documentation only",
        "properties": {"description": {"type": "string", "default": "kept", "minLength": 1,
                                       "description": "field documentation"}},
        "required": ["description"],
        "default": {"description": "actual data", "properties": {"description": "also data"}},
    }
    normalized = _semantic_schema(schema)
    assert normalized["properties"]["description"] == {"type": "string", "default": "kept", "minLength": 1}
    assert normalized["required"] == ["description"]
    assert normalized["default"] == schema["default"]


@pytest.mark.parametrize("leaf,parent,payload", MODEL_CASES, ids=[case[0].__name__ for case in MODEL_CASES])
def test_models_preserve_fields_schema_and_json_in_both_directions(leaf, parent, payload):
    assert leaf is not parent
    assert set(leaf.model_fields) == set(parent.model_fields)
    schema = _semantic_schema(leaf.model_json_schema())
    assert set(schema["properties"]) == set(leaf.model_fields)
    assert schema == _semantic_schema(parent.model_json_schema())
    local_record = leaf.model_validate(payload)
    parent_record = parent.model_validate_json(local_record.model_dump_json())
    returned_local = leaf.model_validate_json(parent_record.model_dump_json())
    assert type(parent_record) is parent and type(returned_local) is leaf
    assert local_record.model_dump(mode="json") == parent_record.model_dump(mode="json") == returned_local.model_dump(mode="json")
    parent_first = parent.model_validate(payload)
    local_second = leaf.model_validate_json(parent_first.model_dump_json())
    returned_parent = parent.model_validate_json(local_second.model_dump_json())
    assert returned_parent.model_dump(mode="json") == parent_first.model_dump(mode="json")


ENUM_CASES = [
    (enums.ReasoningProfile, parent_enums.ReasoningProfile),
    (enums.OutputBudgetBucket, parent_enums.OutputBudgetBucket),
    (enums.ResponseSchemaMode, parent_enums.ResponseSchemaMode),
    (enums.ToolPolicyVariant, parent_enums.ToolPolicyVariant),
    (profiles.ExecutionProfile, parent_profiles.ExecutionProfile),
    (profiles.ShipRecommendation, parent_profiles.ShipRecommendation),
    (profiles.RiskCategory, parent_profiles.RiskCategory),
    (provider_base.CapabilityTier, parent_provider.CapabilityTier),
    (contracts.PreflightSeverity, parent_contracts.PreflightSeverity),
    (contracts.PreflightStatus, parent_contracts.PreflightStatus),
]


@pytest.mark.parametrize("leaf,parent", ENUM_CASES, ids=[case[0].__name__ for case in ENUM_CASES])
def test_enum_members_and_json_values_roundtrip(leaf, parent):
    assert leaf is not parent
    assert [(name, item.value) for name, item in leaf.__members__.items()] == [
        (name, item.value) for name, item in parent.__members__.items()]
    for member in leaf:
        foreign = TypeAdapter(parent).validate_json(TypeAdapter(leaf).dump_json(member))
        returned = TypeAdapter(leaf).validate_json(TypeAdapter(parent).dump_json(foreign))
        assert type(foreign) is parent and type(returned) is leaf
        assert returned.value == member.value


@pytest.mark.parametrize("leaf,parent,payload,error_type,error_location", [
    (dataset.DatasetItem, parent_dataset.DatasetItem, {"id": "a", "input": ""}, "string_too_short", ("input",)),
    (judge.Dimension, parent_judge.Dimension, {**DIMENSION, "weight": -1}, "greater_than_equal", ("weight",)),
    (judge.HardGate, parent_judge.HardGate, {**GATE, "evaluator": "unknown"}, "literal_error", ("evaluator",)),
    (judge.JudgeRubric, parent_judge.JudgeRubric, {"dimensions": [DIMENSION, DIMENSION]}, "value_error", ("dimensions",)),
    (profiles.BoundaryWarning, parent_profiles.BoundaryWarning,
     {"code": "x", "category": "unknown", "summary": "x"}, "enum", ("category",)),
    (provider_base.ProviderCapabilities, parent_provider.ProviderCapabilities,
     {**CAPABILITIES, "tier": "cloud"}, "enum", ("tier",)),
    (provider_base.ProviderRequest, parent_provider.ProviderRequest,
     {**REQUEST, "output_schema": "JudgeResult"}, "is_subclass_of", ("output_schema",)),
    (provider_base.ProviderResponse, parent_provider.ProviderResponse,
     {**RESPONSE, "unexpected": True}, "extra_forbidden", ("unexpected",)),
    (contracts.JudgeQualityMeasurement, parent_contracts.JudgeQualityMeasurement,
     {**QUALITY, "consistency": 1.1}, "less_than_equal", ("consistency",)),
    (contracts.PerformanceMeasurement, parent_contracts.PerformanceMeasurement,
     {**PERFORMANCE, "noise_floor": -1}, "greater_than_equal", ("noise_floor",)),
    (contracts.PreflightReport, parent_contracts.PreflightReport,
     {**REPORT, "measurement_status": {"noise": "approved"}}, "literal_error", ("measurement_status", "noise")),
    (adaptation.AdaptationPlan, parent_adaptation.AdaptationPlan,
     {**PLAN, "unexpected": True}, "extra_forbidden", ("unexpected",)),
])
def test_validation_error_types_and_locations_match(leaf, parent, payload, error_type, error_location):
    observed = []
    for model in (leaf, parent):
        with pytest.raises(ValidationError) as caught:
            model.model_validate(payload)
        observed.append([(item["type"], item["loc"]) for item in caught.value.errors()])
    assert observed[0] == observed[1]
    assert (error_type, error_location) in observed[0]


def test_request_python_schema_class_uses_python_boundary_not_json():
    class CustomAnswer(BaseModel):
        answer: str

    for source, destination in ((provider_base.ProviderRequest, parent_provider.ProviderRequest),
                                (parent_provider.ProviderRequest, provider_base.ProviderRequest)):
        request = source.model_validate({**REQUEST, "output_schema": CustomAnswer})
        converted = destination.model_validate(request.model_dump())
        assert converted.output_schema is CustomAnswer
        with pytest.raises(PydanticSerializationError):
            request.model_dump_json()


def test_generic_parsed_response_does_not_promise_concrete_json_schema_reconstruction():
    # Both APIs annotate parsed as BaseModel, not JudgeResult. An explicit
    # request.output_schema is needed to reconstruct the concrete payload.
    for response_type, result_type in ((provider_base.ProviderResponse, judge.JudgeResult),
                                       (parent_provider.ProviderResponse, parent_judge.JudgeResult)):
        response = response_type(parsed=result_type.model_validate(RESULT))
        assert response.model_dump(mode="json")["parsed"] == {}
        explicit = {**response.model_dump(mode="json"), "parsed": response.parsed.model_dump(mode="json")}
        assert explicit["parsed"] == RESULT
        recovered = result_type.model_validate(explicit["parsed"])
        assert recovered.model_dump(mode="json") == RESULT


def test_judge_outcome_dataclass_fields_tuple_protocol_and_explicit_json_roundtrip():
    assert [field.name for field in fields(judge_base.JudgeOutcome)] == [field.name for field in fields(parent_judge_base.JudgeOutcome)]
    for outcome_type, result_type, event_type, destination in (
        (judge_base.JudgeOutcome, judge.JudgeResult, provider_base.CapabilityEvent, parent_judge_base.JudgeOutcome),
        (parent_judge_base.JudgeOutcome, parent_judge.JudgeResult, parent_provider.CapabilityEvent, judge_base.JudgeOutcome),
    ):
        result = result_type.model_validate(RESULT)
        usage = {"input_tokens": 7, "output_tokens": 3}
        outcome = outcome_type(result, usage, [event_type.model_validate(EVENT)], 12.5)
        assert tuple(outcome) == (result, usage)
        wire = TypeAdapter(outcome_type).dump_json(outcome)
        converted = TypeAdapter(destination).validate_json(wire)
        returned = TypeAdapter(outcome_type).validate_json(TypeAdapter(destination).dump_json(converted))
        assert json.loads(TypeAdapter(outcome_type).dump_json(returned)) == json.loads(wire)


def test_explicit_preflight_bridge_preserves_all_nested_measurement_states():
    leaf = contracts.PreflightReport.model_validate(REPORT)
    converted = to_omegaprompt_report(leaf)
    assert type(converted) is parent_contracts.PreflightReport
    assert type(converted.status) is parent_contracts.PreflightStatus
    assert converted.model_dump(mode="json") == leaf.model_dump(mode="json")
    returned = contracts.PreflightReport.model_validate_json(converted.model_dump_json())
    assert returned.measurement_status == leaf.measurement_status
    assert returned.probe_accounting == leaf.probe_accounting
    assert returned.model_dump(mode="json") == leaf.model_dump(mode="json")


class ParentProvider:
    """Offline transport returning the actual parent's result/error classes."""
    name = "scripted"
    model = "contract-fixture"

    def __init__(self, *, failure=None, parsed=None):
        self.failure = failure
        self.parsed = parent_judge.JudgeResult.model_validate(RESULT) if parsed is None else parsed
        self.requests = []

    def capabilities(self):
        return parent_provider.ProviderCapabilities.model_validate(CAPABILITIES)

    def call(self, request):
        assert type(request) is parent_provider.ProviderRequest
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        return parent_provider.ProviderResponse(
            parsed=self.parsed, usage=RESPONSE["usage"], latency_ms=12.5,
            degraded_capabilities=[parent_provider.CapabilityEvent.model_validate(EVENT)], capability_notes=["offline"],
        )


def test_actual_provider_bridge_preserves_capabilities_parsed_scores_and_degradation():
    provider = ParentProvider()
    bridge = adapt_omegaprompt_provider(provider)
    caps = bridge.capabilities()
    assert type(caps) is provider_base.ProviderCapabilities
    assert caps.model_dump(mode="json") == provider.capabilities().model_dump(mode="json")
    outcome = LLMJudge(provider=bridge).score(
        rubric=judge.JudgeRubric.model_validate(RUBRIC), item=dataset.DatasetItem.model_validate(ITEM), target_response="answer",
    )
    assert type(outcome.result) is judge.JudgeResult
    assert outcome.result.model_dump(mode="json") == RESULT
    assert outcome.usage == RESPONSE["usage"] and outcome.latency_ms == 12.5
    assert [event.model_dump(mode="json") for event in outcome.degraded_capabilities] == [EVENT]
    assert provider.requests[0].output_schema is judge.JudgeResult


def test_provider_bridge_preserves_an_arbitrary_user_schema_class():
    class CustomAnswer(BaseModel):
        answer: str

    provider = ParentProvider(parsed=CustomAnswer(answer="정답 😀"))
    response = adapt_omegaprompt_provider(provider).call(
        provider_base.ProviderRequest.model_validate({**REQUEST, "output_schema": CustomAnswer}))
    assert provider.requests[0].output_schema is CustomAnswer
    assert type(response.parsed) is CustomAnswer and response.parsed.answer == "정답 😀"


@pytest.mark.parametrize("leaf,parent", [(provider_base.ProviderError, parent_provider.ProviderError),
                                       (judge_base.JudgeError, parent_judge_base.JudgeError)])
def test_error_classes_are_distinct_runtime_errors_not_json_models(leaf, parent):
    assert leaf is not parent
    for error_type in (leaf, parent):
        error = error_type("offline — 😀")
        assert isinstance(error, RuntimeError)
        assert error.args == ("offline — 😀",)
        assert str(error) == "offline — 😀"
        assert not hasattr(error, "model_dump")


def test_provider_and_judge_error_translation_preserves_original_cause():
    original = parent_provider.ProviderError("offline failure")
    provider = ParentProvider(failure=original)
    bridge = adapt_omegaprompt_provider(provider)
    request = provider_base.ProviderRequest.model_validate({**REQUEST, "output_schema": judge.JudgeResult})
    with pytest.raises(provider_base.ProviderError) as local_error:
        bridge.call(request)
    assert str(local_error.value) == str(original)
    assert local_error.value.__cause__ is original
    with pytest.raises(judge_base.JudgeError) as local_judge_error:
        LLMJudge(provider=bridge).score(rubric=judge.JudgeRubric.model_validate(RUBRIC),
                                      item=dataset.DatasetItem.model_validate(ITEM), target_response="answer")
    with pytest.raises(parent_judge_base.JudgeError) as parent_judge_error:
        parent_llm_judge.LLMJudge(provider=provider).score(rubric=parent_judge.JudgeRubric.model_validate(RUBRIC),
            item=parent_dataset.DatasetItem.model_validate(ITEM), target_response="answer")
    assert str(local_judge_error.value) == str(parent_judge_error.value)
    assert isinstance(local_judge_error.value.__cause__, provider_base.ProviderError)
    assert local_judge_error.value.__cause__.__cause__ is original
    assert parent_judge_error.value.__cause__ is original

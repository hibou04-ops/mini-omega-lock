# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Unified provider contracts plus capability/degradation reporting."""

from __future__ import annotations

import os
from enum import Enum
from json import JSONDecodeError
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from mini_omega_lock._vendor.domain.enums import (
    OutputBudgetBucket,
    ReasoningProfile,
    ResponseSchemaMode,
    ToolPolicyVariant,
)
from mini_omega_lock._vendor.domain.profiles import ExecutionProfile

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    """Raised when a provider call fails in a way the caller can surface."""


class CapabilityTier(str, Enum):
    """Capability tier used in docs, reporting, and risk policy."""

    CORE = "tier_1_core_parity"
    CLOUD = "tier_2_cloud_grade"
    LOCAL = "tier_3_local"


class CapabilityEvent(BaseModel):
    """One explicit adapter fallback or degraded feature."""

    model_config = ConfigDict(extra="forbid")

    capability: str
    requested: str
    applied: str
    reason: str
    user_visible_note: str
    affects_guarded_boundary: bool = True


class ProviderCapabilities(BaseModel):
    """Static capability summary for one provider adapter."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    tier: CapabilityTier
    supports_strict_schema: bool = False
    supports_json_object: bool = False
    supports_reasoning_profiles: bool = False
    supports_usage_accounting: bool = True
    supports_llm_judge: bool = False
    ship_grade_judge: bool = False
    supports_tools: bool = False
    experimental: bool = False
    placeholder: bool = False
    notes: list[str] = Field(default_factory=list)


class ProviderRequest(BaseModel):
    """The provider-neutral call payload."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    system_prompt: str
    user_message: str
    few_shots: list[dict[str, str]] = Field(default_factory=list)

    reasoning_profile: ReasoningProfile = ReasoningProfile.STANDARD
    output_budget_bucket: OutputBudgetBucket = OutputBudgetBucket.MEDIUM
    response_schema_mode: ResponseSchemaMode = ResponseSchemaMode.FREEFORM
    tool_policy_variant: ToolPolicyVariant = ToolPolicyVariant.NO_TOOLS
    execution_profile: ExecutionProfile = ExecutionProfile.GUARDED

    # Required when response_schema_mode == STRICT_SCHEMA. Otherwise ignored.
    output_schema: type[BaseModel] | None = None

    @model_validator(mode="before")
    @classmethod
    def _compat_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "output_budget" in data and "output_budget_bucket" not in data:
            data["output_budget_bucket"] = data.pop("output_budget")
        if "tool_policy" in data and "tool_policy_variant" not in data:
            data["tool_policy_variant"] = data.pop("tool_policy")
        return data

    @property
    def output_budget(self) -> OutputBudgetBucket:
        return self.output_budget_bucket

    @property
    def tool_policy(self) -> ToolPolicyVariant:
        return self.tool_policy_variant


class ProviderResponse(BaseModel):
    """The provider-neutral response."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    text: str = ""
    parsed: BaseModel | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    finish_reason: str | None = None
    latency_ms: float = 0.0
    degraded_capabilities: list[CapabilityEvent] = Field(default_factory=list)
    capability_notes: list[str] = Field(default_factory=list)


class LLMProvider(Protocol):
    """Structural interface for LLM adapters."""

    name: str
    model: str

    def call(self, request: ProviderRequest) -> ProviderResponse: ...

    def capabilities(self) -> ProviderCapabilities: ...


def provider_capabilities(provider: object) -> ProviderCapabilities:
    """Return declared capabilities or a safe legacy fallback.

    Reviewer P1 #13: a provider without ``capabilities()`` previously got
    a permissive fallback (every flag True, ship_grade_judge=True). Under
    guarded profile that's fail-open — a user-written adapter that
    forgot to declare its capabilities would be treated as cloud-grade.

    The default fallback is now conservative: ship_grade_judge is False,
    schema/judge support flags are False, ``experimental=True``. Users
    who deliberately want the old permissive shape (e.g. a quick local
    test where they know the provider is fine) can set
    ``OMEGAPROMPT_TRUST_LEGACY_PROVIDERS=1`` to opt back in. The env-var
    pattern matches how other audit tools (mini-omega-lock fail-open
    removal) gate trust decisions: explicit, intentional, auditable.
    """

    caps_fn = getattr(provider, "capabilities", None)
    if callable(caps_fn):
        caps = caps_fn()
        if isinstance(caps, ProviderCapabilities):
            return caps

    name = str(getattr(provider, "name", "legacy"))
    if os.environ.get("OMEGAPROMPT_TRUST_LEGACY_PROVIDERS") == "1":
        return ProviderCapabilities(
            provider=name,
            tier=CapabilityTier.CORE,
            supports_strict_schema=True,
            supports_json_object=True,
            supports_reasoning_profiles=True,
            supports_usage_accounting=True,
            supports_llm_judge=True,
            ship_grade_judge=True,
            notes=[
                "Legacy provider without explicit capability declaration.",
                "OMEGAPROMPT_TRUST_LEGACY_PROVIDERS=1 set — capabilities "
                "treated as cloud-grade. Audit assumes you verified this.",
            ],
        )
    return ProviderCapabilities(
        provider=name,
        tier=CapabilityTier.CORE,
        supports_strict_schema=False,
        supports_json_object=False,
        supports_reasoning_profiles=False,
        supports_usage_accounting=False,
        supports_llm_judge=False,
        ship_grade_judge=False,
        experimental=True,
        notes=[
            "Legacy provider without explicit capability declaration.",
            "Fail-closed default: treated as experimental until the "
            "adapter declares its capabilities. Set "
            "OMEGAPROMPT_TRUST_LEGACY_PROVIDERS=1 to opt back into "
            "the previous permissive fallback.",
        ],
    )


def empty_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def normalize_usage(raw: Any) -> dict[str, int]:
    """Coerce vendor usage into the canonical dict shape."""

    def _attr(name: str) -> int:
        value = getattr(raw, name, 0) if raw is not None else 0
        return int(value or 0)

    if isinstance(raw, dict):

        def _attr(name: str) -> int:  # noqa: F811
            return int(raw.get(name, 0) or 0)

    input_tokens = (
        _attr("input_tokens")
        or _attr("prompt_tokens")
        or _attr("prompt_token_count")
    )
    output_tokens = (
        _attr("output_tokens")
        or _attr("completion_tokens")
        or _attr("candidates_token_count")
    )
    total_tokens = _attr("total_token_count") or _attr("total_tokens")
    if total_tokens and input_tokens and not output_tokens:
        output_tokens = max(total_tokens - input_tokens, 0)
    elif total_tokens and output_tokens and not input_tokens:
        input_tokens = max(total_tokens - output_tokens, 0)
    cache_create = _attr("cache_creation_input_tokens")
    cache_read = _attr("cache_read_input_tokens")

    if not cache_read and raw is not None:
        details = getattr(raw, "prompt_tokens_details", None)
        if details is None and isinstance(raw, dict):
            details = raw.get("prompt_tokens_details")
        if details is not None:
            if isinstance(details, dict):
                cache_read = int(details.get("cached_tokens", 0) or 0)
            else:
                cache_read = int(getattr(details, "cached_tokens", 0) or 0)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_create,
        "cache_read_input_tokens": cache_read,
    }


_OUTPUT_BUDGET_MAX_TOKENS: dict[OutputBudgetBucket, int] = {
    OutputBudgetBucket.SMALL: 1024,
    OutputBudgetBucket.MEDIUM: 4096,
    OutputBudgetBucket.LARGE: 16000,
}

_REASONING_EFFORT_LABEL: dict[ReasoningProfile, str] = {
    ReasoningProfile.OFF: "low",
    ReasoningProfile.LIGHT: "low",
    ReasoningProfile.STANDARD: "medium",
    ReasoningProfile.DEEP: "high",
}


def max_tokens_for(budget: OutputBudgetBucket) -> int:
    return _OUTPUT_BUDGET_MAX_TOKENS[budget]


def reasoning_effort_label(profile: ReasoningProfile) -> str:
    return _REASONING_EFFORT_LABEL[profile]


def reasoning_enabled(profile: ReasoningProfile) -> bool:
    return profile != ReasoningProfile.OFF


def estimate_cost_units(usage: dict[str, int] | None) -> float:
    """Provider-neutral cost proxy.

    When adapters do not publish a pricing table, token volume remains a
    stable within-provider proxy for relative cost.
    """

    usage = usage or {}
    return float(int(usage.get("input_tokens", 0) or 0) + int(usage.get("output_tokens", 0) or 0))


def quality_per_cost(fitness: float, cost_units: float) -> float:
    denom = cost_units if cost_units > 0 else 1.0
    return fitness / denom


def quality_per_latency(fitness: float, latency_ms: float) -> float:
    denom = latency_ms if latency_ms > 0 else 1.0
    return fitness / denom


def parse_model_from_json_text(
    *,
    text: str,
    schema: type[T],
    capability: str,
    reason: str,
) -> tuple[T, CapabilityEvent]:
    """Parse an output model from JSON text after an adapter-level fallback."""

    try:
        parsed = schema.model_validate_json(text)
    except (ValidationError, ValueError, JSONDecodeError):
        parsed = schema.model_validate_json(_strip_markdown_fences(text))
    event = CapabilityEvent(
        capability=capability,
        requested="strict_schema",
        applied="json_object_parse",
        reason=reason,
        user_visible_note=(
            "Strict schema support was unavailable, so the adapter fell back to JSON output "
            "plus local validation. Validation strength is lower than native strict parsing."
        ),
    )
    return parsed, event


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[-1].strip().startswith("```"):
        return "\n".join(lines[1:-1])
    return stripped

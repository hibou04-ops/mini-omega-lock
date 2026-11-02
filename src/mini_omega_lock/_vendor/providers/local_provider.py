# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Local OpenAI-compatible adapters for Ollama / vLLM / llama.cpp style APIs."""

from __future__ import annotations

from typing import Any

from mini_omega_lock._vendor.domain.enums import ReasoningProfile, ResponseSchemaMode
from mini_omega_lock._vendor.domain.profiles import ExecutionProfile
from mini_omega_lock._vendor.providers.base import (
    CapabilityEvent,
    CapabilityTier,
    ProviderCapabilities,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    parse_model_from_json_text,
    reasoning_effort_label,
    reasoning_enabled,
)
from mini_omega_lock._vendor.providers.openai_provider import OpenAIProvider


_JSON_SUFFIX = (
    "\n\nReturn exactly one valid JSON object. No markdown fences. "
    "No commentary outside the JSON."
)


class LocalOpenAICompatibleProvider(OpenAIProvider):
    """Explicit local-backend adapter with honest capability notes."""

    def __init__(
        self,
        *,
        model: str,
        backend: str = "local",
        client: Any = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.backend = backend
        super().__init__(
            model=model,
            client=client,
            api_key=api_key,
            base_url=base_url,
        )
        self.name = backend

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            tier=CapabilityTier.LOCAL,
            supports_strict_schema=False,
            supports_json_object=True,
            supports_reasoning_profiles=False,
            supports_usage_accounting=True,
            supports_llm_judge=False,
            ship_grade_judge=False,
            supports_tools=False,
            experimental=True,
            notes=[
                "Target generation is first-class; judge semantics are exploration-grade.",
                "Reasoning_profile is translated into prompt instructions, not native compute control.",
                "STRICT_SCHEMA degrades to JSON output plus local validation only in expedition mode.",
            ],
        )

    def _messages(self, request: ProviderRequest) -> list[dict[str, Any]]:
        system_prompt = request.system_prompt
        if reasoning_enabled(request.reasoning_profile):
            system_prompt += (
                "\n\nReasoning profile: "
                + reasoning_effort_label(request.reasoning_profile)
                + ". Keep the answer within the requested budget."
            )
        if request.response_schema_mode == ResponseSchemaMode.JSON_OBJECT:
            system_prompt += _JSON_SUFFIX
        local_request = request.model_copy(update={"system_prompt": system_prompt})
        return super()._messages(local_request)

    def _maybe_reasoning(self, profile: ReasoningProfile) -> dict[str, Any]:
        return {}

    def _call_freeform(self, request: ProviderRequest) -> ProviderResponse:
        try:
            return super()._call_freeform(request)
        except ProviderError as exc:
            msg = str(exc).lower()
            if request.response_schema_mode == ResponseSchemaMode.JSON_OBJECT and "response_format" in msg:
                if request.execution_profile != ExecutionProfile.EXPEDITION:
                    raise
                degraded_request = request.model_copy(
                    update={"response_schema_mode": ResponseSchemaMode.FREEFORM}
                )
                response = super()._call_freeform(degraded_request)
                response.degraded_capabilities.append(
                    CapabilityEvent(
                        capability="structured_output",
                        requested="json_object",
                        applied="prompt_only_json",
                        reason="backend rejected response_format=json_object",
                        user_visible_note=(
                            "The local backend rejected native JSON mode, so the adapter fell back "
                            "to prompt-only JSON instructions."
                        ),
                    )
                )
                return response
            raise

    def _call_strict(self, request: ProviderRequest) -> ProviderResponse:
        if request.output_schema is None:
            raise ProviderError("response_schema_mode=STRICT_SCHEMA requires request.output_schema.")
        if request.execution_profile != ExecutionProfile.EXPEDITION:
            raise ProviderError(
                f"{self.name} does not provide ship-grade strict schema support. "
                "Use guarded profile with a stronger judge provider, or expedition to allow "
                "JSON fallback with explicit experimental risk."
            )
        json_request = request.model_copy(update={"response_schema_mode": ResponseSchemaMode.JSON_OBJECT})
        freeform = self._call_freeform(json_request)
        try:
            parsed, event = parse_model_from_json_text(
                text=freeform.text,
                schema=request.output_schema,
                capability="structured_output",
                reason=f"{self.name} has no native strict schema path",
            )
        except Exception as exc:
            raise ProviderError(
                f"{self.name} could not satisfy the schema even after JSON fallback."
            ) from exc
        return ProviderResponse(
            text=freeform.text,
            parsed=parsed,
            usage=freeform.usage,
            finish_reason=freeform.finish_reason,
            latency_ms=freeform.latency_ms,
            degraded_capabilities=[*freeform.degraded_capabilities, event],
            capability_notes=freeform.capability_notes,
        )

# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Anthropic adapter - translates meta-axes to native params.

Mappings used:

- ``ReasoningProfile.OFF`` -> no ``thinking`` block.
- ``ReasoningProfile.{LIGHT, STANDARD, DEEP}`` -> ``thinking={"type":"adaptive"}``
  + ``output_config.effort`` in ``{"low","medium","high"}``.
- ``OutputBudgetBucket`` -> native ``max_tokens`` int.
- ``ResponseSchemaMode.FREEFORM`` -> ``messages.create``.
- ``ResponseSchemaMode.JSON_OBJECT`` -> ``messages.create`` + a short
  system-prompt suffix instructing JSON output. Anthropic does not expose
  a vendor-native ``response_format={"type":"json_object"}``; the shape
  is enforced by STRICT_SCHEMA instead.
- ``ResponseSchemaMode.STRICT_SCHEMA`` -> ``messages.parse(output_format=...)``.

``cache_control: ephemeral`` is always applied on the system block so
repeat calls in a calibration run hit cache.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from mini_omega_lock._vendor.domain.enums import ReasoningProfile, ResponseSchemaMode
from mini_omega_lock._vendor.providers.base import (
    CapabilityTier,
    ProviderCapabilities,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    empty_usage,
    max_tokens_for,
    normalize_usage,
    reasoning_effort_label,
    reasoning_enabled,
)


_JSON_OBJECT_SUFFIX = (
    "\n\nReturn your response as a single valid JSON object. No prose, "
    "no markdown fences, no commentary."
)


class AnthropicProvider:
    """``LLMProvider`` for the Anthropic SDK."""

    name = "anthropic"

    def __init__(
        self,
        *,
        model: str,
        client: Any = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model

        if client is not None:
            self._client = client
            return

        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "The 'anthropic' package is required for provider='anthropic'. "
                "Install with `pip install anthropic`."
            ) from exc

        self._client = Anthropic(api_key=api_key) if api_key else Anthropic()

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=True,
            supports_json_object=True,
            supports_reasoning_profiles=True,
            supports_usage_accounting=True,
            supports_llm_judge=True,
            ship_grade_judge=True,
            supports_tools=False,
            notes=[
                "Native strict schema path via messages.parse.",
                "Adaptive thinking + effort tiers preserved behind reasoning_profile.",
            ],
        )

    def call(self, request: ProviderRequest) -> ProviderResponse:
        if request.response_schema_mode == ResponseSchemaMode.STRICT_SCHEMA:
            return self._call_strict(request)
        return self._call_freeform(request)

    # ---- private ----

    def _system_block(self, system_prompt: str, schema_mode: ResponseSchemaMode) -> list[dict]:
        text = system_prompt
        if schema_mode == ResponseSchemaMode.JSON_OBJECT:
            text = system_prompt + _JSON_OBJECT_SUFFIX
        return [
            {
                "type": "text",
                "text": text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _messages(self, request: ProviderRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for shot in request.few_shots:
            messages.append({"role": "user", "content": shot["input"]})
            messages.append({"role": "assistant", "content": shot["output"]})
        messages.append({"role": "user", "content": request.user_message})
        return messages

    def _reasoning_kwargs(self, profile: ReasoningProfile) -> dict[str, Any]:
        if not reasoning_enabled(profile):
            return {}
        return {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": reasoning_effort_label(profile)},
        }

    def _call_freeform(self, request: ProviderRequest) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens_for(request.output_budget_bucket),
            "system": self._system_block(request.system_prompt, request.response_schema_mode),
            "messages": self._messages(request),
            **self._reasoning_kwargs(request.reasoning_profile),
        }

        try:
            started = perf_counter()
            response = self._client.messages.create(**kwargs)
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Anthropic call failed: {exc}") from exc

        text_parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                chunk = getattr(block, "text", "")
                if chunk:
                    text_parts.append(chunk)
        text = "\n".join(text_parts).strip()
        usage = normalize_usage(getattr(response, "usage", None)) or empty_usage()
        return ProviderResponse(
            text=text,
            usage=usage,
            finish_reason=getattr(response, "stop_reason", None),
            latency_ms=(perf_counter() - started) * 1000.0,
        )

    def _call_strict(self, request: ProviderRequest) -> ProviderResponse:
        if request.output_schema is None:
            raise ProviderError(
                "response_schema_mode=STRICT_SCHEMA requires request.output_schema."
            )

        try:
            started = perf_counter()
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=max_tokens_for(request.output_budget_bucket),
                system=self._system_block(request.system_prompt, request.response_schema_mode),
                messages=self._messages(request),
                output_format=request.output_schema,
            )
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Anthropic structured call failed: {exc}") from exc

        if getattr(response, "stop_reason", None) == "refusal":
            raise ProviderError(
                "Anthropic refused to complete under the requested schema. "
                "Inspect the target response for safety-layer triggers."
            )

        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise ProviderError(
                "Anthropic returned no parsed_output. The response did not conform to the schema."
            )
        if not isinstance(parsed, request.output_schema):
            parsed = request.output_schema.model_validate(parsed)

        usage = normalize_usage(getattr(response, "usage", None)) or empty_usage()
        return ProviderResponse(
            parsed=parsed,
            usage=usage,
            finish_reason=getattr(response, "stop_reason", None),
            latency_ms=(perf_counter() - started) * 1000.0,
        )

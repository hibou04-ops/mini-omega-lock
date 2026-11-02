# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Google Gemini adapter for the provider-neutral call surface."""

from __future__ import annotations

import os
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from mini_omega_lock._vendor.domain.enums import ReasoningProfile, ResponseSchemaMode
from mini_omega_lock._vendor.domain.profiles import ExecutionProfile
from mini_omega_lock._vendor.providers.base import (
    CapabilityEvent,
    CapabilityTier,
    ProviderCapabilities,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    empty_usage,
    max_tokens_for,
    normalize_usage,
    parse_model_from_json_text,
)


_JSON_OBJECT_SUFFIX = (
    "\n\nReturn exactly one valid JSON object. No markdown fences. "
    "No commentary outside the JSON."
)


class GeminiProvider:
    """``LLMProvider`` for the official Google GenAI SDK."""

    name = "gemini"

    def __init__(
        self,
        *,
        model: str,
        client: Any = None,
        api_key: str | None = None,
        native_strict_schema: bool = True,
    ) -> None:
        self.model = model
        self.native_strict_schema = native_strict_schema

        if client is not None:
            self._client = client
            return

        resolved_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not resolved_key:
            raise ProviderError(
                "Gemini API key is required for provider='gemini'. Set GEMINI_API_KEY "
                "or GOOGLE_API_KEY, or pass api_key explicitly."
            )

        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "The 'google-genai' package is required for provider='gemini'. "
                "Install with `pip install google-genai`."
            ) from exc

        self._client = genai.Client(api_key=resolved_key)

    def capabilities(self) -> ProviderCapabilities:
        notes = [
            "Freeform and JSON object calls use the Google GenAI generate_content API.",
            "Usage is normalized from Gemini usage_metadata when present.",
            "Reasoning profiles are not mapped to a native Gemini control in this adapter.",
        ]
        if self.native_strict_schema:
            notes.extend(
                [
                    "STRICT_SCHEMA requests Gemini response_schema and still validates locally.",
                    "ship_grade_judge remains false until guarded-mode production probes validate Gemini judge reliability.",
                ]
            )
        else:
            notes.append(
                "Native strict schema disabled; expedition may fall back to JSON object plus local validation."
            )

        return ProviderCapabilities(
            provider=self.name,
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=self.native_strict_schema,
            supports_json_object=True,
            supports_reasoning_profiles=False,
            supports_usage_accounting=True,
            supports_llm_judge=True,
            ship_grade_judge=False,
            supports_tools=False,
            experimental=not self.native_strict_schema,
            placeholder=False,
            notes=notes,
        )

    def call(self, request: ProviderRequest) -> ProviderResponse:
        if request.response_schema_mode == ResponseSchemaMode.STRICT_SCHEMA:
            return self._call_strict(request)
        return self._call_freeform(request)

    def _call_freeform(self, request: ProviderRequest) -> ProviderResponse:
        degraded = self._reasoning_degradation(request.reasoning_profile)
        config = self._base_config(request)
        system_prompt = request.system_prompt
        if request.response_schema_mode == ResponseSchemaMode.JSON_OBJECT:
            config["response_mime_type"] = "application/json"
            system_prompt += _JSON_OBJECT_SUFFIX
        config["system_instruction"] = system_prompt

        try:
            started = perf_counter()
            response = self._client.models.generate_content(
                model=self.model,
                contents=self._contents(request),
                config=config,
            )
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Gemini call failed: {exc}") from exc

        text = _extract_text(response)
        parsed = None
        if (
            request.response_schema_mode == ResponseSchemaMode.JSON_OBJECT
            and request.output_schema is not None
        ):
            parsed = _validate_with_schema(
                response=response,
                text=text,
                schema=request.output_schema,
                provider_label="Gemini JSON object response",
            )

        return ProviderResponse(
            text=text,
            parsed=parsed,
            usage=_usage(response),
            finish_reason=_finish_reason(response),
            latency_ms=(perf_counter() - started) * 1000.0,
            degraded_capabilities=degraded,
        )

    def _call_strict(self, request: ProviderRequest) -> ProviderResponse:
        if request.output_schema is None:
            raise ProviderError(
                "response_schema_mode=STRICT_SCHEMA requires request.output_schema."
            )
        if not self.native_strict_schema:
            if request.execution_profile != ExecutionProfile.EXPEDITION:
                raise ProviderError(
                    "Gemini native strict schema is unavailable for this adapter instance. "
                    "Guarded mode does not allow silent downgrade to JSON-object parsing."
                )
            return self._fallback_strict_schema(request)

        degraded = self._reasoning_degradation(request.reasoning_profile)
        config = self._base_config(request)
        config.update(
            {
                "system_instruction": request.system_prompt,
                "response_mime_type": "application/json",
                "response_schema": request.output_schema,
            }
        )
        try:
            started = perf_counter()
            response = self._client.models.generate_content(
                model=self.model,
                contents=self._contents(request),
                config=config,
            )
        except Exception as exc:  # pragma: no cover
            raise ProviderError(f"Gemini structured call failed: {exc}") from exc

        text = _extract_text(response)
        parsed = _validate_with_schema(
            response=response,
            text=text,
            schema=request.output_schema,
            provider_label="Gemini strict schema response",
        )
        return ProviderResponse(
            text=text,
            parsed=parsed,
            usage=_usage(response),
            finish_reason=_finish_reason(response),
            latency_ms=(perf_counter() - started) * 1000.0,
            degraded_capabilities=degraded,
        )

    def _fallback_strict_schema(self, request: ProviderRequest) -> ProviderResponse:
        json_request = request.model_copy(
            update={
                "response_schema_mode": ResponseSchemaMode.JSON_OBJECT,
                "output_schema": None,
            }
        )
        freeform = self._call_freeform(json_request)
        try:
            parsed, event = parse_model_from_json_text(
                text=freeform.text,
                schema=request.output_schema,  # type: ignore[arg-type]
                capability="structured_output",
                reason="native Gemini strict schema unavailable",
            )
        except Exception as exc:
            raise ProviderError(
                "Gemini strict-schema fallback returned JSON that failed local validation."
            ) from exc
        event.affects_guarded_boundary = True
        return ProviderResponse(
            text=freeform.text,
            parsed=parsed,
            usage=freeform.usage,
            finish_reason=freeform.finish_reason,
            latency_ms=freeform.latency_ms,
            degraded_capabilities=[*freeform.degraded_capabilities, event],
            capability_notes=freeform.capability_notes,
        )

    def _base_config(self, request: ProviderRequest) -> dict[str, Any]:
        return {
            "max_output_tokens": max_tokens_for(request.output_budget_bucket),
        }

    def _contents(self, request: ProviderRequest) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for shot in request.few_shots:
            contents.append({"role": "user", "parts": [{"text": shot["input"]}]})
            contents.append({"role": "model", "parts": [{"text": shot["output"]}]})
        contents.append({"role": "user", "parts": [{"text": request.user_message}]})
        return contents

    def _reasoning_degradation(self, profile: ReasoningProfile) -> list[CapabilityEvent]:
        if profile in {ReasoningProfile.OFF, ReasoningProfile.STANDARD}:
            return []
        return [
            CapabilityEvent(
                capability="reasoning_profile",
                requested=profile.value,
                applied=ReasoningProfile.STANDARD.value,
                reason="Gemini adapter does not map reasoning_profile to a native control",
                user_visible_note=(
                    "Gemini was called without a native reasoning-profile control; "
                    "the request used the model default reasoning behavior."
                ),
            )
        ]


def _validate_with_schema(
    *,
    response: Any,
    text: str,
    schema: type[BaseModel],
    provider_label: str,
) -> BaseModel:
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        try:
            if isinstance(parsed, schema):
                return parsed
            return schema.model_validate(parsed)
        except ValidationError as exc:
            raise ProviderError(f"{provider_label} failed schema validation: {exc}") from exc

    try:
        return schema.model_validate_json(text)
    except ValueError as exc:
        message = str(exc)
        if "Invalid JSON" in message or "JSON invalid" in message:
            raise ProviderError(f"{provider_label} returned invalid JSON: {exc}") from exc
        raise ProviderError(f"{provider_label} failed schema validation: {exc}") from exc


def _extract_text(response: Any) -> str:
    safety_reason = _safety_block_reason(response)
    if safety_reason:
        raise ProviderError(f"Gemini refused or safety-blocked the request: {safety_reason}")

    try:
        text = getattr(response, "text", None)
    except Exception:
        text = None
    if isinstance(text, str) and text.strip():
        return text.strip()

    candidates = getattr(response, "candidates", None)
    if not candidates:
        raise ProviderError("Gemini SDK returned no candidates and no text.")

    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    if str(finish_reason).upper() in {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT"}:
        raise ProviderError(f"Gemini refused or safety-blocked the request: {finish_reason}")

    parts = getattr(getattr(candidate, "content", None), "parts", None) or []
    chunks: list[str] = []
    for part in parts:
        part_text = getattr(part, "text", None)
        if isinstance(part_text, str):
            chunks.append(part_text)
    text = "".join(chunks).strip()
    if not text:
        raise ProviderError("Gemini SDK returned no text in the first candidate.")
    return text


def _safety_block_reason(response: Any) -> str | None:
    prompt_feedback = getattr(response, "prompt_feedback", None)
    if prompt_feedback is None:
        return None
    block_reason = getattr(prompt_feedback, "block_reason", None)
    if block_reason:
        return str(block_reason)
    return None


def _finish_reason(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    reason = getattr(candidates[0], "finish_reason", None)
    return None if reason is None else str(reason)


def _usage(response: Any) -> dict[str, int]:
    raw = getattr(response, "usage_metadata", None)
    if raw is None:
        raw = getattr(response, "usage", None)
    try:
        return normalize_usage(raw)
    except Exception:
        return empty_usage()

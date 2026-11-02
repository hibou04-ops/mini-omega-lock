# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""OpenAI adapter (also handles OpenAI-compatible endpoints via ``base_url``).

Mappings:

- ``ReasoningProfile.OFF`` -> no reasoning parameter.
- ``ReasoningProfile.{LIGHT, STANDARD, DEEP}`` -> the provider's
  ``reasoning_effort`` when the model supports it. Unknown-model paths
  drop the parameter silently rather than 400; users of exotic endpoints
  should pick FREEFORM if their model rejects reasoning knobs.
- ``OutputBudgetBucket`` -> ``max_tokens`` int.
- ``ResponseSchemaMode.FREEFORM`` -> ``chat.completions.create``.
- ``ResponseSchemaMode.JSON_OBJECT`` -> adds
  ``response_format={"type":"json_object"}``.
- ``ResponseSchemaMode.STRICT_SCHEMA`` -> ``beta.chat.completions.parse(response_format=...)``.
"""

from __future__ import annotations

from time import perf_counter
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
    empty_usage,
    max_tokens_for,
    normalize_usage,
    parse_model_from_json_text,
    reasoning_effort_label,
    reasoning_enabled,
)


class OpenAIProvider:
    """``LLMProvider`` for the OpenAI SDK and compatible endpoints."""

    name = "openai"

    def __init__(
        self,
        *,
        model: str,
        client: Any = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url

        if client is not None:
            self._client = client
            return

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "The 'openai' package is required for provider='openai'. "
                "Install with `pip install openai`."
            ) from exc

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs) if kwargs else OpenAI()

    def capabilities(self) -> ProviderCapabilities:
        # Reviewer P1 #14: when a non-OpenAI base_url is configured the
        # adapter is wired to an OpenAI-compatible endpoint (OpenRouter,
        # local server, vLLM, etc.). These endpoints frequently lack
        # strict schema enforcement or honest reasoning profile support;
        # treating them as cloud-grade is fail-open. Downgrade until a
        # preflight probe confirms the endpoint actually meets the bar.
        if self.base_url and "api.openai.com" not in self.base_url:
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
                    "OpenAI-compatible endpoint at a non-openai.com base_url. "
                    "Capabilities downgraded to LOCAL until a doctor / "
                    "preflight probe confirms the endpoint supports strict "
                    "schema, reasoning profiles, and ship-grade judging.",
                ],
            )
        notes = [
            "Native json_object and beta parse paths when the model supports them.",
            "Unknown OpenAI-compatible endpoints may degrade schema or reasoning controls.",
        ]
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
            notes=notes,
        )

    def call(self, request: ProviderRequest) -> ProviderResponse:
        if request.response_schema_mode == ResponseSchemaMode.STRICT_SCHEMA:
            return self._call_strict(request)
        return self._call_freeform(request)

    # ---- private ----

    def _messages(self, request: ProviderRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": request.system_prompt},
        ]
        for shot in request.few_shots:
            messages.append({"role": "user", "content": shot["input"]})
            messages.append({"role": "assistant", "content": shot["output"]})
        messages.append({"role": "user", "content": request.user_message})
        return messages

    def _maybe_reasoning(self, profile: ReasoningProfile) -> dict[str, Any]:
        if not reasoning_enabled(profile):
            return {}
        return {"reasoning_effort": reasoning_effort_label(profile)}

    def _call_freeform(self, request: ProviderRequest) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens_for(request.output_budget_bucket),
            "messages": self._messages(request),
        }
        if request.response_schema_mode == ResponseSchemaMode.JSON_OBJECT:
            kwargs["response_format"] = {"type": "json_object"}

        # reasoning_effort is model-gated; some endpoints reject it. Try,
        # and drop on known-unsupported error shape at the adapter boundary.
        reasoning_kwargs = self._maybe_reasoning(request.reasoning_profile)
        if reasoning_kwargs:
            kwargs.update(reasoning_kwargs)
        degraded: list[CapabilityEvent] = []

        try:
            started = perf_counter()
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # pragma: no cover
            msg = str(exc).lower()
            if "reasoning_effort" in msg and reasoning_kwargs:
                # Retry without reasoning knobs.
                for k in list(reasoning_kwargs):
                    kwargs.pop(k, None)
                degraded.append(
                    CapabilityEvent(
                        capability="reasoning_profile",
                        requested=request.reasoning_profile.value,
                        applied=ReasoningProfile.OFF.value,
                        reason="endpoint rejected reasoning_effort",
                        user_visible_note=(
                            "The endpoint rejected native reasoning controls, so the adapter "
                            "fell back to a plain completion call."
                        ),
                    )
                )
                try:
                    started = perf_counter()
                    response = self._client.chat.completions.create(**kwargs)
                except Exception as exc2:
                    raise ProviderError(f"OpenAI call failed: {exc2}") from exc2
            else:
                raise ProviderError(f"OpenAI call failed: {exc}") from exc

        if not getattr(response, "choices", None):
            raise ProviderError("OpenAI call returned no choices.")
        choice = response.choices[0]
        message = choice.message
        text = getattr(message, "content", "") or ""
        usage = normalize_usage(getattr(response, "usage", None)) or empty_usage()
        return ProviderResponse(
            text=text.strip(),
            usage=usage,
            finish_reason=getattr(choice, "finish_reason", None),
            latency_ms=(perf_counter() - started) * 1000.0,
            degraded_capabilities=degraded,
        )

    def _call_strict(self, request: ProviderRequest) -> ProviderResponse:
        if request.output_schema is None:
            raise ProviderError(
                "response_schema_mode=STRICT_SCHEMA requires request.output_schema."
            )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens_for(request.output_budget_bucket),
            "messages": self._messages(request),
            "response_format": request.output_schema,
        }
        reasoning_kwargs = self._maybe_reasoning(request.reasoning_profile)
        if reasoning_kwargs:
            kwargs.update(reasoning_kwargs)
        degraded: list[CapabilityEvent] = []

        try:
            started = perf_counter()
            response = self._client.beta.chat.completions.parse(**kwargs)
        except Exception as exc:  # pragma: no cover
            msg = str(exc).lower()
            if "reasoning_effort" in msg and reasoning_kwargs:
                for k in list(reasoning_kwargs):
                    kwargs.pop(k, None)
                degraded.append(
                    CapabilityEvent(
                        capability="reasoning_profile",
                        requested=request.reasoning_profile.value,
                        applied=ReasoningProfile.OFF.value,
                        reason="endpoint rejected reasoning_effort during strict parse",
                        user_visible_note=(
                            "The endpoint rejected native reasoning controls during strict parsing."
                        ),
                    )
                )
                try:
                    started = perf_counter()
                    response = self._client.beta.chat.completions.parse(**kwargs)
                except Exception as exc2:
                    raise ProviderError(f"OpenAI structured call failed: {exc2}") from exc2
            elif self._schema_fallback_allowed(request.execution_profile, msg):
                return self._fallback_strict_schema(request, msg)
            else:
                raise ProviderError(f"OpenAI structured call failed: {exc}") from exc

        if not getattr(response, "choices", None):
            raise ProviderError("OpenAI structured call returned no choices.")
        choice = response.choices[0]
        if getattr(choice, "finish_reason", None) == "content_filter":
            raise ProviderError(
                "OpenAI refused under content_filter. "
                "Target response hit the moderation layer."
            )
        message = getattr(choice, "message", None)
        if message is None:
            raise ProviderError("OpenAI structured call returned no message.")

        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise ProviderError(
                "OpenAI returned no parsed object. The response did not conform to response_format."
            )
        if not isinstance(parsed, request.output_schema):
            parsed = request.output_schema.model_validate(parsed)

        usage = normalize_usage(getattr(response, "usage", None)) or empty_usage()
        return ProviderResponse(
            parsed=parsed,
            usage=usage,
            finish_reason=getattr(choice, "finish_reason", None),
            latency_ms=(perf_counter() - started) * 1000.0,
            degraded_capabilities=degraded,
        )

    def _fallback_strict_schema(
        self,
        request: ProviderRequest,
        reason: str,
    ) -> ProviderResponse:
        json_request = request.model_copy(
            update={"response_schema_mode": ResponseSchemaMode.JSON_OBJECT}
        )
        freeform = self._call_freeform(json_request)
        if request.output_schema is None:
            raise ProviderError("Strict-schema fallback requires output_schema.")
        try:
            parsed, event = parse_model_from_json_text(
                text=freeform.text,
                schema=request.output_schema,
                capability="structured_output",
                reason=reason,
            )
        except Exception as exc:
            raise ProviderError(
                "OpenAI endpoint could not provide native strict schema support and the "
                "JSON fallback did not validate."
            ) from exc
        return ProviderResponse(
            text=freeform.text,
            parsed=parsed,
            usage=freeform.usage,
            finish_reason=freeform.finish_reason,
            latency_ms=freeform.latency_ms,
            degraded_capabilities=[*freeform.degraded_capabilities, event],
        )

    def _schema_fallback_allowed(self, profile: ExecutionProfile, error_message: str) -> bool:
        if profile != ExecutionProfile.EXPEDITION:
            return False
        msg = error_message.lower()
        return "response_format" in msg or "json_schema" in msg or "parse" in msg

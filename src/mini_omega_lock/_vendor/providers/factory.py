# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Provider factory for mini_omega_lock._vendor.

Same pattern as antemortem-cli: one call site to construct the right
adapter from a string name. Extending: implement ``LLMProvider`` in a
new module, register in ``_REGISTRY``.
"""

from __future__ import annotations

from typing import Any

from mini_omega_lock._vendor.providers.base import LLMProvider, ProviderError


DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-opus-4-7",
    "openai": "gpt-4o",
    "gemini": "gemini-2.5-flash",
    "local": "local-model",
    "ollama": "llama3.1:8b",
    "vllm": "meta-llama/Llama-3.1-8B-Instruct",
    "llama_cpp": "llama.cpp-local",
}


def supported_providers() -> list[str]:
    return list(_REGISTRY.keys())


def make_provider(
    name: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    client: Any = None,
    **extra: Any,
) -> LLMProvider:
    """Construct a configured ``LLMProvider`` by name."""
    key = name.lower().strip()
    if key not in _REGISTRY:
        raise ProviderError(
            f"Unknown provider {name!r}. Supported: {', '.join(supported_providers())}"
        )

    builder = _REGISTRY[key]
    resolved_model = model or DEFAULT_MODELS[key]
    return builder(
        model=resolved_model,
        api_key=api_key,
        base_url=base_url,
        client=client,
        **extra,
    )


def _build_anthropic(**kwargs: Any) -> LLMProvider:
    from mini_omega_lock._vendor.providers.anthropic_provider import AnthropicProvider

    kwargs.pop("base_url", None)
    return AnthropicProvider(**kwargs)


def _build_openai(**kwargs: Any) -> LLMProvider:
    from mini_omega_lock._vendor.providers.openai_provider import OpenAIProvider

    return OpenAIProvider(**kwargs)


def _build_gemini(**kwargs: Any) -> LLMProvider:
    from mini_omega_lock._vendor.providers.gemini_provider import GeminiProvider

    kwargs.pop("base_url", None)
    return GeminiProvider(**kwargs)


def _build_local(**kwargs: Any) -> LLMProvider:
    from mini_omega_lock._vendor.providers.local_provider import LocalOpenAICompatibleProvider

    backend = kwargs.pop("backend", "local")
    return LocalOpenAICompatibleProvider(backend=backend, **kwargs)


def _build_ollama(**kwargs: Any) -> LLMProvider:
    # Distinct, discoverable named adapter (keyless local OpenAI-compatible
    # endpoint). Behaviour is backward-compatible with the prior
    # backend="ollama" local alias; the difference is a clearly-named class
    # with Ollama defaults (local base URL, sentinel key).
    from mini_omega_lock._vendor.providers.ollama_provider import OllamaProvider

    kwargs.pop("backend", None)
    return OllamaProvider(**kwargs)


_REGISTRY = {
    "anthropic": _build_anthropic,
    "openai": _build_openai,
    "gemini": _build_gemini,
    "local": _build_local,
    "ollama": _build_ollama,
    "vllm": lambda **kwargs: _build_local(backend="vllm", **kwargs),
    "llama_cpp": lambda **kwargs: _build_local(backend="llama_cpp", **kwargs),
}

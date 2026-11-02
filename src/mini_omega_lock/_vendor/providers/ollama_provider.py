# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Ollama adapter — a distinct, discoverable local/keyless provider.

Ollama exposes an OpenAI-compatible ``/v1`` endpoint, so the transport is
the same as :class:`~mini_omega_lock._vendor.providers.local_provider.LocalOpenAICompatibleProvider`.
This subclass exists for *discoverability*: ``make_provider("ollama")``
returns a clearly-named adapter with Ollama-appropriate defaults (local
base URL, no API key required) rather than a generic ``local`` adapter
configured with a ``backend`` string.

Like the generic local adapter, capabilities are reported as
LOCAL / experimental: target generation is first-class, but judging is
exploration-grade and there is no native strict-schema path.
"""

from __future__ import annotations

from typing import Any

from mini_omega_lock._vendor.providers.local_provider import LocalOpenAICompatibleProvider

# Ollama's OpenAI-compatible endpoint. The SDK requires *some* api_key
# string even though Ollama ignores it, so a sentinel is used by default.
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
_OLLAMA_SENTINEL_KEY = "ollama"


class OllamaProvider(LocalOpenAICompatibleProvider):
    """LLMProvider for a local Ollama server (keyless, OpenAI-compatible)."""

    def __init__(
        self,
        *,
        model: str,
        client: Any = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(
            model=model,
            backend="ollama",
            client=client,
            # Ollama ignores the key but the OpenAI SDK requires a non-empty
            # one to construct without an OPENAI_API_KEY env var.
            api_key=api_key or _OLLAMA_SENTINEL_KEY,
            base_url=base_url or _DEFAULT_OLLAMA_BASE_URL,
        )
        # backend already sets name="ollama"; keep it explicit for clarity.
        self.name = "ollama"

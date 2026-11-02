# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Provider-neutral meta-axes.

Each enum captures a semantic dimension of prompt configuration that every
major LLM provider exposes in some form, without tying the public contract
to any single vendor's parameter names. Adapters translate these to
vendor-native params in their ``call()`` implementation.

Design rule: enum members are ordered from cheapest/lightest to
strongest/most-expensive. A searcher can treat the ordinal as a proxy for
cost/capability axis and probe from both ends to cut the space quickly.
"""

from __future__ import annotations

from enum import Enum


class ReasoningProfile(str, Enum):
    """How much reasoning effort the target should spend.

    Mapped per provider:

    - Anthropic: OFF -> thinking disabled; LIGHT/STANDARD/DEEP -> adaptive
      thinking + effort tiers (low/medium/high).
    - OpenAI: OFF -> no reasoning directive; LIGHT/STANDARD/DEEP -> the
      provider's reasoning_effort parameter where supported, else a
      system-prompt-level hint.
    - Local / Ollama: encoded as a system-prompt suffix (no native knob).
    """

    OFF = "off"
    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


class OutputBudgetBucket(str, Enum):
    """Discretised max-output-tokens bucket.

    The calibration searcher picks a bucket; adapters resolve it to a
    concrete ``max_tokens`` int appropriate for their vendor.
    """

    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ResponseSchemaMode(str, Enum):
    """How strictly the target's response is shape-constrained.

    FREEFORM is the default - the target produces plain text. JSON_OBJECT
    requests a JSON object at the message level (``response_format``-style).
    STRICT_SCHEMA uses the provider's strongest schema-enforcement path
    (Pydantic-parse on OpenAI, messages.parse on Anthropic).
    """

    FREEFORM = "freeform"
    JSON_OBJECT = "json_object"
    STRICT_SCHEMA = "strict_schema"


class ToolPolicyVariant(str, Enum):
    """Whether/how the target is expected to use tools.

    Not every target uses tools; this axis is a no-op for plain
    chat-completion targets and is unlocked only when the target expose
    tool schemas at construction time.
    """

    NO_TOOLS = "no_tools"
    TOOL_OPTIONAL = "tool_optional"
    TOOL_REQUIRED = "tool_required"


# Ordinal mappings so searchers can iterate from weakest to strongest.
REASONING_ORDINALS: dict[ReasoningProfile, int] = {
    ReasoningProfile.OFF: 0,
    ReasoningProfile.LIGHT: 1,
    ReasoningProfile.STANDARD: 2,
    ReasoningProfile.DEEP: 3,
}

OUTPUT_BUDGET_ORDINALS: dict[OutputBudgetBucket, int] = {
    OutputBudgetBucket.SMALL: 0,
    OutputBudgetBucket.MEDIUM: 1,
    OutputBudgetBucket.LARGE: 2,
}


def reasoning_from_ordinal(idx: int) -> ReasoningProfile:
    members = list(ReasoningProfile)
    idx = max(0, min(len(members) - 1, idx))
    return members[idx]


def output_budget_from_ordinal(idx: int) -> OutputBudgetBucket:
    members = list(OutputBudgetBucket)
    idx = max(0, min(len(members) - 1, idx))
    return members[idx]

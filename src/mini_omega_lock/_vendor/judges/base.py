# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Judge Protocol - provider-neutral scoring contract.

Every judge consumes (rubric, dataset_item, target_response) and returns
a ``JudgeOutcome`` carrying the result, usage, optional degradation
events, and latency. No judge implementation may import a provider SDK
directly — they go through :class:`LLMProvider` if they need an LLM call.

Reviewer P0: judge provider degradation events were dropped on the floor
between LLMJudge and PromptTarget. ``JudgeOutcome`` carries them
forward. It iterates as ``(result, usage)`` so existing tuple-unpacking
callers keep working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator, Protocol

from mini_omega_lock._vendor.domain.dataset import DatasetItem
from mini_omega_lock._vendor.domain.judge import JudgeResult, JudgeRubric

if TYPE_CHECKING:
    from mini_omega_lock._vendor.providers.base import CapabilityEvent


class JudgeError(RuntimeError):
    """Raised when a judge cannot produce a valid result."""


@dataclass
class JudgeOutcome:
    """Structured outcome of one ``Judge.score()`` call.

    Iterable as ``(result, usage)`` so all existing tuple-unpacking
    callers continue to work without code changes. New callers that
    need degradation events or latency read them via attribute access:

        outcome = judge.score(...)
        outcome.result            # JudgeResult
        outcome.usage             # dict[str, int]
        outcome.degraded_capabilities  # list[CapabilityEvent]
        outcome.latency_ms        # float
    """

    result: JudgeResult
    usage: dict[str, int]
    degraded_capabilities: list = field(default_factory=list)  # list[CapabilityEvent]
    latency_ms: float = 0.0

    def __iter__(self) -> Iterator:
        # Backward-compat tuple shape: (result, usage). Iterating
        # further raises StopIteration so ``a, b, c = ...`` fails
        # loudly instead of unpacking degradation by accident.
        yield self.result
        yield self.usage


class Judge(Protocol):
    """Structural interface for judges."""

    name: str

    def score(
        self,
        *,
        rubric: JudgeRubric,
        item: DatasetItem,
        target_response: str,
    ) -> JudgeOutcome:
        """Return a ``JudgeOutcome``.

        ``usage`` uses the same canonical key set as
        :func:`mini_omega_lock._vendor.providers.base.empty_usage`; rule-based judges
        return a zero-valued dict and an empty ``degraded_capabilities``
        list. Iteration yields ``(result, usage)`` for backward-compat.
        """
        ...

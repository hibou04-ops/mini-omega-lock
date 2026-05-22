"""Deterministic, no-network demo of `mini_omega_lock.empirical_preflight`.

Goals:
    - Show the full warning surface without any provider/API key.
    - Produce byte-for-byte stable stdout so a tampered output trips
      ``tests/test_demo_replay.py``.
    - Round-trip through `omegaprompt.preflight.PreflightReport` and
      `derive_adaptation_plan` so the demo doubles as a smoke check of
      the omegaprompt contract.

Timing fields (`mean_call_latency_ms`, `projected_wall_time_seconds`)
are masked to ``<masked: timing>`` before printing — see
``docs/examples.md`` "Why timing fields are masked".

Run with::

    python examples/demo_replay.py

Then compare against ``examples/_demo_output.txt``; the bundled test
``tests/test_demo_replay.py`` does that diff automatically.
"""

from __future__ import annotations

import sys
from typing import Any

from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.judge import Dimension, HardGate, JudgeResult, JudgeRubric
from omegaprompt.judges.llm_judge import LLMJudge
from omegaprompt.preflight import PreflightReport, derive_adaptation_plan
from omegaprompt.providers.base import (
    CapabilityTier,
    ProviderCapabilities,
    ProviderResponse,
)

from mini_omega_lock import empirical_preflight


# ---------------------------------------------------------------------------
# Fake provider — identical to the pattern used in the test suite, kept
# *outside* the test tree so the demo is self-contained.
# ---------------------------------------------------------------------------


class _DeterministicProvider:
    """Scripted provider: always returns the same judge result.

    Same score every call => `measure_judge_consistency` reports 1.0;
    same gate value every call => `measure_gate_flip_rate` reports 0.0.
    """

    name = "demo-fake"
    model = "scripted"

    def __init__(self, score: int = 4, gate_value: bool = True) -> None:
        self._score = score
        self._gate_value = gate_value
        self._cursor = 0

    def call(self, request: Any) -> ProviderResponse:  # noqa: ARG002
        self._cursor += 1
        return ProviderResponse(
            parsed=JudgeResult(
                scores={"accuracy": self._score},
                gate_results={"no_refusal": self._gate_value},
                notes="demo-deterministic",
            ),
            usage={
                "input_tokens": 50,
                "output_tokens": 10,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
            latency_ms=10.0,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="demo-fake",
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=True,
            supports_llm_judge=True,
            ship_grade_judge=True,
        )


# ---------------------------------------------------------------------------
# Stable rendering helpers
# ---------------------------------------------------------------------------


_TIMING_MASK = "<masked: timing>"


def _format_measurement(label: str, model: Any, masked_fields: tuple[str, ...] = ()) -> str:
    """Render a Pydantic measurement as ``key=value`` lines.

    Fields listed in ``masked_fields`` are replaced with the literal
    ``<masked: timing>`` so non-deterministic timing values don't leak
    into the demo's stdout. Other fields are rendered verbatim.
    """
    out = [f"{label}:"]
    data = model.model_dump(mode="json")
    for key in sorted(data):
        value = _TIMING_MASK if key in masked_fields else data[key]
        out.append(f"  {key} = {value!r}")
    return "\n".join(out)


def _format_plan(plan: Any) -> str:
    out = ["AdaptationPlan:"]
    data = plan.model_dump(mode="json")
    for key in sorted(data):
        out.append(f"  {key} = {data[key]!r}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Demo body
# ---------------------------------------------------------------------------


def run() -> str:
    """Execute the demo and return the rendered string (instead of printing)."""
    rubric = JudgeRubric(
        dimensions=[
            Dimension(
                name="accuracy",
                description="is the answer correct",
                weight=1.0,
                scale=(1, 5),
            )
        ],
        hard_gates=[HardGate(name="no_refusal", description="must try", evaluator="judge")],
    )
    probe_item = DatasetItem(id="probe-1", input="What is 2+2?", reference="4")
    probe_response = "The answer is 4."

    judge = LLMJudge(provider=_DeterministicProvider())

    judge_q, endpoint, perf, warnings = empirical_preflight(
        judge=judge,
        rubric=rubric,
        probe_item=probe_item,
        probe_response=probe_response,
        consistency_repeats=3,
        dataset_size_hint=10,
        candidates_expected=20,
        # No strict_schema probe   => schema_reliability warning expected.
        # No monotonic_examples     => scale_monotonic warning expected.
        # No token_counter          => chars_per_token heuristic warning expected.
        # No fitness_samples        => noise_floor warning expected.
    )

    lines: list[str] = []
    lines.append("=== mini-omega-lock deterministic demo replay ===")
    lines.append("Inputs:")
    lines.append("  judge          = LLMJudge(provider=_DeterministicProvider())")
    lines.append("  consistency_repeats = 3")
    lines.append("  schema probe        = not supplied (fail-closed expected)")
    lines.append("  monotonic_examples  = not supplied (fail-closed expected)")
    lines.append("  token_counter       = not supplied (heuristic path)")
    lines.append("  fitness_samples     = not supplied (fail-closed expected)")
    lines.append("")

    lines.append(_format_measurement("JudgeQualityMeasurement", judge_q))
    lines.append("")
    lines.append(_format_measurement("EndpointMeasurement", endpoint))
    lines.append("")
    lines.append(
        _format_measurement(
            "PerformanceMeasurement",
            perf,
            masked_fields=("mean_call_latency_ms", "projected_wall_time_seconds"),
        )
    )
    lines.append("")

    lines.append(f"Warnings ({len(warnings)}):")
    for w in warnings:
        # Trim repeated whitespace so the demo output is independent of how
        # the source file wraps the warning strings.
        lines.append(f"  - {' '.join(w.split())}")
    lines.append("")

    # Round-trip through omegaprompt's adaptation layer to prove
    # PreflightReport contract still holds.
    report = PreflightReport(judge_quality=judge_q, endpoint=endpoint, performance=perf)
    plan = derive_adaptation_plan(report=report)

    lines.append(_format_plan(plan))
    lines.append("")
    lines.append("=== end demo ===")
    return "\n".join(lines) + "\n"


def main() -> int:
    # The probes' warning strings contain em-dashes; Windows default
    # cp949 stdout cannot encode them. Force UTF-8 so the demo prints
    # consistently across platforms.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())

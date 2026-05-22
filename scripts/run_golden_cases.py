"""Replay every JSON case under ``benchmarks/golden_cases/`` against
``mini_omega_lock.empirical_preflight``.

Cases are intentionally small and use scripted fake providers (the same
pattern as ``examples/demo_replay.py``). Comparison rules:

* Deterministic fields are compared exactly.
* ``mean_call_latency_ms`` and ``projected_wall_time_seconds`` are
  *never* compared — they would flake.
* ``context_budget_margin`` is compared by sign (``positive`` / ``negative``
  / ``zero``) rather than value, so updating the chars-per-token heuristic
  does not cascade into rewriting every case.
* ``warnings_contains_all_of`` is a list of substrings that must all
  appear (somewhere) in the returned warnings list.

Run modes::

    python scripts/run_golden_cases.py --check          # diff and exit
    python scripts/run_golden_cases.py --list           # show case names
    python scripts/run_golden_cases.py --update-manifest # rehash fixtures

The ``--update-manifest`` flag delegates to
``scripts/verify_fixture_integrity.py`` so the SHA-256 manifest stays in
one place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.enums import (
    OutputBudgetBucket,
    ReasoningProfile,
    ResponseSchemaMode,
)
from omegaprompt.domain.judge import (
    Dimension,
    HardGate,
    JudgeResult,
    JudgeRubric,
)
from omegaprompt.judges.llm_judge import LLMJudge
from omegaprompt.providers.base import (
    CapabilityTier,
    ProviderCapabilities,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)

from mini_omega_lock import empirical_preflight

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = REPO_ROOT / "benchmarks" / "golden_cases"


# ---------------------------------------------------------------------------
# Fake providers
# ---------------------------------------------------------------------------


class _ScriptedJudgeProvider:
    """Returns judge results from a scripted score list, cycling as needed."""

    name = "golden-fake"
    model = "scripted"

    def __init__(self, scores: list[int], gate_value: bool = True) -> None:
        self._scores = list(scores) if scores else [4]
        self._gate_value = gate_value
        self._cursor = 0

    def call(self, request: ProviderRequest) -> ProviderResponse:  # noqa: ARG002
        score = self._scores[self._cursor % len(self._scores)]
        self._cursor += 1
        return ProviderResponse(
            parsed=JudgeResult(
                scores={"accuracy": score},
                gate_results={"no_refusal": self._gate_value},
            ),
            usage={
                "input_tokens": 50,
                "output_tokens": 10,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
            latency_ms=5.0,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="golden-fake",
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=True,
            supports_llm_judge=True,
            ship_grade_judge=True,
        )


class _SchemaProbeProvider:
    """Configurable strict-schema probe provider.

    ``outcomes`` is a list of one of:
        - "ok"   : return a parsed JudgeResult
        - "fail" : raise ProviderError
        - "none" : return a response with parsed=None
    The list cycles to cover all configured probes.
    """

    name = "schema-fake"
    model = "scripted"

    def __init__(self, outcomes: list[str]) -> None:
        self._outcomes = list(outcomes) if outcomes else ["ok"]
        self._cursor = 0

    def call(self, request: ProviderRequest) -> ProviderResponse:  # noqa: ARG002
        outcome = self._outcomes[self._cursor % len(self._outcomes)]
        self._cursor += 1
        if outcome == "fail":
            raise ProviderError("scripted schema probe failure")
        if outcome == "none":
            return ProviderResponse(parsed=None, usage={})
        return ProviderResponse(
            parsed=JudgeResult(
                scores={"accuracy": 4},
                gate_results={"no_refusal": True},
            ),
            usage={"input_tokens": 5, "output_tokens": 2},
            latency_ms=5.0,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="schema-fake",
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=True,
            supports_llm_judge=False,
            ship_grade_judge=False,
        )


# ---------------------------------------------------------------------------
# Case execution
# ---------------------------------------------------------------------------


def _build_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Translate a case's ``inputs`` dict into the kwargs ``empirical_preflight`` accepts."""
    judge = LLMJudge(
        provider=_ScriptedJudgeProvider(
            scores=inputs.get("scripted_scores", [4, 4, 4]),
            gate_value=inputs.get("gate_value", True),
        )
    )
    rubric = JudgeRubric(
        dimensions=[
            Dimension(
                name="accuracy",
                description=inputs.get("rubric_description", "is the answer correct"),
                weight=1.0,
                scale=(1, 5),
            )
        ],
        hard_gates=[HardGate(name="no_refusal", description="g", evaluator="judge")],
    )
    probe_item = DatasetItem(
        id="probe",
        input=inputs.get("probe_input", "2+2"),
        reference=inputs.get("probe_reference", "4"),
    )
    kwargs: dict[str, Any] = {
        "judge": judge,
        "rubric": rubric,
        "probe_item": probe_item,
        "probe_response": inputs.get("probe_response", "4"),
        "consistency_repeats": inputs.get("consistency_repeats", 3),
        "dataset_size_hint": inputs.get("dataset_size_hint", 10),
        "candidates_expected": inputs.get("candidates_expected", 20),
    }

    if inputs.get("include_schema_probe"):
        outcomes = inputs.get("schema_probe_outcomes", ["ok", "ok", "ok"])
        kwargs["strict_schema_provider"] = _SchemaProbeProvider(outcomes=outcomes)
        kwargs["strict_schema_output"] = JudgeResult
        kwargs["strict_schema_probes"] = tuple(
            ProviderRequest(
                system_prompt="schema probe",
                user_message=msg,
                response_schema_mode=ResponseSchemaMode.FREEFORM,
                output_budget_bucket=OutputBudgetBucket.SMALL,
                reasoning_profile=ReasoningProfile.OFF,
            )
            for msg in inputs.get(
                "schema_probe_messages", ["probe-1", "probe-2", "probe-3"]
            )
        )

    if inputs.get("fitness_samples"):
        kwargs["fitness_samples"] = inputs["fitness_samples"]

    if inputs.get("monotonic_examples"):
        # The fake judge here always returns the same score, so monotonic
        # ordering trivially holds; cases that want failure must supply a
        # scripted score sequence + paired examples that flip the order.
        kwargs["monotonic_examples"] = [
            (DatasetItem(id=f"m{i}", input=f"q{i}", reference="r"), f"a{i}")
            for i in range(2)
        ]

    if inputs.get("token_counter") == "approx":
        kwargs["token_counter"] = lambda s: max(1, len(s) // 4)
        kwargs["system_prompts"] = inputs.get("system_prompts", ["You are a judge."])

    return kwargs


def _sign(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def _check_expected(case: dict[str, Any], judge_q, endpoint, perf, warnings) -> list[str]:
    """Return list of human-readable mismatch descriptions; empty list = pass."""
    issues: list[str] = []
    expected = case.get("expected", {})

    def _cmp(section: str, model_dump: dict, expected_section: dict) -> None:
        for key, exp in expected_section.items():
            actual = model_dump.get(key)
            if actual != exp:
                issues.append(
                    f"{section}.{key}: expected {exp!r}, got {actual!r}"
                )

    jq_dump = judge_q.model_dump(mode="json")
    ep_dump = endpoint.model_dump(mode="json")
    pf_dump = perf.model_dump(mode="json")

    # Special: context_budget_margin compared by sign.
    ep_dump_for_check = dict(ep_dump)
    if "context_budget_margin_sign" in expected.get("endpoint", {}):
        ep_dump_for_check["context_budget_margin_sign"] = _sign(
            ep_dump.get("context_budget_margin", 0.0)
        )
        # Don't compare the raw float on top of the sign.
        ep_dump_for_check.pop("context_budget_margin", None)

    _cmp("judge_quality", jq_dump, expected.get("judge_quality", {}))
    _cmp("endpoint", ep_dump_for_check, expected.get("endpoint", {}))
    # Performance: only ``noise_floor`` is deterministic enough to compare.
    pf_for_check = {"noise_floor": pf_dump.get("noise_floor")}
    _cmp("performance", pf_for_check, expected.get("performance", {}))

    # Warnings substring assertions.
    must_contain = expected.get("warnings_contains_all_of", [])
    flattened = " || ".join(warnings)
    for needle in must_contain:
        if needle not in flattened:
            issues.append(f"warnings missing substring {needle!r}")

    must_not_contain = expected.get("warnings_contains_none_of", [])
    for needle in must_not_contain:
        if needle in flattened:
            issues.append(f"warnings unexpectedly contain substring {needle!r}")

    return issues


def _run_case(case_path: Path) -> tuple[str, list[str]]:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    name = case.get("name", case_path.stem)
    kwargs = _build_inputs(case.get("inputs", {}))
    judge_q, endpoint, perf, warnings = empirical_preflight(**kwargs)
    return name, _check_expected(case, judge_q, endpoint, perf, warnings)


def _list_cases() -> list[Path]:
    if not CASES_DIR.exists():
        return []
    return sorted(p for p in CASES_DIR.glob("*.json") if p.name != "manifest.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Run all cases; exit 1 on any mismatch.")
    mode.add_argument("--list", action="store_true", help="List case files and exit.")
    mode.add_argument(
        "--update-manifest",
        action="store_true",
        help="Rebuild benchmarks/golden_cases/manifest.json by delegating to verify_fixture_integrity.py.",
    )
    args = parser.parse_args(argv)

    cases = _list_cases()
    if args.list:
        for c in cases:
            print(c.relative_to(REPO_ROOT))
        return 0

    if args.update_manifest:
        verify_script = REPO_ROOT / "scripts" / "verify_fixture_integrity.py"
        return subprocess.run(
            [sys.executable, str(verify_script), "--write"],
            cwd=REPO_ROOT,
        ).returncode

    # Default + --check: run every case.
    if not cases:
        print("no golden cases found; see docs/examples.md", file=sys.stderr)
        return 1

    fail_count = 0
    for case_path in cases:
        try:
            name, issues = _run_case(case_path)
        except Exception as exc:
            print(f"[case ERROR] {case_path.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            fail_count += 1
            continue
        if issues:
            fail_count += 1
            print(f"[case FAIL] {name} ({case_path.name})")
            for line in issues:
                print(f"  - {line}", file=sys.stderr)
        else:
            print(f"[case ok ] {name}")

    print(f"\n{len(cases) - fail_count}/{len(cases)} cases passed.")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())

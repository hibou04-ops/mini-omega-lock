"""Tests for the ``preflight`` CLI (H1).

Covers:
  * JSON / JSONL / text output shape (in-process, scripted provider).
  * Process EXIT CODES by actually running the CLI as a subprocess:
      - unmeasured-field fail-closed -> non-zero (exit 2)
      - bad usage -> exit 1
      - tokenizer-unavailable fail-loud -> exit 1
      - success (0) and measured-but-bad warning (0) via the pure
        exit-code classifier (a fully-measured run is not reachable
        through the documented flag surface, which never supplies a
        schema probe / monotonic fixture).
  * Library warning strings are byte-unchanged (CLI must not rewrite
    any probes.py warning text).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_DEMO = REPO_ROOT / "examples" / "cli_demo_replay.py"
CLI_GOLDEN = REPO_ROOT / "examples" / "_cli_demo_output.json"

_RUBRIC = json.dumps(
    {
        "dimensions": [
            {"name": "accuracy", "description": "is the answer correct", "weight": 1.0, "scale": [1, 5]}
        ],
        "hard_gates": [{"name": "no_refusal", "description": "must try", "evaluator": "judge"}],
    }
)
_ITEM = json.dumps({"id": "probe-1", "input": "What is 2+2?", "reference": "4"})


# ---------------------------------------------------------------------------
# In-process output-shape tests (scripted provider, no network).
# ---------------------------------------------------------------------------


def _run_cli_inprocess(argv, monkeypatch):
    """Patch make_provider to a scripted offline provider, run cli.main,
    capture stdout, return (stdout, exit_code)."""
    import io
    from contextlib import redirect_stdout

    from omegaprompt.domain.judge import JudgeResult
    from omegaprompt.providers.base import (
        CapabilityTier,
        ProviderCapabilities,
        ProviderResponse,
    )
    from mini_omega_lock import cli

    class _Scripted:
        name = "anthropic"
        model = "scripted"

        def call(self, request):  # noqa: ANN001
            return ProviderResponse(
                parsed=JudgeResult(scores={"accuracy": 4}, gate_results={"no_refusal": True}),
                usage={"input_tokens": 50, "output_tokens": 10},
                latency_ms=5.0,
            )

        def capabilities(self):
            return ProviderCapabilities(
                provider="anthropic",
                tier=CapabilityTier.CLOUD,
                supports_strict_schema=True,
                supports_llm_judge=True,
                ship_grade_judge=True,
            )

    monkeypatch.setattr("omegaprompt.providers.make_provider", lambda *a, **kw: _Scripted())
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(argv)
    return buf.getvalue(), code


_BASE_ARGS = [
    "--provider", "anthropic",
    "--rubric", _RUBRIC,
    "--probe-item", _ITEM,
    "--probe-response", "4",
    "--consistency-repeats", "1",
]


def test_cli_json_output_shape(monkeypatch):
    out, code = _run_cli_inprocess(_BASE_ARGS + ["--json"], monkeypatch)
    obj = json.loads(out)
    assert set(obj) == {
        "judge_quality",
        "endpoint",
        "performance",
        "warnings",
        "adaptation_plan",
    }
    assert isinstance(obj["warnings"], list)
    # Unmeasured fields present -> fail-closed exit 2.
    assert code == 2


def test_cli_jsonl_output_shape(monkeypatch):
    out, code = _run_cli_inprocess(_BASE_ARGS + ["--jsonl"], monkeypatch)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 2
    report = json.loads(lines[0])
    plan = json.loads(lines[1])
    assert set(report) == {"judge_quality", "endpoint", "performance", "warnings"}
    assert set(plan) == {"adaptation_plan"}
    assert code == 2


def test_cli_text_output_shape(monkeypatch):
    out, code = _run_cli_inprocess(_BASE_ARGS + ["--text"], monkeypatch)
    assert "=== mini-omega-lock preflight ===" in out
    assert "warnings (" in out
    assert "adaptation_plan:" in out
    assert code == 2


def test_cli_default_format_is_text(monkeypatch):
    out, _ = _run_cli_inprocess(_BASE_ARGS, monkeypatch)
    assert out.startswith("=== mini-omega-lock preflight ===")


# ---------------------------------------------------------------------------
# Exit-code classifier (pure) — covers success=0 / measured-warning=0.
# ---------------------------------------------------------------------------


def test_exit_code_zero_when_no_warnings():
    from mini_omega_lock.cli import EXIT_OK, _exit_code_for_warnings

    assert _exit_code_for_warnings([]) == EXIT_OK


def test_exit_code_zero_for_measured_but_bad_warning():
    """A measured-but-bad value (low consistency, gate flip) is NOT an
    unmeasured-field signal — it was measured, so exit stays 0."""
    from mini_omega_lock.cli import EXIT_OK, _exit_code_for_warnings

    measured_bad = [
        "judge gate 'no_refusal' flipped on 0.40 of consecutive call pairs",
    ]
    assert _exit_code_for_warnings(measured_bad) == EXIT_OK


def test_exit_code_nonzero_for_unmeasured_field():
    from mini_omega_lock.cli import EXIT_UNMEASURED, _exit_code_for_warnings

    unmeasured = [
        "endpoint.schema_reliability not measured — ...",
    ]
    assert _exit_code_for_warnings(unmeasured) == EXIT_UNMEASURED
    assert EXIT_UNMEASURED != 0


# ---------------------------------------------------------------------------
# Real subprocess exit codes (actually invoking the CLI).
# ---------------------------------------------------------------------------


def test_cli_subprocess_unmeasured_exit_2():
    """Run the deterministic CLI demo as a real process; the demo path has
    unmeasured fields -> the CLI must exit non-zero (2)."""
    # cli_demo_replay.run() returns the exit code; invoke it so the real
    # cli.main return value drives a real process exit code.
    code = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'examples'); "
            "import cli_demo_replay as c; _, code = c.run(); sys.exit(code)",
        ],
        cwd=REPO_ROOT,
    ).returncode
    assert code == 2


def test_cli_subprocess_bad_args_exit_1():
    """Missing required args -> argparse exits 2 (its own usage code); a
    malformed rubric -> our input-error path exits 1."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mini_omega_lock.cli",
            "--provider", "anthropic",
            "--rubric", "{not valid json",
            "--probe-item", _ITEM,
            "--probe-response", "4",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "input error" in proc.stderr


def test_cli_subprocess_tokenizer_unavailable_fail_loud():
    """An unknown --token-counter spec must RAISE (exit 1), never silently
    fall back to the chars/token heuristic."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mini_omega_lock.cli",
            "--provider", "anthropic",
            "--rubric", _RUBRIC,
            "--probe-item", _ITEM,
            "--probe-response", "4",
            "--token-counter", "definitely-not-a-real-tokenizer",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "token-counter" in proc.stderr


# ---------------------------------------------------------------------------
# Golden + library-warning-string invariant.
# ---------------------------------------------------------------------------


def test_cli_demo_matches_golden():
    proc = subprocess.run(
        [sys.executable, str(CLI_DEMO), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"CLI golden drift.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


def test_cli_does_not_rewrite_library_warning_strings():
    """The warnings the CLI surfaces must be byte-identical to the ones the
    library produces (no CLI-side rewriting). Compare the CLI's golden
    warnings against empirical_preflight's own output on the same inputs."""
    from omegaprompt.domain.dataset import DatasetItem
    from omegaprompt.domain.judge import Dimension, HardGate, JudgeRubric, JudgeResult
    from omegaprompt.judges.llm_judge import LLMJudge
    from omegaprompt.providers.base import (
        CapabilityTier,
        ProviderCapabilities,
        ProviderResponse,
    )
    from mini_omega_lock import empirical_preflight

    class _Scripted:
        name = "anthropic"
        model = "scripted"

        def call(self, request):  # noqa: ANN001
            return ProviderResponse(
                parsed=JudgeResult(scores={"accuracy": 4}, gate_results={"no_refusal": True}),
                usage={"input_tokens": 50, "output_tokens": 10},
                latency_ms=10.0,
            )

        def capabilities(self):
            return ProviderCapabilities(
                provider="anthropic",
                tier=CapabilityTier.CLOUD,
                supports_strict_schema=True,
                supports_llm_judge=True,
                ship_grade_judge=True,
            )

    rubric = JudgeRubric(
        dimensions=[Dimension(name="accuracy", description="is the answer correct", weight=1.0, scale=(1, 5))],
        hard_gates=[HardGate(name="no_refusal", description="must try", evaluator="judge")],
    )
    _, _, _, lib_warnings = empirical_preflight(
        judge=LLMJudge(provider=_Scripted()),
        rubric=rubric,
        probe_item=DatasetItem(id="probe-1", input="What is 2+2?", reference="4"),
        probe_response="The answer is 4.",
        consistency_repeats=3,
    )
    golden = json.loads(CLI_GOLDEN.read_text(encoding="utf-8"))
    assert golden["warnings"] == lib_warnings

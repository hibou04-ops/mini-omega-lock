"""Byte-for-byte diff between ``examples/demo_replay.py`` stdout and
``examples/_demo_output.txt``.

Why this test exists:
    The warning surface of `empirical_preflight` is load-bearing. If a
    refactor accidentally changes a warning string, swaps a fail-closed
    default, or alters the AdaptationPlan shape, the diff here flags it
    *before* it ships to users. The demo is the smallest reproduction
    that exercises the full surface offline.

Cross-platform note:
    Both sides are normalised to ``\\n`` line endings so a Windows
    runner with CRLF doesn't false-positive against a LF-only baseline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "examples" / "demo_replay.py"
EXPECTED = REPO_ROOT / "examples" / "_demo_output.txt"


def _normalise(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def test_demo_file_exists():
    assert DEMO.exists(), "examples/demo_replay.py is missing"
    assert EXPECTED.exists(), "examples/_demo_output.txt is missing"


def test_demo_replay_matches_expected_output():
    result = subprocess.run(
        [sys.executable, str(DEMO)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        f"demo exited non-zero.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    actual = _normalise(result.stdout)
    expected = _normalise(EXPECTED.read_text(encoding="utf-8"))
    if actual != expected:
        # Surface the diff in pytest's output so triage doesn't require
        # rerunning the demo by hand.
        import difflib

        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile="_demo_output.txt (expected)",
                tofile="demo_replay.py stdout (actual)",
                n=3,
            )
        )
        raise AssertionError(
            "demo output drifted from the committed baseline. "
            "If this drift is intentional, regenerate with "
            "`python examples/demo_replay.py > examples/_demo_output.txt` "
            "and commit. Otherwise treat as a real regression in the "
            "warning surface.\n\n" + diff
        )


def test_demo_output_has_no_unmasked_timing():
    """Guard against accidentally leaking real perf_counter() values
    into the committed baseline (which would make this whole test
    flaky next time someone regenerates on a faster machine)."""
    expected = EXPECTED.read_text(encoding="utf-8")
    # mean_call_latency_ms and projected_wall_time_seconds must always
    # be masked in the demo. If either appears as a number, the masking
    # was bypassed.
    for line in expected.splitlines():
        for forbidden_prefix in ("mean_call_latency_ms = ", "projected_wall_time_seconds = "):
            if line.strip().startswith(forbidden_prefix):
                value = line.strip()[len(forbidden_prefix):]
                assert value == "'<masked: timing>'", (
                    f"timing field is not masked in baseline: {line.strip()!r}"
                )


def test_demo_output_contains_full_warning_surface():
    """A reader scanning _demo_output.txt should see all four warning
    categories at a glance. This guards the demo against accidentally
    losing coverage of one of them."""
    expected = EXPECTED.read_text(encoding="utf-8")
    for needle in (
        "scale_monotonic not measured",
        "schema_reliability not measured",
        "chars_per_token",
        "noise_floor not measured",
    ):
        assert needle in expected, f"warning surface lost from demo: {needle!r}"

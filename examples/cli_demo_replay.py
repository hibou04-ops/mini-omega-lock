"""Deterministic, no-network demo of the ``preflight`` CLI (H1).

Runs ``mini_omega_lock.cli.main`` in-process against a scripted fake
provider (no API key, no network), captures the ``--json`` output, and
writes/compares it against ``examples/_cli_demo_output.json``.

This is the CLI analogue of ``examples/demo_replay.py``. It exists so the
CLI's output shape + exit code have a byte-stable golden the test suite
can diff. Timing fields (``mean_call_latency_ms``,
``projected_wall_time_seconds``) are masked to ``<masked: timing>``
before writing, exactly like the library demo, so the golden never
flakes on machine speed.

Run with::

    python examples/cli_demo_replay.py            # print masked JSON
    python examples/cli_demo_replay.py --write     # (re)write the golden
    python examples/cli_demo_replay.py --check      # diff vs golden; exit 1 on drift
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

from omegaprompt.domain.judge import JudgeResult
from omegaprompt.providers.base import (
    CapabilityTier,
    ProviderCapabilities,
    ProviderResponse,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN = REPO_ROOT / "examples" / "_cli_demo_output.json"

_TIMING_MASK = "<masked: timing>"


class _DeterministicProvider:
    """Same scripted judge as examples/demo_replay.py."""

    name = "anthropic"
    model = "scripted"

    def __init__(self) -> None:
        self._cursor = 0

    def call(self, request):  # noqa: ANN001
        self._cursor += 1
        return ProviderResponse(
            parsed=JudgeResult(
                scores={"accuracy": 4},
                gate_results={"no_refusal": True},
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
            provider="anthropic",
            tier=CapabilityTier.CLOUD,
            supports_strict_schema=True,
            supports_llm_judge=True,
            ship_grade_judge=True,
        )


_RUBRIC = json.dumps(
    {
        "dimensions": [
            {"name": "accuracy", "description": "is the answer correct", "weight": 1.0, "scale": [1, 5]}
        ],
        "hard_gates": [{"name": "no_refusal", "description": "must try", "evaluator": "judge"}],
    }
)
_ITEM = json.dumps({"id": "probe-1", "input": "What is 2+2?", "reference": "4"})


def run(argv: list[str] | None = None) -> tuple[dict, int]:
    """Invoke cli.main with a patched provider; return (masked_result, exit_code)."""
    import omegaprompt.providers as _providers
    from mini_omega_lock import cli

    original = _providers.make_provider
    _providers.make_provider = lambda *a, **kw: _DeterministicProvider()  # type: ignore
    try:
        args = argv if argv is not None else [
            "--provider", "anthropic",
            "--rubric", _RUBRIC,
            "--probe-item", _ITEM,
            "--probe-response", "The answer is 4.",
            "--consistency-repeats", "3",
            "--json",
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(args)
        result = json.loads(buf.getvalue())
    finally:
        _providers.make_provider = original  # type: ignore

    # Mask non-deterministic timing fields so the golden stays stable.
    perf = result.get("performance", {})
    for k in ("mean_call_latency_ms", "projected_wall_time_seconds"):
        if k in perf:
            perf[k] = _TIMING_MASK
    return result, code


def _serialize(result: dict) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    result, code = run()
    rendered = _serialize(result)

    if mode == "--write":
        GOLDEN.write_text(rendered, encoding="utf-8")
        print(f"wrote {GOLDEN.relative_to(REPO_ROOT)} (cli exit code {code})")
        return 0
    if mode == "--check":
        if not GOLDEN.exists():
            print(f"missing golden: {GOLDEN.relative_to(REPO_ROOT)} — run --write", file=sys.stderr)
            return 1
        if GOLDEN.read_text(encoding="utf-8").replace("\r\n", "\n") != rendered:
            print("CLI demo output drifted from the committed golden.", file=sys.stderr)
            return 1
        print("CLI demo output matches golden.")
        return 0

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())

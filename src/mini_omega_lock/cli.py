# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""``preflight`` command-line entry point for mini-omega-lock.

Wraps :func:`mini_omega_lock.empirical_preflight` + omegaprompt's
:func:`derive_adaptation_plan` so the preflight gate is reachable from a
shell / CI without writing Python.

Exit-code contract (mirrors the library's fail-closed semantics)::

    0   all requested measurements ran (no unmeasured-field warnings)
    2   one or more fields fell back to a fail-closed default because
        they were NOT measured (e.g. ``schema_reliability not measured``,
        ``scale_monotonic not measured``). A measured-but-bad value
        (low consistency, gate-flip) is still exit 0 — it was measured.
    1   usage / runtime error (bad args, provider failure, etc.)

INVARIANT: this module reads the warnings list emitted by ``probes.py``
verbatim and NEVER rewrites a library warning string. The byte-locked
``examples/_demo_output.txt`` baseline is the library's contract; the
CLI must leave it untouched.

Output modes::

    --text    human-readable blocks (default)
    --json    one pretty JSON object
    --jsonl   one compact JSON object per line (report, then plan)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

# Substrings in a warning that mean "this field was NOT measured" and so
# must drive a non-zero exit code (fail-closed for CI). Kept as a tuple of
# stable fragments of the library warning text — we match, never rewrite.
_UNMEASURED_FIELD_SIGNALS: tuple[str, ...] = (
    "schema_reliability not measured",
    "scale_monotonic not measured",
    "noise_floor not measured",
    "context_budget_margin uses the chars_per_token",
    "mean_call_latency_ms not measured",
    "degradation not probed",
)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_UNMEASURED = 2


# ---------------------------------------------------------------------------
# Input resolution
# ---------------------------------------------------------------------------


def _load_json_arg(value: str, *, what: str) -> Any:
    """Resolve a ``path-or-inline-JSON`` argument.

    If ``value`` names an existing file, parse that file; otherwise treat
    ``value`` as inline JSON text. Either way the result is the parsed
    object. Raises ``ValueError`` (turned into exit 1 by ``main``) on a
    parse failure so the user gets a precise diagnostic.
    """
    candidate = Path(value)
    try:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
        return json.loads(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"could not parse {what} as a JSON file path or inline JSON: {exc}"
        ) from exc


def _resolve_rubric(value: str):
    from omegaprompt.domain.judge import JudgeRubric

    data = _load_json_arg(value, what="--rubric")
    if not isinstance(data, dict):
        raise ValueError("--rubric must resolve to a JSON object (rubric dict)")
    return JudgeRubric.model_validate(data)


def _resolve_item(value: str):
    from omegaprompt.domain.dataset import DatasetItem

    data = _load_json_arg(value, what="--probe-item")
    if not isinstance(data, dict):
        raise ValueError("--probe-item must resolve to a JSON object (DatasetItem dict)")
    return DatasetItem.model_validate(data)


def _build_judge(provider: str, model: str | None, base_url: str | None):
    from omegaprompt.judges import LLMJudge
    from omegaprompt.providers import make_provider

    provider_obj = make_provider(provider, model=model, base_url=base_url)
    return LLMJudge(provider=provider_obj)


def resolve_token_counter(spec: str | None) -> Callable[[str], int] | None:
    """Resolve a ``--token-counter`` spec into a ``str -> int`` callable.

    FAIL LOUD: if the requested tokenizer backend is unavailable, RAISE.
    Never silently fall back to the chars/token heuristic — a user who
    asks for an exact token count and silently gets an approximation is
    exactly the false-safe this package exists to prevent. Pass no
    ``--token-counter`` (``None``) to deliberately use the heuristic
    path; that path emits its own ``chars_per_token`` warning.

    Supported specs:
        ``tiktoken``            -> tiktoken with the ``cl100k_base`` encoding
        ``tiktoken:<encoding>`` -> tiktoken with the named encoding
    """
    if spec is None:
        return None
    spec = spec.strip()
    if spec.startswith("tiktoken"):
        try:
            import tiktoken  # type: ignore
        except ImportError as exc:  # fail loud, do NOT degrade silently
            raise RuntimeError(
                "--token-counter=tiktoken requested but the 'tiktoken' package "
                "is not installed. Install it (`pip install tiktoken`) or omit "
                "--token-counter to use the chars_per_token heuristic "
                "(which emits an explicit warning). Refusing to silently fall "
                "back to the heuristic."
            ) from exc
        _, _, enc_name = spec.partition(":")
        enc_name = enc_name or "cl100k_base"
        try:
            enc = tiktoken.get_encoding(enc_name)
        except Exception as exc:  # unknown encoding -> loud, not silent
            raise RuntimeError(
                f"--token-counter=tiktoken encoding {enc_name!r} is unavailable: "
                f"{exc}. Refusing to silently fall back to the heuristic."
            ) from exc
        return lambda text: len(enc.encode(text))
    raise RuntimeError(
        f"unknown --token-counter spec {spec!r}. Supported: 'tiktoken' or "
        f"'tiktoken:<encoding>'. Omit the flag for the heuristic path."
    )


# ---------------------------------------------------------------------------
# Core run
# ---------------------------------------------------------------------------


def _run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the preflight + adaptation plan, returning a serializable dict."""
    from omegaprompt.preflight import PreflightReport, derive_adaptation_plan

    from mini_omega_lock import empirical_preflight

    rubric = _resolve_rubric(args.rubric)
    probe_item = _resolve_item(args.probe_item)
    judge = _build_judge(args.provider, args.model, args.base_url)
    token_counter = resolve_token_counter(args.token_counter)

    fitness_samples: Sequence[float] | None = None
    if args.fitness_samples:
        fitness_samples = [float(x) for x in args.fitness_samples.split(",") if x.strip()]

    judge_q, endpoint, perf, warnings = empirical_preflight(
        judge=judge,
        rubric=rubric,
        probe_item=probe_item,
        probe_response=args.probe_response,
        consistency_repeats=args.consistency_repeats,
        context_window_tokens=args.context_window,
        token_counter=token_counter,
        fitness_samples=fitness_samples,
    )

    report = PreflightReport(judge_quality=judge_q, endpoint=endpoint, performance=perf)
    plan = derive_adaptation_plan(report=report)

    return {
        "judge_quality": judge_q.model_dump(mode="json"),
        "endpoint": endpoint.model_dump(mode="json"),
        "performance": perf.model_dump(mode="json"),
        "warnings": list(warnings),
        "adaptation_plan": plan.model_dump(mode="json"),
    }


def _exit_code_for_warnings(warnings: Sequence[str]) -> int:
    """Non-zero when any warning names an UNMEASURED field (fail-closed)."""
    for w in warnings:
        for signal in _UNMEASURED_FIELD_SIGNALS:
            if signal in w:
                return EXIT_UNMEASURED
    return EXIT_OK


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_text(result: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("=== mini-omega-lock preflight ===")
    for section in ("judge_quality", "endpoint", "performance"):
        out.append(f"{section}:")
        for key in sorted(result[section]):
            out.append(f"  {key} = {result[section][key]!r}")
    warnings = result["warnings"]
    out.append(f"warnings ({len(warnings)}):")
    for w in warnings:
        out.append(f"  - {' '.join(w.split())}")
    out.append("adaptation_plan:")
    for key in sorted(result["adaptation_plan"]):
        out.append(f"  {key} = {result['adaptation_plan'][key]!r}")
    out.append("=== end preflight ===")
    return "\n".join(out) + "\n"


def _render_json(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _render_jsonl(result: dict[str, Any]) -> str:
    # Two lines: the measurement report, then the adaptation plan, so a
    # streaming consumer can read them independently.
    report = {k: result[k] for k in ("judge_quality", "endpoint", "performance", "warnings")}
    plan = {"adaptation_plan": result["adaptation_plan"]}
    return (
        json.dumps(report, ensure_ascii=False, sort_keys=True)
        + "\n"
        + json.dumps(plan, ensure_ascii=False, sort_keys=True)
        + "\n"
    )


# ---------------------------------------------------------------------------
# argparse + main
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="preflight",
        description=(
            "Run mini-omega-lock empirical preflight + omegaprompt adaptation "
            "plan from the shell. Exits 2 when any field fell back to a "
            "fail-closed default (was not measured)."
        ),
    )
    parser.add_argument("--provider", required=True, help="Provider name (e.g. anthropic, openai).")
    parser.add_argument("--model", default=None, help="Model id override.")
    parser.add_argument("--base-url", dest="base_url", default=None, help="Provider base URL override.")
    parser.add_argument(
        "--rubric",
        required=True,
        help="JudgeRubric: path to a JSON file or inline JSON object.",
    )
    parser.add_argument(
        "--probe-item",
        dest="probe_item",
        required=True,
        help="DatasetItem: path to a JSON file or inline JSON object.",
    )
    parser.add_argument(
        "--probe-response",
        dest="probe_response",
        required=True,
        help="Canonical correct response string for the probe item.",
    )
    parser.add_argument(
        "--consistency-repeats",
        dest="consistency_repeats",
        type=int,
        default=3,
        help="How many times to re-judge the probe (default 3).",
    )
    parser.add_argument(
        "--context-window",
        dest="context_window",
        type=int,
        default=0,
        help="Model context window in tokens (0 -> library default 32000).",
    )
    parser.add_argument(
        "--token-counter",
        dest="token_counter",
        default=None,
        help=(
            "Tokenizer spec for an exact context margin: 'tiktoken' or "
            "'tiktoken:<encoding>'. Omit for the chars_per_token heuristic. "
            "An unavailable tokenizer RAISES (no silent heuristic fallback)."
        ),
    )
    parser.add_argument(
        "--fitness-samples",
        dest="fitness_samples",
        default=None,
        help="Comma-separated fitness floats (>=2) for the noise-floor measurement.",
    )
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--text", action="store_const", dest="format", const="text", help="Human-readable output (default).")
    fmt.add_argument("--json", action="store_const", dest="format", const="json", help="Pretty JSON output.")
    fmt.add_argument("--jsonl", action="store_const", dest="format", const="jsonl", help="JSON-lines output.")
    parser.set_defaults(format="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        # Warning strings contain em-dashes; force UTF-8 so Windows cp949
        # stdout doesn't crash on them.
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = _run_preflight(args)
    except ValueError as exc:
        print(f"preflight: input error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except RuntimeError as exc:
        # resolve_token_counter fail-loud lands here.
        print(f"preflight: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:  # provider / runtime failure
        print(f"preflight: runtime error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    renderers = {"text": _render_text, "json": _render_json, "jsonl": _render_jsonl}
    sys.stdout.write(renderers[args.format](result))

    return _exit_code_for_warnings(result["warnings"])


if __name__ == "__main__":
    sys.exit(main())

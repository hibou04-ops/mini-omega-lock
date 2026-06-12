# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Headline summary + scorecard for a mini-omega-lock preflight run.

The package's single most load-bearing number is the **judge noise
floor**: how much the *same* judge disagrees with itself when it scores
the *same* (response, rubric) pair repeatedly. An A/B optimisation delta
smaller than this number is indistinguishable from the judge flipping a
coin — "an optimization delta smaller than your judge's own noise is not
real".

This module turns the four-tuple ``empirical_preflight`` returns into:

* :func:`judge_noise_floor` — the single headline float (0.0 = the judge
  is perfectly self-consistent; 1.0 = its score swing matched its mean).
* :func:`build_summary` — a flat, JSON-serialisable dict of CI-consumable
  metrics, carrying a ``schema_version`` string so a downstream consumer
  can detect format changes.
* :func:`render_scorecard` — a single-file Markdown or HTML scorecard,
  stdlib only, byte-stable (no timestamps, no machine-specific values).

All helpers are pure: they read the measurement records, never issue a
provider call, and never mutate their inputs.
"""

from __future__ import annotations

import html
import json
from typing import Any, Sequence

# Bump on any breaking change to the summary dict shape. Additive fields
# (new keys) do NOT require a bump; a removed/renamed/retyped key does.
SUMMARY_SCHEMA_VERSION = "mini-omega-lock/summary/v1"

# Warning substrings that mean "this field was NOT measured" (fail-closed
# default in play). Mirrors cli._UNMEASURED_FIELD_SIGNALS but kept here so
# the summary layer has no import dependency on the CLI. We MATCH these,
# never rewrite the library warning text.
_UNMEASURED_SIGNALS: dict[str, str] = {
    "schema_reliability not measured": "schema_reliability",
    "scale_monotonic not measured": "scale_monotonic",
    "noise_floor not measured": "fitness_noise_floor",
    "context_budget_margin uses the chars_per_token": "context_budget_margin",
    "mean_call_latency_ms not measured": "mean_call_latency_ms",
    "degradation not probed": "silent_degradation_detected",
}


def _dump(model: Any) -> dict[str, Any]:
    """Accept a Pydantic measurement OR a plain dict; return a dict."""
    if isinstance(model, dict):
        return dict(model)
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    raise TypeError(
        f"expected a measurement record or dict, got {type(model).__name__}"
    )


def judge_noise_floor(judge_quality: Any) -> float:
    """The headline judge-noise-floor number for a preflight run.

    Defined as ``1 - consistency`` where ``consistency`` is the
    ``JudgeQualityMeasurement.consistency`` field (``1 - CV`` of the
    judge's repeated weighted scores, clamped to ``[0, 1]``). So:

    * ``0.0`` — the judge returned the identical weighted score on every
      repeat (no measurable self-disagreement).
    * ``1.0`` — the judge's score standard deviation matched its mean
      (maximal measured noise).

    Interpretation: an A/B fitness delta smaller than this is below the
    judge's own noise floor and should not be trusted as a real
    improvement. Raise ``consistency_repeats`` and/or ``rescore_count``,
    or pick a steadier judge, before chasing sub-floor gains.

    Args:
        judge_quality: A ``JudgeQualityMeasurement`` (or its ``model_dump``
            dict) from ``empirical_preflight`` /
            ``measure_judge_consistency``.

    Returns:
        Float in ``[0.0, 1.0]``.
    """
    data = _dump(judge_quality)
    consistency = float(data.get("consistency", 0.0))
    # Clamp defensively; consistency is already clamped upstream but a
    # hand-built dict could be out of range.
    consistency = max(0.0, min(1.0, consistency))
    return round(1.0 - consistency, 12)


def _unmeasured_fields(warnings: Sequence[str]) -> list[str]:
    found: list[str] = []
    for w in warnings:
        for signal, field in _UNMEASURED_SIGNALS.items():
            if signal in w and field not in found:
                found.append(field)
    return sorted(found)


def build_summary(
    judge_quality: Any,
    endpoint: Any,
    performance: Any,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a flat, CI-consumable summary dict from a preflight run.

    Lead-with-the-headline shape: ``judge_noise_floor`` first, then the
    other measured surfaces, then the bookkeeping fields. Timing fields
    (``mean_call_latency_ms``, ``projected_wall_time_seconds``) are
    intentionally excluded so the summary is byte-stable across machines
    — use the full ``--json`` dump if you need them.

    Args:
        judge_quality: ``JudgeQualityMeasurement`` or dict.
        endpoint: ``EndpointMeasurement`` or dict.
        performance: ``PerformanceMeasurement`` or dict.
        warnings: The warnings list from ``empirical_preflight``.

    Returns:
        A dict with a stable ``schema_version`` and the headline metrics.
    """
    jq = _dump(judge_quality)
    ep = _dump(endpoint)
    pf = _dump(performance)
    unmeasured = _unmeasured_fields(warnings)

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        # --- headline ---
        "judge_noise_floor": judge_noise_floor(jq),
        # --- judge quality ---
        "judge_consistency": round(float(jq.get("consistency", 0.0)), 12),
        "anchoring_usage": round(float(jq.get("anchoring_usage", 0.0)), 12),
        "scale_monotonic": bool(jq.get("scale_monotonic", False)),
        "consistency_samples": int(jq.get("samples", 0)),
        # --- endpoint ---
        "schema_reliability": round(float(ep.get("schema_reliability", 0.0)), 12),
        "context_budget_margin": round(float(ep.get("context_budget_margin", 0.0)), 12),
        "silent_degradation_detected": bool(ep.get("silent_degradation_detected", False)),
        "caching_active": bool(ep.get("caching_active", False)),
        # --- performance (timing excluded for byte-stability) ---
        "fitness_noise_floor": round(float(pf.get("noise_floor", 0.0)), 12),
        # --- bookkeeping ---
        "warning_count": len(list(warnings)),
        "unmeasured_fields": unmeasured,
        "all_fields_measured": not unmeasured,
    }


# ---------------------------------------------------------------------------
# Scorecard rendering (stdlib only, byte-stable)
# ---------------------------------------------------------------------------


def _rows(summary: dict[str, Any]) -> list[tuple[str, str]]:
    """Ordered (label, value) rows for the scorecard, headline first."""

    def fmt(x: Any) -> str:
        if isinstance(x, bool):
            return "yes" if x else "no"
        if isinstance(x, float):
            return f"{x:.6f}".rstrip("0").rstrip(".") if x else "0"
        if isinstance(x, list):
            return ", ".join(str(i) for i in x) if x else "(none)"
        return str(x)

    return [
        ("Judge noise floor (headline)", fmt(summary["judge_noise_floor"])),
        ("Judge consistency (1 - CV)", fmt(summary["judge_consistency"])),
        ("Consistency samples", fmt(summary["consistency_samples"])),
        ("Anchoring usage", fmt(summary["anchoring_usage"])),
        ("Scale monotonic", fmt(summary["scale_monotonic"])),
        ("Schema reliability", fmt(summary["schema_reliability"])),
        ("Silent degradation detected", fmt(summary["silent_degradation_detected"])),
        ("Context budget margin", fmt(summary["context_budget_margin"])),
        ("Fitness noise floor", fmt(summary["fitness_noise_floor"])),
        ("All fields measured", fmt(summary["all_fields_measured"])),
        ("Unmeasured fields", fmt(summary["unmeasured_fields"])),
    ]


def _render_markdown(summary: dict[str, Any]) -> str:
    nf = summary["judge_noise_floor"]
    lines = [
        "# mini-omega-lock preflight scorecard",
        "",
        f"**Judge noise floor: `{nf}`** — an A/B fitness delta smaller than "
        "this is below the judge's own noise and is not a real improvement.",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for label, value in _rows(summary):
        lines.append(f"| {label} | `{value}` |")
    lines.append("")
    lines.append(f"_schema: `{summary['schema_version']}`_")
    lines.append("")
    return "\n".join(lines)


def _render_html(summary: dict[str, Any]) -> str:
    nf = html.escape(str(summary["judge_noise_floor"]))
    body_rows = "\n".join(
        f"      <tr><td>{html.escape(label)}</td>"
        f"<td><code>{html.escape(value)}</code></td></tr>"
        for label, value in _rows(summary)
    )
    schema = html.escape(summary["schema_version"])
    # Self-contained single file: inline CSS, no external assets, no
    # timestamp (byte-stable for golden tests).
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>mini-omega-lock preflight scorecard</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 48rem; margin: 2rem auto; padding: 0 1rem; }}
  .headline {{ font-size: 1.5rem; font-weight: 700; margin: 0 0 .25rem; }}
  .headline code {{ background: #f3f4f6; padding: .1rem .4rem; border-radius: .25rem; }}
  .sub {{ color: #555; margin: 0 0 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: .5rem .75rem; border-bottom: 1px solid #e5e7eb; }}
  th {{ background: #f9fafb; }}
  code {{ font-family: ui-monospace, monospace; }}
  footer {{ margin-top: 1.5rem; color: #888; font-size: .85rem; }}
</style>
</head>
<body>
  <p class="headline">Judge noise floor: <code>{nf}</code></p>
  <p class="sub">An A/B fitness delta smaller than this is below the judge's own noise &mdash; not a real improvement.</p>
  <table>
    <thead><tr><th>Metric</th><th>Value</th></tr></thead>
    <tbody>
{body_rows}
    </tbody>
  </table>
  <footer>schema: <code>{schema}</code></footer>
</body>
</html>
"""


def render_scorecard(summary: dict[str, Any], fmt: str = "md") -> str:
    """Render a single-file preflight scorecard from a summary dict.

    Args:
        summary: The dict from :func:`build_summary`.
        fmt: ``"md"`` / ``"markdown"`` for Markdown, ``"html"`` for a
            self-contained HTML page (inline CSS, no external assets, no
            timestamp — byte-stable).

    Returns:
        The rendered scorecard string.

    Raises:
        ValueError: on an unsupported ``fmt``.
    """
    f = fmt.strip().lower()
    if f in ("md", "markdown"):
        return _render_markdown(summary)
    if f == "html":
        return _render_html(summary)
    raise ValueError(
        f"unsupported scorecard format {fmt!r}; use 'md' (markdown) or 'html'."
    )


def summary_json(summary: dict[str, Any]) -> str:
    """Serialise a summary dict to deterministic JSON (sorted keys + newline)."""
    return json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n"

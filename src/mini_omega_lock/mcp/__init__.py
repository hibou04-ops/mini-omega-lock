# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""MCP server exposing mini-omega-lock's empirical preflight probes.

Run with:

    python -m mini_omega_lock.mcp           # stdio transport
    python -m mini_omega_lock.mcp --http    # streamable-http transport

Ten tools cover the full probe surface (regenerated list in
``docs/generated/claims.md`` — `scripts/check_repo_consistency.py` fails
if this docstring and the registered ``@mcp_app.tool()`` decorators
drift):

* ``empirical_preflight``               — combined judge / endpoint / performance probe
* ``measure_judge_consistency``         — judge stability across repeated calls
* ``measure_gate_flip_rate``            — fraction of consecutive call-pairs where a hard gate flips
* ``measure_scale_monotonicity``        — does the judge preserve a bad < mid < good ordering
* ``probe_strict_schema``               — strict-schema parse-success rate + silent-degradation signal
* ``compute_context_margin``            — deterministic context-budget headroom (chars heuristic)
* ``compute_context_margin_from_texts`` — tokenizer-exact context-budget headroom
* ``noise_floor_estimate``              — fitness variance from repeated evaluations
* ``project_performance``               — wall-time projection from probe latencies
* ``derive_adaptation_plan``            — convert measurements into an omegaprompt AdaptationPlan

Use these BEFORE running a full omegaprompt calibration to verify the
runtime environment is ship-grade.
"""

from __future__ import annotations

from mini_omega_lock.mcp.server import mcp_app

__all__ = ["mcp_app"]

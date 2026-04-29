# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""MCP server exposing mini-omega-lock's empirical preflight probes.

Run with:

    python -m mini_omega_lock.mcp           # stdio transport
    python -m mini_omega_lock.mcp --http    # streamable-http transport

Five tools cover the full probe surface:

* ``empirical_preflight``       — combined judge / endpoint / performance probe
* ``measure_judge_consistency`` — judge stability across repeated calls
* ``compute_context_margin``    — deterministic context-budget headroom
* ``noise_floor_estimate``      — fitness variance from repeated evaluations
* ``project_performance``       — wall-time projection from probe latencies

Use these BEFORE running a full omegaprompt calibration to verify the
runtime environment is ship-grade.
"""

from __future__ import annotations

from mini_omega_lock.mcp.server import mcp_app

__all__ = ["mcp_app"]

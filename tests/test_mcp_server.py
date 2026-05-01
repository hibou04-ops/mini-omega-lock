# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Smoke tests for the mini-omega-lock MCP server."""

from __future__ import annotations

import asyncio

import pytest

mcp = pytest.importorskip("mcp")


@pytest.fixture(scope="module")
def mcp_app():
    from mini_omega_lock.mcp import mcp_app as app

    return app


@pytest.fixture(scope="module")
def tools(mcp_app):
    return asyncio.run(mcp_app.list_tools())


EXPECTED_TOOLS = {
    "empirical_preflight",
    "measure_judge_consistency",
    "measure_gate_flip_rate",
    "compute_context_margin",
    "noise_floor_estimate",
    "project_performance",
}


def test_six_probes_registered(tools):
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS


def test_each_tool_has_description(tools):
    for tool in tools:
        assert tool.description and len(tool.description) > 50


def test_each_tool_has_input_schema(tools):
    for tool in tools:
        assert tool.inputSchema is not None
        assert tool.inputSchema.get("properties")


def test_compute_context_margin_executes_without_llm(mcp_app):
    """compute_context_margin is pure deterministic — tool execution should work."""
    result = asyncio.run(
        mcp_app.call_tool(
            "compute_context_margin",
            {
                "system_prompt_chars": 1000,
                "rubric_chars": 2000,
                "longest_input_chars": 5000,
                "longest_reference_chars": 1000,
                "longest_response_chars": 4000,
                "context_window_tokens": 200000,
            },
        )
    )
    # FastMCP returns a list of content blocks; the first block has the JSON result.
    assert result is not None


def test_empirical_preflight_schema_includes_strict_schema_probe_params(tools):
    """Reviewer 2순위: MCP signature must accept strict_schema_probe_messages
    so the composite empirical_preflight can actually probe schema reliability
    rather than fail-closing to 0.0 every time."""
    ep = next(t for t in tools if t.name == "empirical_preflight")
    properties = ep.inputSchema["properties"]
    assert "strict_schema_probe_messages" in properties, (
        "MCP empirical_preflight must expose strict_schema_probe_messages — "
        "without it the README's 'all five probes' claim doesn't match runtime."
    )
    assert "strict_schema_provider" in properties
    assert "fitness_samples" in properties

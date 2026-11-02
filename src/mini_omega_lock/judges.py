# SPDX-License-Identifier: Apache-2.0
"""Standalone judge wrapper with no provider SDK imports at import time."""

from mini_omega_lock._vendor.judges.llm_judge import LLMJudge

__all__ = ["LLMJudge"]

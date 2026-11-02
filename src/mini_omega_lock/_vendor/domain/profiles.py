# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Execution profiles and beginner-facing structural risk contracts."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExecutionProfile(str, Enum):
    """How aggressively the engine may relax safeguards."""

    GUARDED = "guarded"
    EXPEDITION = "expedition"


class ShipRecommendation(str, Enum):
    """Top-level deployment recommendation."""

    SHIP = "ship"
    HOLD = "hold"
    EXPERIMENT = "experiment"
    BLOCK = "block"


class RiskCategory(str, Enum):
    """Beginner-friendly framing for structural fatigue boundaries."""

    SAFETY_BOUNDARY = "safety boundary"
    VALIDATION_STRENGTH = "validation strength"
    EXPERIMENTAL_RISK = "experimental risk"
    DEPLOYMENT_READINESS = "deployment readiness"


class BoundaryWarning(BaseModel):
    """A visible warning about structural risk or boundary fatigue."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1)
    category: RiskCategory
    severity: str = Field(default="warning", pattern="^(info|warning|critical)$")
    summary: str = Field(..., min_length=1)
    detail: str = Field(default="")
    affects_guarded_boundary: bool = Field(default=True)


class RelaxedSafeguard(BaseModel):
    """One explicit safeguard the expedition profile relaxed."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    increased_risk: str = Field(..., min_length=1)

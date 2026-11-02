# SPDX-License-Identifier: Apache-2.0
"""Explicit, optional boundaries to the omegaprompt package.

Core probes never import the parent package. Install [bridge] and use
these converters when exchanging Pydantic records or provider instances.
"""

from __future__ import annotations

import importlib
from typing import Any

from pydantic import BaseModel

from mini_omega_lock._vendor.providers.base import (
    ProviderCapabilities,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)


def to_omegaprompt_report(report: BaseModel | dict[str, Any]):
    """Convert a local report to the parent's report using JSON-compatible data."""
    try:
        PreflightReport = importlib.import_module("omegaprompt.preflight").PreflightReport
    except ModuleNotFoundError as exc:
        if exc.name != "omegaprompt":
            raise
        raise RuntimeError(
            "omegaprompt integration requires pip install 'mini-omega-lock[bridge]'"
        ) from exc
    data = report.model_dump(mode="json") if isinstance(report, BaseModel) else report
    return PreflightReport.model_validate(data)


def adapt_omegaprompt_provider(provider: Any):
    """Adapt a parent provider's request, response, capabilities and exception types.

    Pass the returned object to the local LLMJudge. This boundary is
    explicit because independently packaged Pydantic classes have different
    identities even when their JSON contracts match.
    """
    try:
        parent_types = importlib.import_module("omegaprompt.providers.base")
        ParentProviderError = parent_types.ProviderError
        ParentProviderRequest = parent_types.ProviderRequest
    except ModuleNotFoundError as exc:
        if exc.name != "omegaprompt":
            raise
        raise RuntimeError(
            "omegaprompt integration requires pip install 'mini-omega-lock[bridge]'"
        ) from exc

    class ProviderBridge:
        name = provider.name
        model = provider.model

        def capabilities(self) -> ProviderCapabilities:
            caps = provider.capabilities()
            return ProviderCapabilities.model_validate(caps.model_dump(mode="json"))

        def call(self, request: ProviderRequest) -> ProviderResponse:
            parent_request = ParentProviderRequest.model_validate(request.model_dump())
            try:
                response = provider.call(parent_request)
            except ParentProviderError as exc:
                raise ProviderError(str(exc)) from exc
            parsed = response.parsed
            if parsed is not None and request.output_schema is not None:
                parsed = request.output_schema.model_validate(parsed.model_dump(mode="json"))
            data = response.model_dump(mode="json", exclude={"parsed"})
            return ProviderResponse.model_validate({**data, "parsed": parsed})

    return ProviderBridge()


__all__ = ["adapt_omegaprompt_provider", "to_omegaprompt_report"]

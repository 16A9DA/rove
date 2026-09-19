from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from app.tools.base import FinishParams, Tool, ToolRegistry, ToolRiskLevel, finish

# ponytail: flat length cap, matches BrowserController.get_text's cap — raise if a
# real task needs more.
MAX_FETCH_CHARS = 5000
FETCH_TIMEOUT_SECONDS = 15.0


class FetchUrlParams(BaseModel):
    url: str


def fetch_url(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, FetchUrlParams)
    response = httpx.get(params.url, follow_redirects=True, timeout=FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    return {"content": response.text[:MAX_FETCH_CHARS]}


def research_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool("fetch_url", "Fetch a URL's raw content via HTTP GET, no browser involved.", FetchUrlParams, ToolRiskLevel.LOW, fetch_url))
    registry.register(Tool("finish", "Report the subtask as complete with a result.", FinishParams, ToolRiskLevel.LOW, finish))
    return registry

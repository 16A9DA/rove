import json
from unittest.mock import patch

import httpx

from app.help_request import HelpRequest
from app.tools import ToolExecutor, research_registry


def test_fetch_url_returns_capped_content() -> None:
    fake_response = httpx.Response(200, text="hello world", request=httpx.Request("GET", "https://example.com"))
    with patch("app.tools.research.httpx.get", return_value=fake_response) as mock_get:
        result = ToolExecutor(research_registry(HelpRequest())).execute("id1", "fetch_url", json.dumps({"url": "https://example.com"}))

    mock_get.assert_called_once()
    assert not result.is_error
    assert json.loads(result.content) == {"content": "hello world"}


def test_fetch_url_surfaces_http_errors() -> None:
    fake_request = httpx.Request("GET", "https://example.com")
    fake_response = httpx.Response(404, request=fake_request)
    with patch("app.tools.research.httpx.get", return_value=fake_response):
        result = ToolExecutor(research_registry(HelpRequest())).execute("id1", "fetch_url", json.dumps({"url": "https://example.com"}))

    assert result.is_error

from __future__ import annotations

import httpx
import pytest

from brokerai.bots.researcher.llm import (
    _grok_effort_payload,
    _parse_api_error_body,
    _raise_for_status_with_detail,
)


def test_parse_api_error_body_openai_style():
    response = httpx.Response(
        403,
        json={"error": {"message": "You have run out of credits"}},
    )
    assert _parse_api_error_body(response) == "You have run out of credits"


def test_grok_effort_payload_maps_reasoning():
    assert _grok_effort_payload("high") == {"effort": "high"}
    assert _grok_effort_payload(None) == {}


def test_raise_for_status_with_detail_includes_grok_hint():
    response = httpx.Response(
        403,
        json={"error": {"message": "Forbidden"}},
    )
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        _raise_for_status_with_detail(response, provider_label="Grok")
    assert "Forbidden" in str(exc_info.value)
    assert "console.x.ai" in str(exc_info.value)

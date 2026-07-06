from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from brokerai.bots.researcher.llm import _parse_chat_completion, _request_chat_completion


def test_parse_chat_completion_returns_usage():
    data = {
        "choices": [{"message": {"content": "Hello world"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    result = _parse_chat_completion(data, "OpenAI")
    assert result.content == "Hello world"
    assert result.usage == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }


@pytest.mark.asyncio
async def test_request_chat_completion_records_cost():
    response_json = {
        "choices": [{"message": {"content": "Analysis complete"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    mock_response = httpx.Response(200, json=response_json, request=httpx.Request("POST", "https://api.test"))

    with (
        patch(
            "brokerai.bots.researcher.llm.httpx.AsyncClient",
        ) as client_cls,
        patch("brokerai.bots.researcher.llm._post_with_retry", AsyncMock(return_value=mock_response)),
        patch("brokerai.bots.researcher.llm.record_cost_entry_task") as record_task,
    ):
        client_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        content = await _request_chat_completion(
            url="https://api.test/chat/completions",
            headers={},
            model_name="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            provider_label="OpenAI",
            provider_type="openai",
            cost_context={
                "operation": "forex_analysis",
                "source": "daily_report",
                "forex_group": "EUR",
            },
        )

    assert content == "Analysis complete"
    record_task.assert_called_once()
    args, kwargs = record_task.call_args
    assert args[0] == "llm"
    assert kwargs["source"] == "daily_report"
    metadata = kwargs["metadata"]
    assert metadata["input_tokens"] == 100
    assert metadata["output_tokens"] == 50
    assert metadata["forex_group"] == "EUR"
    assert metadata["operation"] == "forex_analysis"

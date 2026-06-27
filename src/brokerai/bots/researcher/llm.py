from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_OPENAI_COMPAT_TYPES = {"openai", "grok"}
_PROVIDER_LABELS = {"openai": "OpenAI", "grok": "Grok", "open_webui": "Open WebUI"}
_RESEARCH_CHAT_TIMEOUT = 300.0
_RESEARCH_MAX_OUTPUT_TOKENS = 8192
_GROK_RESPONSES_TIMEOUT = 300.0
_RATE_LIMIT_MAX_RETRIES = 3
_RATE_LIMIT_INITIAL_DELAY = 2.0


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


async def _post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    json: dict,
    headers: dict[str, str],
    max_retries: int = _RATE_LIMIT_MAX_RETRIES,
) -> httpx.Response:
    """POST with exponential backoff on HTTP 429."""
    delay = _RATE_LIMIT_INITIAL_DELAY
    response: httpx.Response | None = None
    for attempt in range(max_retries + 1):
        response = await client.post(url, json=json, headers=headers)
        if response.status_code != 429 or attempt == max_retries:
            return response
        logger.warning(
            "Rate limited (429) on %s; retrying in %.1fs (attempt %d/%d)",
            url,
            delay,
            attempt + 1,
            max_retries,
        )
        await asyncio.sleep(delay)
        delay *= 2
    assert response is not None
    return response


async def test_open_webui(
    base_url: str,
    model_name: str,
    api_key: str | None = None,
) -> tuple[bool, str]:
    base = base_url.rstrip("/")
    headers = _auth_headers(api_key)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            models_url = f"{base}/api/models"
            response = await client.get(models_url, headers=headers)
            if response.status_code == 401:
                return False, "Open WebUI authentication failed"
            if response.status_code >= 400:
                chat_ok, chat_msg = await _test_open_webui_chat(client, base, model_name, headers)
                if chat_ok:
                    return True, chat_msg
                return False, f"Open WebUI returned HTTP {response.status_code}"

            data = response.json()
            model_ids: set[str] = set()
            if isinstance(data, dict):
                for item in data.get("data") or []:
                    if isinstance(item, dict) and item.get("id"):
                        model_ids.add(str(item["id"]))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        mid = item.get("id") or item.get("name")
                        if mid:
                            model_ids.add(str(mid))

            if model_ids and model_name not in model_ids:
                return False, f"Model '{model_name}' not found on Open WebUI"

            return True, f"Open WebUI connection successful (model: {model_name})"
    except httpx.HTTPError as exc:
        return False, f"Open WebUI request failed: {exc}"


async def _test_open_webui_chat(
    client: httpx.AsyncClient,
    base: str,
    model_name: str,
    headers: dict[str, str],
) -> tuple[bool, str]:
    url = f"{base}/api/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Reply with OK only."}],
        "max_tokens": 5,
    }
    try:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            return False, f"Chat completion failed: HTTP {response.status_code}"
        return True, f"Open WebUI chat successful (model: {model_name})"
    except httpx.HTTPError as exc:
        return False, f"Open WebUI chat failed: {exc}"


async def test_openai_compatible(
    base_url: str,
    model_name: str,
    api_key: str | None,
    *,
    provider_label: str = "API",
) -> tuple[bool, str]:
    if not api_key:
        return False, f"{provider_label} API key is required"

    base = base_url.rstrip("/")
    headers = _auth_headers(api_key)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            models_url = f"{base}/models"
            response = await client.get(models_url, headers=headers)
            if response.status_code == 401:
                return False, f"{provider_label} authentication failed"
            if response.status_code >= 400:
                chat_ok, chat_msg = await _test_openai_compatible_chat(
                    client, base, model_name, headers, provider_label
                )
                if chat_ok:
                    return True, chat_msg
                return False, f"{provider_label} returned HTTP {response.status_code}"

            data = response.json()
            model_ids: set[str] = set()
            if isinstance(data, dict):
                for item in data.get("data") or []:
                    if isinstance(item, dict) and item.get("id"):
                        model_ids.add(str(item["id"]))

            if model_ids and model_name not in model_ids:
                return False, f"Model '{model_name}' not found on {provider_label}"

            return True, f"{provider_label} connection successful (model: {model_name})"
    except httpx.HTTPError as exc:
        return False, f"{provider_label} request failed: {exc}"


async def _test_openai_compatible_chat(
    client: httpx.AsyncClient,
    base: str,
    model_name: str,
    headers: dict[str, str],
    provider_label: str,
) -> tuple[bool, str]:
    url = f"{base}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Reply with OK only."}],
        "max_tokens": 5,
    }
    try:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            return False, f"Chat completion failed: HTTP {response.status_code}"
        return True, f"{provider_label} chat successful (model: {model_name})"
    except httpx.HTTPError as exc:
        return False, f"{provider_label} chat failed: {exc}"


async def analyze_with_open_webui(
    base_url: str,
    model_name: str,
    messages: list[dict[str, str]],
    api_key: str | None = None,
    *,
    reasoning_effort: str | None = None,
) -> str:
    base = base_url.rstrip("/")
    url = f"{base}/api/chat/completions"
    headers = {**_auth_headers(api_key), "Content-Type": "application/json"}
    return await _request_chat_completion(
        url=url,
        headers=headers,
        model_name=model_name,
        messages=messages,
        provider_label="Open WebUI",
        reasoning_effort=reasoning_effort,
    )


async def analyze_openai_compatible(
    base_url: str,
    model_name: str,
    messages: list[dict[str, str]],
    api_key: str | None,
    *,
    provider_label: str = "API",
    reasoning_effort: str | None = None,
) -> str:
    if not api_key:
        raise RuntimeError(f"{provider_label} API key is required")

    base = base_url.rstrip("/")
    url = f"{base}/chat/completions"
    headers = {**_auth_headers(api_key), "Content-Type": "application/json"}
    return await _request_chat_completion(
        url=url,
        headers=headers,
        model_name=model_name,
        messages=messages,
        provider_label=provider_label,
        reasoning_effort=reasoning_effort,
    )


async def _request_chat_completion(
    *,
    url: str,
    headers: dict[str, str],
    model_name: str,
    messages: list[dict[str, str]],
    provider_label: str,
    reasoning_effort: str | None = None,
) -> str:
    payload: dict = {
        "model": model_name,
        "messages": messages,
        "max_tokens": _RESEARCH_MAX_OUTPUT_TOKENS,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    else:
        payload["temperature"] = 0.3

    async with httpx.AsyncClient(timeout=_RESEARCH_CHAT_TIMEOUT) as client:
        response = await _post_with_retry(
            client, url, json=payload, headers=headers
        )
        if response.status_code == 400 and reasoning_effort:
            fallback = {
                "model": model_name,
                "messages": messages,
                "max_tokens": _RESEARCH_MAX_OUTPUT_TOKENS,
                "temperature": 0.3,
            }
            response = await _post_with_retry(
                client, url, json=fallback, headers=headers
            )
        response.raise_for_status()
        return _parse_chat_completion(response.json(), provider_label)


def _parse_chat_completion(data: dict, provider_label: str) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"{provider_label} returned no choices")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not content.strip():
        raise RuntimeError(f"{provider_label} returned empty content")
    return content.strip()


def _parse_responses_output(data: dict) -> str:
    parts: list[str] = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text":
                text = content.get("text") or ""
                if text.strip():
                    parts.append(text.strip())
    if not parts:
        raise RuntimeError("Grok Responses API returned no output text")
    return "\n".join(parts)


async def grok_web_search(
    base_url: str,
    model_name: str,
    api_key: str,
    messages: list[dict[str, str]],
    *,
    reasoning_effort: str | None = None,
) -> str:
    """Call xAI Responses API with web_search enabled."""
    if not api_key:
        raise RuntimeError("Grok API key is required")

    base = base_url.rstrip("/")
    url = f"{base}/responses"
    headers = {**_auth_headers(api_key), "Content-Type": "application/json"}
    payload: dict = {
        "model": model_name,
        "input": messages,
        "tools": [{"type": "web_search"}],
        "max_output_tokens": _RESEARCH_MAX_OUTPUT_TOKENS,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    async with httpx.AsyncClient(timeout=_GROK_RESPONSES_TIMEOUT) as client:
        response = await _post_with_retry(
            client, url, json=payload, headers=headers
        )
        if response.status_code == 400 and reasoning_effort:
            fallback = {k: v for k, v in payload.items() if k != "reasoning_effort"}
            response = await _post_with_retry(
                client, url, json=fallback, headers=headers
            )
        response.raise_for_status()
        return _parse_responses_output(response.json())


async def grok_x_search(
    base_url: str,
    model_name: str,
    api_key: str,
    messages: list[dict[str, str]],
    *,
    reasoning_effort: str | None = None,
) -> str:
    """Call xAI Responses API with X (formerly Twitter) search enabled."""
    if not api_key:
        raise RuntimeError("Grok API key is required")

    base = base_url.rstrip("/")
    url = f"{base}/responses"
    headers = {**_auth_headers(api_key), "Content-Type": "application/json"}
    payload: dict = {
        "model": model_name,
        "input": messages,
        "tools": [{"type": "x_search"}],
        "max_output_tokens": _RESEARCH_MAX_OUTPUT_TOKENS,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    async with httpx.AsyncClient(timeout=_GROK_RESPONSES_TIMEOUT) as client:
        response = await _post_with_retry(
            client, url, json=payload, headers=headers
        )
        if response.status_code == 400 and reasoning_effort:
            fallback = {k: v for k, v in payload.items() if k != "reasoning_effort"}
            response = await _post_with_retry(
                client, url, json=fallback, headers=headers
            )
        response.raise_for_status()
        return _parse_responses_output(response.json())


async def test_model(
    model_type: str,
    base_url: str,
    model_name: str,
    api_key: str | None = None,
) -> tuple[bool, str]:
    if model_type == "open_webui":
        return await test_open_webui(base_url, model_name, api_key)
    if model_type in _OPENAI_COMPAT_TYPES:
        label = _PROVIDER_LABELS.get(model_type, model_type)
        return await test_openai_compatible(
            base_url, model_name, api_key, provider_label=label
        )
    return False, f"Provider type '{model_type}' is not supported yet"


async def analyze_with_model(
    model_type: str,
    base_url: str,
    model_name: str,
    messages: list[dict[str, str]],
    api_key: str | None = None,
    *,
    reasoning_effort: str | None = None,
) -> str:
    if model_type == "open_webui":
        return await analyze_with_open_webui(
            base_url,
            model_name,
            messages,
            api_key,
            reasoning_effort=reasoning_effort,
        )
    if model_type in _OPENAI_COMPAT_TYPES:
        label = _PROVIDER_LABELS.get(model_type, model_type)
        return await analyze_openai_compatible(
            base_url,
            model_name,
            messages,
            api_key,
            provider_label=label,
            reasoning_effort=reasoning_effort,
        )
    raise RuntimeError(f"Provider type '{model_type}' is not supported yet")

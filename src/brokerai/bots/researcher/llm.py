from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from brokerai.cost.categories import LLM
from brokerai.cost.ledger import record_cost_entry_task
from brokerai.cost.llm_pricing import estimate_llm_cost_usd
from brokerai.cost.llm_usage import parse_llm_usage

logger = logging.getLogger(__name__)

_OPENAI_COMPAT_TYPES = {"openai", "grok"}
_PROVIDER_LABELS = {
    "openai": "OpenAI",
    "grok": "Grok",
    "open_webui": "Open WebUI",
    "claude": "Claude",
}
_ANTHROPIC_VERSION = "2023-06-01"
_RESEARCH_CHAT_TIMEOUT = 300.0
_RESEARCH_MAX_OUTPUT_TOKENS = 8192
_GROK_RESPONSES_TIMEOUT = 300.0
_RATE_LIMIT_MAX_RETRIES = 3
_RATE_LIMIT_INITIAL_DELAY = 2.0

CostContext = dict[str, Any]


@dataclass(frozen=True)
class LlmCallResult:
    content: str
    usage: dict[str, Any] | None


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


def _parse_api_error_body(response: httpx.Response) -> str | None:
    """Extract a human-readable message from provider JSON error bodies."""
    try:
        data = response.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    err = data.get("error")
    if isinstance(err, dict):
        for key in ("message", "detail", "code"):
            value = err.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("message", "detail", "error"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _http_status_hint(status_code: int, *, provider_label: str) -> str | None:
    if status_code == 403 and provider_label == "Grok":
        return (
            "Check console.x.ai: API key ACLs must include api-key:model:grok-4.3 (or "
            "api-key:model:*) and api-key:endpoint:*. X Premium / SuperGrok web "
            "subscriptions do not grant API access — create a pay-as-you-go API key."
        )
    if status_code == 401:
        return f"Verify the {provider_label} API key in Settings → Models."
    return None


def _raise_for_status_with_detail(response: httpx.Response, *, provider_label: str) -> None:
    if response.is_success:
        return
    detail = _parse_api_error_body(response)
    hint = _http_status_hint(response.status_code, provider_label=provider_label)
    parts = [f"{provider_label} returned HTTP {response.status_code}"]
    if detail:
        parts.append(detail)
    if hint:
        parts.append(hint)
    try:
        req = response.request
    except RuntimeError:
        req = httpx.Request("POST", "https://localhost")
    raise httpx.HTTPStatusError(
        " — ".join(parts),
        request=req,
        response=response,
    )


def _grok_effort_payload(reasoning_effort: str | None) -> dict:
    """Map BrokerAI reasoning_effort to xAI's `effort` parameter."""
    if not reasoning_effort:
        return {}
    return {"effort": reasoning_effort}


def _operation_label(operation: str) -> str:
    labels = {
        "forex_analysis": "Forex analysis",
        "synthesis": "Report synthesis",
        "web_search": "Web search",
        "x_search": "X search",
        "weekly_brief": "Weekly brief",
        "weekly_debrief": "Weekly debrief",
        "connection_test": "Connection test",
        "llm_call": "LLM call",
    }
    return labels.get(operation, operation.replace("_", " ").title())


def _build_cost_description(
    operation: str,
    model_name: str,
    context: dict[str, Any],
) -> str:
    label = _operation_label(operation)
    forex_group = context.get("forex_group")
    if forex_group:
        return f"{label} — {forex_group} ({model_name})"
    return f"{label} ({model_name})"


def _schedule_llm_cost_record(
    usage_raw: dict[str, Any] | None,
    *,
    provider_type: str | None,
    model_name: str,
    cost_context: CostContext | None,
) -> None:
    usage = parse_llm_usage(usage_raw)
    if usage is None and not cost_context:
        return

    ctx = dict(cost_context or {})
    billable = bool(ctx.pop("billable", True))
    operation = str(ctx.get("operation") or "llm_call")
    source = ctx.get("source")
    if isinstance(source, str):
        source = source.strip() or None
    else:
        source = None

    amount_usd: float | None = None
    estimated = False
    if usage is not None:
        amount_usd, estimated = estimate_llm_cost_usd(provider_type, model_name, usage)

    metadata: dict[str, Any] = {
        "provider": provider_type,
        "model_name": model_name,
        "billable": billable,
        "estimated": estimated,
        "operation": operation,
        **ctx,
    }
    if usage is not None:
        metadata.update(
            {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            }
        )
        if usage.raw_usage:
            metadata["raw_usage"] = usage.raw_usage

    description = _build_cost_description(operation, model_name, ctx)
    record_cost_entry_task(
        LLM,
        amount_usd,
        description,
        source=source,
        metadata=metadata,
    )


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


# Drop image / video / audio / voice generation models from chat catalogs.
# Keep multimodal chat models that accept images as input (e.g. gpt-4o).
_MEDIA_MODEL_TOKEN_RE = re.compile(
    r"(?:^|[-_.])(?:imagine|image|video|audio|voice|tts|whisper|dall-?e|sora|realtime)"
    r"(?:$|[-_.])",
    re.IGNORECASE,
)


def _is_media_generation_model(item: dict[str, Any], model_id: str, display_name: str) -> bool:
    """Return True when a catalog row is image/video/audio generation (not text chat)."""
    haystack = f"{model_id} {display_name}".strip()
    if _MEDIA_MODEL_TOKEN_RE.search(haystack):
        return True

    outputs = item.get("output_modalities")
    if isinstance(outputs, list) and outputs:
        text_outputs = {"text", "output_text"}
        if not any(str(modality).lower() in text_outputs for modality in outputs):
            return True

    # xAI Imagine models expose image_price and no completion text pricing.
    if item.get("image_price") is not None and item.get("completion_text_token_price") is None:
        return True

    return False


def parse_model_catalog(data: Any) -> list[dict[str, str]]:
    """Parse OpenAI-/Open-WebUI-/Anthropic-shaped model list payloads into id/name rows.

    Image, video, and audio generation models are omitted so Settings → Reports only
    offers text/chat models suitable for research analysis.
    """
    items: list[Any] = []
    if isinstance(data, dict):
        raw = data.get("data")
        if isinstance(raw, list):
            items = raw
        elif isinstance(data.get("models"), list):
            items = data["models"]
    elif isinstance(data, list):
        items = data

    by_id: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        mid = item.get("id") or item.get("name")
        if not mid:
            continue
        model_id = str(mid).strip()
        if not model_id:
            continue
        display = item.get("display_name") or item.get("name") or model_id
        display_name = str(display).strip() or model_id
        if _is_media_generation_model(item, model_id, display_name):
            continue
        by_id[model_id] = display_name

    return [{"id": mid, "name": by_id[mid]} for mid in sorted(by_id)]


async def list_open_webui_models(
    base_url: str,
    api_key: str | None = None,
) -> tuple[bool, str, list[dict[str, str]]]:
    base = base_url.rstrip("/")
    headers = _auth_headers(api_key)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{base}/api/models", headers=headers)
            if response.status_code == 401:
                return False, "Open WebUI authentication failed", []
            if response.status_code >= 400:
                return False, f"Open WebUI returned HTTP {response.status_code}", []
            models = parse_model_catalog(response.json())
            return True, f"Found {len(models)} Open WebUI model(s)", models
    except httpx.HTTPError as exc:
        return False, f"Open WebUI request failed: {exc}", []


async def list_openai_compatible_models(
    base_url: str,
    api_key: str | None,
    *,
    provider_label: str = "API",
) -> tuple[bool, str, list[dict[str, str]]]:
    if not api_key:
        return False, f"{provider_label} API key is required", []

    base = base_url.rstrip("/")
    headers = _auth_headers(api_key)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{base}/models", headers=headers)
            if response.status_code == 401:
                return False, f"{provider_label} authentication failed", []
            if response.status_code >= 400:
                detail = _parse_api_error_body(response) or f"HTTP {response.status_code}"
                hint = _http_status_hint(response.status_code, provider_label=provider_label)
                msg = f"{provider_label} returned {detail}"
                if hint:
                    msg = f"{msg}. {hint}"
                return False, msg, []
            models = parse_model_catalog(response.json())
            return True, f"Found {len(models)} {provider_label} model(s)", models
    except httpx.HTTPError as exc:
        return False, f"{provider_label} request failed: {exc}", []


async def list_claude_models(
    base_url: str,
    api_key: str | None,
) -> tuple[bool, str, list[dict[str, str]]]:
    if not api_key:
        return False, "Claude API key is required", []

    base = base_url.rstrip("/")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{base}/models", headers=headers)
            if response.status_code == 401:
                return False, "Claude authentication failed", []
            if response.status_code >= 400:
                detail = _parse_api_error_body(response) or f"HTTP {response.status_code}"
                return False, f"Claude returned {detail}", []
            models = parse_model_catalog(response.json())
            return True, f"Found {len(models)} Claude model(s)", models
    except httpx.HTTPError as exc:
        return False, f"Claude request failed: {exc}", []


async def list_available_models(
    model_type: str,
    base_url: str,
    api_key: str | None = None,
) -> tuple[bool, str, list[dict[str, str]]]:
    """List models exposed by an API source. Returns (ok, message, models)."""
    if model_type == "open_webui":
        return await list_open_webui_models(base_url, api_key)
    if model_type in _OPENAI_COMPAT_TYPES:
        label = _PROVIDER_LABELS.get(model_type, model_type)
        return await list_openai_compatible_models(
            base_url,
            api_key,
            provider_label=label,
        )
    if model_type == "claude":
        return await list_claude_models(base_url, api_key)
    return False, f"Provider type '{model_type}' is not supported yet", []


async def test_open_webui(
    base_url: str,
    model_name: str | None = None,
    api_key: str | None = None,
) -> tuple[bool, str]:
    ok, message, models = await list_open_webui_models(base_url, api_key)
    if not ok:
        if model_name:
            async with httpx.AsyncClient(timeout=20.0) as client:
                chat_ok, chat_msg = await _test_open_webui_chat(
                    client,
                    base_url.rstrip("/"),
                    model_name,
                    _auth_headers(api_key),
                )
                if chat_ok:
                    return True, chat_msg
        return False, message

    model_ids = {m["id"] for m in models}
    if model_name and model_ids and model_name not in model_ids:
        return False, f"Model '{model_name}' not found on Open WebUI"
    if model_name:
        return True, f"Open WebUI connection successful (model: {model_name})"
    return True, f"Open WebUI connection successful ({len(models)} model(s))"


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
    model_name: str | None,
    api_key: str | None,
    *,
    provider_label: str = "API",
    provider_type: str | None = None,
) -> tuple[bool, str]:
    ok, message, models = await list_openai_compatible_models(
        base_url,
        api_key,
        provider_label=provider_label,
    )
    if not ok:
        if model_name and api_key:
            async with httpx.AsyncClient(timeout=20.0) as client:
                chat_ok, chat_msg = await _test_openai_compatible_chat(
                    client,
                    base_url.rstrip("/"),
                    model_name,
                    _auth_headers(api_key),
                    provider_label,
                    provider_type=provider_type,
                )
                if chat_ok:
                    return True, chat_msg
        return False, message

    model_ids = {m["id"] for m in models}
    if model_name and model_ids and model_name not in model_ids:
        return False, f"Model '{model_name}' not found on {provider_label}"
    if model_name:
        return True, f"{provider_label} connection successful (model: {model_name})"
    return True, f"{provider_label} connection successful ({len(models)} model(s))"


async def test_claude(
    base_url: str,
    model_name: str | None = None,
    api_key: str | None = None,
) -> tuple[bool, str]:
    ok, message, models = await list_claude_models(base_url, api_key)
    if not ok:
        return False, message
    model_ids = {m["id"] for m in models}
    if model_name and model_ids and model_name not in model_ids:
        return False, f"Model '{model_name}' not found on Claude"
    if model_name:
        return True, f"Claude connection successful (model: {model_name})"
    return True, f"Claude connection successful ({len(models)} model(s))"


async def _test_openai_compatible_chat(
    client: httpx.AsyncClient,
    base: str,
    model_name: str,
    headers: dict[str, str],
    provider_label: str,
    *,
    provider_type: str | None = None,
) -> tuple[bool, str]:
    url = f"{base}/chat/completions"
    payload: dict = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Reply with OK only."}],
        "max_tokens": 5,
    }
    if provider_type == "grok":
        payload.update(_grok_effort_payload("low"))
    try:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code >= 400:
            detail = _parse_api_error_body(response) or f"HTTP {response.status_code}"
            hint = _http_status_hint(response.status_code, provider_label=provider_label)
            msg = f"Chat completion failed: {detail}"
            if hint:
                msg = f"{msg}. {hint}"
            return False, msg
        data = response.json()
        usage = data.get("usage") if isinstance(data, dict) else None
        _schedule_llm_cost_record(
            usage if isinstance(usage, dict) else None,
            provider_type=provider_type,
            model_name=model_name,
            cost_context={
                "operation": "connection_test",
                "source": "connection_test",
                "billable": False,
            },
        )
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
    cost_context: CostContext | None = None,
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
        provider_type="open_webui",
        cost_context=cost_context,
    )


async def analyze_openai_compatible(
    base_url: str,
    model_name: str,
    messages: list[dict[str, str]],
    api_key: str | None,
    *,
    provider_label: str = "API",
    reasoning_effort: str | None = None,
    provider_type: str | None = None,
    cost_context: CostContext | None = None,
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
        provider_type=provider_type,
        cost_context=cost_context,
    )


async def _request_chat_completion(
    *,
    url: str,
    headers: dict[str, str],
    model_name: str,
    messages: list[dict[str, str]],
    provider_label: str,
    reasoning_effort: str | None = None,
    provider_type: str | None = None,
    cost_context: CostContext | None = None,
) -> str:
    payload: dict = {
        "model": model_name,
        "messages": messages,
        "max_tokens": _RESEARCH_MAX_OUTPUT_TOKENS,
    }
    if provider_type == "grok":
        payload.update(_grok_effort_payload(reasoning_effort))
        if not reasoning_effort:
            payload["temperature"] = 0.3
    elif reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    else:
        payload["temperature"] = 0.3

    async with httpx.AsyncClient(timeout=_RESEARCH_CHAT_TIMEOUT) as client:
        response = await _post_with_retry(
            client, url, json=payload, headers=headers
        )
        if response.status_code == 400 and reasoning_effort and provider_type != "grok":
            fallback = {
                "model": model_name,
                "messages": messages,
                "max_tokens": _RESEARCH_MAX_OUTPUT_TOKENS,
                "temperature": 0.3,
            }
            response = await _post_with_retry(
                client, url, json=fallback, headers=headers
            )
        if not response.is_success:
            _raise_for_status_with_detail(response, provider_label=provider_label)
        result = _parse_chat_completion(response.json(), provider_label)
        _schedule_llm_cost_record(
            result.usage,
            provider_type=provider_type,
            model_name=model_name,
            cost_context=cost_context,
        )
        return result.content


def _parse_chat_completion(data: dict, provider_label: str) -> LlmCallResult:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"{provider_label} returned no choices")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not content.strip():
        raise RuntimeError(f"{provider_label} returned empty content")
    usage = data.get("usage")
    usage_dict = usage if isinstance(usage, dict) else None
    return LlmCallResult(content=content.strip(), usage=usage_dict)


def _parse_responses_output(data: dict) -> LlmCallResult:
    parts: list[str] = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text":
                text = content.get("text") or ""
                if text.strip():
                    parts.append(text.strip())
    if not parts:
        raise RuntimeError("Grok Responses API returned no output text")
    usage = data.get("usage")
    usage_dict = usage if isinstance(usage, dict) else None
    return LlmCallResult(content="\n".join(parts), usage=usage_dict)


async def grok_web_search(
    base_url: str,
    model_name: str,
    api_key: str,
    messages: list[dict[str, str]],
    *,
    reasoning_effort: str | None = None,
    cost_context: CostContext | None = None,
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
        **_grok_effort_payload(reasoning_effort),
    }

    async with httpx.AsyncClient(timeout=_GROK_RESPONSES_TIMEOUT) as client:
        response = await _post_with_retry(
            client, url, json=payload, headers=headers
        )
        if response.status_code == 400 and reasoning_effort:
            fallback = {
                k: v
                for k, v in payload.items()
                if k != "effort"
            }
            response = await _post_with_retry(
                client, url, json=fallback, headers=headers
            )
        if not response.is_success:
            _raise_for_status_with_detail(response, provider_label="Grok")
        result = _parse_responses_output(response.json())
        ctx = dict(cost_context or {})
        ctx.setdefault("operation", "web_search")
        _schedule_llm_cost_record(
            result.usage,
            provider_type="grok",
            model_name=model_name,
            cost_context=ctx,
        )
        return result.content


async def grok_x_search(
    base_url: str,
    model_name: str,
    api_key: str,
    messages: list[dict[str, str]],
    *,
    reasoning_effort: str | None = None,
    cost_context: CostContext | None = None,
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
        **_grok_effort_payload(reasoning_effort),
    }

    async with httpx.AsyncClient(timeout=_GROK_RESPONSES_TIMEOUT) as client:
        response = await _post_with_retry(
            client, url, json=payload, headers=headers
        )
        if response.status_code == 400 and reasoning_effort:
            fallback = {
                k: v
                for k, v in payload.items()
                if k != "effort"
            }
            response = await _post_with_retry(
                client, url, json=fallback, headers=headers
            )
        if not response.is_success:
            _raise_for_status_with_detail(response, provider_label="Grok")
        result = _parse_responses_output(response.json())
        ctx = dict(cost_context or {})
        ctx.setdefault("operation", "x_search")
        _schedule_llm_cost_record(
            result.usage,
            provider_type="grok",
            model_name=model_name,
            cost_context=ctx,
        )
        return result.content


async def test_model(
    model_type: str,
    base_url: str,
    model_name: str | None = None,
    api_key: str | None = None,
) -> tuple[bool, str]:
    if model_type == "open_webui":
        return await test_open_webui(base_url, model_name, api_key)
    if model_type in _OPENAI_COMPAT_TYPES:
        label = _PROVIDER_LABELS.get(model_type, model_type)
        return await test_openai_compatible(
            base_url,
            model_name,
            api_key,
            provider_label=label,
            provider_type=model_type,
        )
    if model_type == "claude":
        return await test_claude(base_url, model_name, api_key)
    return False, f"Provider type '{model_type}' is not supported yet"


async def analyze_with_model(
    model_type: str,
    base_url: str,
    model_name: str,
    messages: list[dict[str, str]],
    api_key: str | None = None,
    *,
    reasoning_effort: str | None = None,
    cost_context: CostContext | None = None,
) -> str:
    if model_type == "open_webui":
        return await analyze_with_open_webui(
            base_url,
            model_name,
            messages,
            api_key,
            reasoning_effort=reasoning_effort,
            cost_context=cost_context,
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
            provider_type=model_type,
            cost_context=cost_context,
        )
    raise RuntimeError(f"Provider type '{model_type}' is not supported yet")

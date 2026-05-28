"""Anthropic Messages API provider."""

import os
import httpx
from typing import List, Dict, Any, Optional, Tuple

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


async def query(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Query an Anthropic model via the Messages API.

    Anthropic's API takes system prompts as a separate `system` field, not in messages.
    This function extracts any system role messages and routes them correctly.

    Returns: (result_dict, error_str) — exactly one is non-None.
    """
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return None, "ANTHROPIC_API_KEY not set"

    # Extract system message; pass the rest as Anthropic-format messages
    system_text = None
    chat_messages = []
    for m in messages:
        role = m.get('role')
        content = m.get('content', '')
        if role == 'system':
            system_text = content
        elif role in ('user', 'assistant'):
            chat_messages.append({"role": role, "content": content})

    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": chat_messages,
    }
    if system_text:
        payload["system"] = system_text

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(ANTHROPIC_API_URL, headers=headers, json=payload)

            if response.status_code >= 400:
                return None, f"HTTP {response.status_code}: {response.text[:500]}"

            data = response.json()

            if 'content' not in data or not data['content']:
                return None, f"Unexpected response shape: {str(data)[:500]}"

            # Anthropic returns content as a list of blocks. Concatenate text blocks.
            text_parts = []
            for block in data['content']:
                if block.get('type') == 'text':
                    text_parts.append(block.get('text', ''))
            text = ''.join(text_parts).strip()

            if not text:
                stop_reason = data.get('stop_reason', 'unknown')
                return None, f"Empty content (stop_reason: {stop_reason})"

            return {'content': text}, None

    except httpx.TimeoutException:
        return None, f"Timeout after {timeout}s"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

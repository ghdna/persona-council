"""OpenAI Chat Completions API provider."""

import os
import httpx
from typing import List, Dict, Any, Optional, Tuple

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


async def query(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Query an OpenAI model. Message format matches OpenAI/OpenRouter standard.

    Returns: (result_dict, error_str) — exactly one is non-None.
    """
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return None, "OPENAI_API_KEY not set"

    payload = {
        "model": model,
        "messages": messages,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(OPENAI_API_URL, headers=headers, json=payload)

            if response.status_code >= 400:
                return None, f"HTTP {response.status_code}: {response.text[:500]}"

            data = response.json()

            if 'choices' not in data or not data['choices']:
                return None, f"Unexpected response shape: {str(data)[:500]}"

            message = data['choices'][0].get('message') or {}
            content = message.get('content')

            if not content:
                finish = data['choices'][0].get('finish_reason', 'unknown')
                return None, f"Empty content (finish_reason: {finish})"

            return {'content': content}, None

    except httpx.TimeoutException:
        return None, f"Timeout after {timeout}s"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

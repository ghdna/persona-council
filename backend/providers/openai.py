"""OpenAI Chat Completions API provider."""

import os
import re
import httpx
from typing import List, Dict, Any, Optional, Tuple

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"

# Substrings that mark a non-chat model (audio / image / embeddings / etc.).
# /v1/models returns everything the account can access, so we filter to chat.
_OPENAI_EXCLUDE = (
    "audio", "realtime", "transcribe", "tts", "image", "embedding", "moderation",
    "search", "whisper", "dall-e", "babbage", "davinci", "codex", "instruct",
)
# Hide dated snapshots (e.g. gpt-4o-2024-08-06, gpt-4-0613) so the dropdown keeps
# the stable flagship aliases — new releases then appear automatically by alias.
_OPENAI_DATED = re.compile(r"\d{4}-\d{2}-\d{2}|-\d{4}$")


def _is_chat_model(model_id: str) -> bool:
    mid = model_id.lower()
    if any(x in mid for x in _OPENAI_EXCLUDE):
        return False
    if not (mid.startswith("gpt-") or re.match(r"o[1-9]", mid)):
        return False
    if _OPENAI_DATED.search(mid):
        return False
    return True


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


async def list_models(timeout: float = 10.0) -> Tuple[List[str], Optional[str]]:
    """List chat-capable OpenAI models as 'openai/<id>'.

    Filters /v1/models down to chat models (drops audio/image/embeddings and
    dated snapshots — see _is_chat_model), so new flagship releases surface
    automatically. Returns ([...], None) on success or ([], error) on failure
    (caller falls back to the curated list).
    """
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return [], "OPENAI_API_KEY not set"

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(OPENAI_MODELS_URL, headers=headers)
            if response.status_code >= 400:
                return [], f"HTTP {response.status_code}: {response.text[:200]}"
            data = response.json()
            ids = sorted(
                m['id'] for m in data.get('data', [])
                if m.get('id') and _is_chat_model(m['id'])
            )
            return [f"openai/{i}" for i in ids], None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"

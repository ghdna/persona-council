"""Google Gemini API provider."""

import os
import re
import httpx
from typing import List, Dict, Any, Optional, Tuple

GEMINI_API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Non-chat Gemini family models to drop from the dropdown.
_GEMINI_EXCLUDE = ("embedding", "aqa", "imagen", "veo", "tts", "image", "learnlm")
# Hide pinned version snapshots (e.g. gemini-2.0-flash-001) to keep stable aliases.
_GEMINI_PINNED = re.compile(r"-\d{3}$")


async def query(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Query a Google Gemini model.

    Gemini uses a different format from OpenAI:
    - System prompts go in `systemInstruction`, not messages
    - Messages array is called `contents`, with role "model" instead of "assistant"

    Returns: (result_dict, error_str) — exactly one is non-None.
    """
    api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        return None, "GOOGLE_API_KEY (or GEMINI_API_KEY) not set"

    # Convert OpenAI-style messages to Gemini format
    system_text = None
    contents = []
    for m in messages:
        role = m.get('role')
        content = m.get('content', '')
        if role == 'system':
            system_text = content
        elif role == 'assistant':
            contents.append({"role": "model", "parts": [{"text": content}]})
        elif role == 'user':
            contents.append({"role": "user", "parts": [{"text": content}]})

    payload: Dict[str, Any] = {"contents": contents}
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}

    url = GEMINI_API_URL_TEMPLATE.format(model=model) + f"?key={api_key}"
    headers = {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code >= 400:
                return None, f"HTTP {response.status_code}: {response.text[:500]}"

            data = response.json()

            if 'candidates' not in data or not data['candidates']:
                return None, f"Unexpected response shape: {str(data)[:500]}"

            candidate = data['candidates'][0]
            if 'content' not in candidate or 'parts' not in candidate.get('content', {}):
                finish = candidate.get('finishReason', 'unknown')
                return None, f"No content in candidate (finishReason: {finish}). Raw: {str(candidate)[:300]}"

            # Gemini returns content as a list of parts; concatenate text parts
            text_parts = []
            for part in candidate['content']['parts']:
                if 'text' in part:
                    text_parts.append(part['text'])
            text = ''.join(text_parts).strip()

            if not text:
                finish = candidate.get('finishReason', 'unknown')
                return None, f"Empty content (finishReason: {finish})"

            return {'content': text}, None

    except httpx.TimeoutException:
        return None, f"Timeout after {timeout}s"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


async def list_models(timeout: float = 10.0) -> Tuple[List[str], Optional[str]]:
    """List Gemini chat models as 'google/<id>'.

    Keeps models that support generateContent and drops non-chat families and
    pinned version snapshots, so new flagship releases surface automatically.
    Returns ([...], None) on success or ([], error) on failure (caller falls
    back to the curated list).
    """
    api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if not api_key:
        return [], "GOOGLE_API_KEY (or GEMINI_API_KEY) not set"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                GEMINI_MODELS_URL, params={"key": api_key, "pageSize": 1000}
            )
            if response.status_code >= 400:
                return [], f"HTTP {response.status_code}: {response.text[:200]}"
            data = response.json()
            out = []
            for m in data.get('models', []):
                name = m.get('name') or ''            # e.g. "models/gemini-2.5-flash"
                mid = name.split('/', 1)[1] if '/' in name else name
                if not mid.startswith('gemini'):
                    continue
                if 'generateContent' not in (m.get('supportedGenerationMethods') or []):
                    continue
                if any(x in mid.lower() for x in _GEMINI_EXCLUDE):
                    continue
                if _GEMINI_PINNED.search(mid):
                    continue
                out.append(f"google/{mid}")
            return sorted(set(out)), None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"

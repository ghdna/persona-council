"""Ollama local model provider.

Ollama runs a local server (default http://localhost:11434) and needs NO API key
— availability is determined by the server being reachable, not by an env key.
It exposes an OpenAI-compatible chat endpoint, so the message format (system /
user / assistant) maps 1:1 with the OpenAI provider; no translation needed.

Models are whatever the user has `ollama pull`-ed locally, discovered at runtime
via the native /api/tags endpoint (see `list_models`).
"""

import os
import asyncio
import httpx
from typing import List, Dict, Any, Optional, Tuple


# Limit how many generations we send to Ollama concurrently. Ollama serializes
# requests for a model anyway (especially large ones on limited memory), so
# without a limiter all parallel council members open at t=0 and the queued ones
# burn their whole timeout waiting → they all time out together. Gating client-
# side means each request's timeout clock starts when it actually begins running.
# Raise OLLAMA_MAX_CONCURRENCY if your Ollama server has OLLAMA_NUM_PARALLEL > 1.
_MAX_CONCURRENCY = max(1, int(os.getenv("OLLAMA_MAX_CONCURRENCY", "1")))
_semaphore: Optional[asyncio.Semaphore] = None


def _concurrency_limiter() -> asyncio.Semaphore:
    """Lazily-created semaphore (safe: asyncio is single-threaded, no await in
    the check-and-set). Used as `async with _concurrency_limiter():`."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
    return _semaphore


def host() -> str:
    """Base URL of the Ollama server. Override with OLLAMA_HOST (e.g. for Docker
    use http://host.docker.internal:11434 to reach Ollama on the host)."""
    return os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def default_timeout() -> float:
    """Per-request timeout for Ollama generations. Generous by default: reasoning
    models (e.g. deepseek-r1) are slow and Ollama serializes concurrent requests,
    so queued council members need a wide window. Tune with OLLAMA_TIMEOUT."""
    return float(os.getenv("OLLAMA_TIMEOUT", "300"))


async def query(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Query a local Ollama model via its OpenAI-compatible endpoint.

    No API key required. Returns: (result_dict, error_str) — exactly one non-None.
    timeout=None uses default_timeout() (OLLAMA_TIMEOUT). Requests are run through
    a concurrency limiter (OLLAMA_MAX_CONCURRENCY) so that, when Ollama serializes
    them, each request's timeout clock starts when it actually begins — otherwise
    queued requests burn their whole budget waiting and all time out together.
    """
    if timeout is None:
        timeout = default_timeout()

    url = f"{host()}/v1/chat/completions"
    payload = {"model": model, "messages": messages}

    try:
        async with _concurrency_limiter():
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)

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

    except httpx.ConnectError:
        return None, f"Cannot reach Ollama at {host()} (is `ollama serve` running?)"
    except httpx.TimeoutException:
        return None, f"Timeout after {timeout}s"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


async def list_models(timeout: float = 2.0) -> Tuple[List[str], Optional[str]]:
    """List locally-installed models as prefixed identifiers.

    Hits Ollama's native /api/tags endpoint. Returns (['ollama/llama3.2:latest',
    ...], None) on success, or ([], error_str) if the server is unreachable.
    Used by /api/providers to populate the dropdown with what's actually pulled,
    and as the reachability check (error is None ⇒ server is up).
    """
    url = f"{host()}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            if response.status_code >= 400:
                return [], f"HTTP {response.status_code}: {response.text[:200]}"
            data = response.json()
            models = [
                f"ollama/{m['name']}"
                for m in data.get('models', [])
                if m.get('name')
            ]
            return models, None
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"

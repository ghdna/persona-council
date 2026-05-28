"""Provider router. Dispatches model queries to the right backend based on prefix + available keys."""

import os
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Callable

from . import anthropic as anthropic_provider
from . import openai as openai_provider
from . import gemini as gemini_provider
from . import openrouter as openrouter_provider

# Module-level dict for capturing last error per model (full identifier including prefix)
last_errors: Dict[str, str] = {}


def _route(model: str) -> Tuple[Optional[Callable], str, str]:
    """Pick the provider's query function + native model id + provider name.

    Returns: (query_func, native_model_id, provider_name)
             or (None, model, '') if no provider available
    """
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')
    google_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    openrouter_key = os.getenv('OPENROUTER_API_KEY')

    if '/' in model:
        prefix, native_id = model.split('/', 1)
    else:
        prefix, native_id = '', model

    # Try direct provider first (prefix match + key available)
    if prefix == 'anthropic' and anthropic_key:
        return anthropic_provider.query, native_id, 'anthropic'
    if prefix == 'openai' and openai_key:
        return openai_provider.query, native_id, 'openai'
    if prefix in ('google', 'gemini') and google_key:
        return gemini_provider.query, native_id, 'gemini'

    # Fall back to OpenRouter (which expects the full prefixed identifier)
    if openrouter_key:
        return openrouter_provider.query, model, 'openrouter'

    return None, model, ''


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0
) -> Optional[Dict[str, Any]]:
    """Route a model query to the appropriate provider.

    Returns response dict {'content': str, ...} on success, None on failure.
    On failure, records the error in `last_errors[model]` and prints to stdout.
    """
    query_func, native_model, provider_name = _route(model)

    if query_func is None:
        if '/' in model:
            prefix = model.split('/')[0].upper()
            error_msg = (
                f"No provider available for {model}. "
                f"Set {prefix}_API_KEY for direct access, "
                f"or OPENROUTER_API_KEY for multi-provider fallback."
            )
        else:
            error_msg = (
                f"No provider available for '{model}'. "
                f"Model identifier should be in 'provider/model' format. "
                f"Set at least one provider API key in .env."
            )
        last_errors[model] = error_msg
        print(f"[router] {model} → {error_msg}", flush=True)
        return None

    last_errors.pop(model, None)

    result, error = await query_func(native_model, messages, timeout)

    if error:
        last_errors[model] = error
        print(f"[{provider_name}] {model} → {error}", flush=True)
        return None

    return result


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query multiple models in parallel with the same messages payload."""
    tasks = [query_model(model, messages) for model in models]
    responses = await asyncio.gather(*tasks)
    return {model: response for model, response in zip(models, responses)}

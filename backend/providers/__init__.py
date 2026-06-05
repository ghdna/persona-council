"""Provider routing for the Persona Council.

Supports direct API integration with:
- Anthropic (ANTHROPIC_API_KEY)
- OpenAI (OPENAI_API_KEY)
- Google Gemini (GOOGLE_API_KEY or GEMINI_API_KEY)
- Ollama (no key — local server at OLLAMA_HOST, default http://localhost:11434)
- OpenRouter (OPENROUTER_API_KEY) - multi-provider fallback

Model identifiers use a provider/model format:
- anthropic/claude-sonnet-4-5
- openai/gpt-5.1
- google/gemini-2.5-flash
- ollama/llama3.2   (local, no key; models discovered via /api/tags)
- xai/grok-4   (OpenRouter only)
- deepseek/deepseek-chat   (OpenRouter only)

If a direct provider key is set for the model's prefix, calls go directly to that provider.
The ollama/ prefix always routes to the local Ollama server.
Otherwise, falls back to OpenRouter if configured.
"""

from .router import query_model, last_errors, query_models_parallel

__all__ = ['query_model', 'last_errors', 'query_models_parallel']

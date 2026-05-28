"""Configuration for the Persona Council.

User-facing configuration is just provider API keys in `.env`.
Everything else (model selection, mode) is set in the UI per conversation.

The defaults below are fallbacks used only when the UI doesn't pass an override.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────
# Provider API keys (read at request time by the provider router)
# ─────────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ─────────────────────────────────────────────────────────────────────────
# Default council mode (overridable per-request from the UI)
# ─────────────────────────────────────────────────────────────────────────
# "model"   = Karpathy's original (N different models, no personas)
# "persona" = single model run with N persona prompts (default)
# "hybrid"  = N different models, each with a persona prompt
MODE = os.getenv("COUNCIL_MODE", "persona")

# ─────────────────────────────────────────────────────────────────────────
# Persona definitions
# ─────────────────────────────────────────────────────────────────────────
PERSONAS_DIR = Path(__file__).parent.parent / "personas"

PERSONAS = [
    "contrarian",
    "first-principles-skeptic",
    "expansionist",
    "outsider",
    "executor",
]

# Chairman persona file (in PERSONAS_DIR). Empty disables persona injection.
CHAIRMAN_PERSONA = os.getenv("CHAIRMAN_PERSONA", "chairman")

# ─────────────────────────────────────────────────────────────────────────
# Internal model defaults (UI overrides these per request)
# ─────────────────────────────────────────────────────────────────────────
# These exist as fallbacks if the API is called without a `model` parameter
# (e.g., scripting the backend directly). The UI always passes a model.

# Persona mode default — single model used for all personas
PERSONA_MODEL = os.getenv("PERSONA_MODEL", "anthropic/claude-sonnet-4-5")

# Chairman synthesis default
CHAIRMAN_MODEL = os.getenv("CHAIRMAN_MODEL", "anthropic/claude-sonnet-4-5")

# Conversation title generator (fast/cheap model)
TITLE_MODEL = os.getenv("TITLE_MODEL", "anthropic/claude-haiku-4-5")

# Mode "model" — Karpathy's original multi-model council
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4-5",
    "xai/grok-4",
]

# Mode "hybrid" — each persona assigned a specific model
PERSONA_MODEL_MAP = {
    "contrarian": "openai/gpt-5.1",
    "first-principles-skeptic": "google/gemini-3-pro-preview",
    "expansionist": "anthropic/claude-sonnet-4-5",
    "outsider": "xai/grok-4",
    "executor": "deepseek/deepseek-chat",
}

# ─────────────────────────────────────────────────────────────────────────
# Storage
# ─────────────────────────────────────────────────────────────────────────
DATA_DIR = "data/conversations"

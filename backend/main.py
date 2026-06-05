"""FastAPI backend for Persona Council."""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import asyncio

import time

from . import storage
from .config import PERSONA_MODEL, CHAIRMAN_MODEL, TITLE_MODEL
from .providers import (
    ollama as ollama_provider,
    openai as openai_provider,
    anthropic as anthropic_provider,
    gemini as gemini_provider,
)
from .council import (
    run_full_council, generate_conversation_title,
    stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final,
    calculate_aggregate_rankings,
)

app = FastAPI(title="Persona Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────
# Models catalog
# ─────────────────────────────────────────────────────────────────────────
# When a direct provider key is set, models are discovered dynamically from the
# provider's API (so new releases appear automatically — see _discover_models).
# This curated list is the FALLBACK, used when discovery fails or when a provider
# is only reachable via OpenRouter (no direct key to call its /models endpoint).
PROVIDER_MODELS = {
    "anthropic": [
        "anthropic/claude-sonnet-4-5",
        "anthropic/claude-opus-4-5",
        "anthropic/claude-haiku-4-5",
    ],
    "openai": [
        "openai/gpt-5.1",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
    ],
    "google": [
        "google/gemini-3-pro-preview",
        "google/gemini-2.5-flash",
    ],
}

# Models only available via OpenRouter (no direct provider integration yet)
OPENROUTER_ONLY_MODELS = [
    "xai/grok-4",
    "deepseek/deepseek-chat",
]

# Dynamic-discovery functions per provider (return prefixed model identifiers).
_LISTERS = {
    "anthropic": anthropic_provider.list_models,
    "openai": openai_provider.list_models,
    "google": gemini_provider.list_models,
}

# In-memory TTL cache for discovered model lists. /api/providers is hit on every
# frontend mount/refresh, so without this we'd call the provider /models APIs on
# each load. Keyed by provider → (fetched_at, models).
_MODELS_CACHE: Dict[str, Any] = {}
_MODELS_CACHE_TTL = 3600  # seconds


async def _discover_models(provider: str) -> List[str]:
    """Dynamically discovered models for a provider that has a direct key set.

    Falls back to the curated PROVIDER_MODELS list if discovery errors or returns
    nothing. Cached for _MODELS_CACHE_TTL to avoid hammering the provider APIs.
    """
    now = time.time()
    cached = _MODELS_CACHE.get(provider)
    if cached and now - cached[0] < _MODELS_CACHE_TTL:
        return cached[1]

    lister = _LISTERS.get(provider)
    models, err = await lister() if lister else ([], "no lister")
    if err or not models:
        models = PROVIDER_MODELS.get(provider, [])  # graceful fallback to curated

    _MODELS_CACHE[provider] = (now, models)
    return models


class CreateConversationRequest(BaseModel):
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message. `mode` and `model` are optional per-request overrides."""
    content: str
    mode: Optional[str] = None  # "model" | "persona" | "hybrid"
    model: Optional[str] = None  # Overrides PERSONA_MODEL/CHAIRMAN_MODEL/TITLE_MODEL in persona mode


class ConversationMetadata(BaseModel):
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    return {"status": "ok", "service": "Persona Council API"}


@app.get("/api/providers")
async def get_providers():
    """Return which provider keys are configured and which models are usable."""
    keys = {
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
        "google": bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
    }

    # Run all network discovery concurrently to keep this endpoint snappy:
    # Ollama (local, doubles as reachability check) + each direct-key provider.
    direct_providers = [p for p in PROVIDER_MODELS if keys[p]]
    results = await asyncio.gather(
        ollama_provider.list_models(),
        *[_discover_models(p) for p in direct_providers],
    )
    ollama_models, ollama_err = results[0]
    keys["ollama"] = ollama_err is None
    discovered = dict(zip(direct_providers, results[1:]))

    available_models: List[str] = []
    for provider in PROVIDER_MODELS:
        if keys[provider]:
            # Direct key → dynamically discovered models (with curated fallback)
            available_models.extend(discovered[provider])
        elif keys["openrouter"]:
            # No direct key but OpenRouter can serve them → curated static list
            available_models.extend(PROVIDER_MODELS[provider])

    # OpenRouter-only models
    if keys["openrouter"]:
        available_models.extend(OPENROUTER_ONLY_MODELS)

    # Ollama models discovered dynamically from the local server
    available_models.extend(ollama_models)

    # Pick a sensible default. Dynamic lists are sorted alphabetically, so the
    # first entry can be an old model (e.g. gpt-3.5-turbo). Prefer the configured
    # PERSONA_MODEL, then the hand-picked curated flagships, then anything.
    preferred = [PERSONA_MODEL] + [m for ms in PROVIDER_MODELS.values() for m in ms]
    default_model = next((m for m in preferred if m in available_models), None)
    if default_model is None and available_models:
        default_model = available_models[0]

    return {
        "keys": keys,
        "available_models": available_models,
        "default_model": default_model,
        "config_defaults": {
            "persona_model": PERSONA_MODEL,
            "chairman_model": CHAIRMAN_MODEL,
            "title_model": TITLE_MODEL,
        },
    }


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    conversation_id = str(uuid.uuid4())
    return storage.create_conversation(conversation_id)


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_first_message = len(conversation["messages"]) == 0
    storage.add_user_message(conversation_id, request.content)

    if is_first_message:
        title = await generate_conversation_title(request.content, title_model_override=request.model)
        storage.update_conversation_title(conversation_id, title)

    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content, mode=request.mode, model=request.model
    )

    storage.add_assistant_message(
        conversation_id, stage1_results, stage2_results, stage3_result,
        stage1_failures=metadata.get("stage1_failures"),
    )

    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata,
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            storage.add_user_message(conversation_id, request.content)

            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(
                    generate_conversation_title(request.content, title_model_override=request.model)
                )

            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results, stage1_failures = await stage1_collect_responses(
                request.content, mode=request.mode, model=request.model
            )
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results, 'failures': stage1_failures})}\n\n"

            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_member = await stage2_collect_rankings(
                request.content, stage1_results
            )
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_member)
            metadata_payload = {
                'label_to_model': label_to_member,
                'label_to_member': label_to_member,
                'aggregate_rankings': aggregate_rankings,
                'mode': request.mode,
                'model': request.model,
            }
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': metadata_payload})}\n\n"

            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(
                request.content, stage1_results, stage2_results, label_to_member,
                chairman_model_override=request.model
            )
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            storage.add_assistant_message(
                conversation_id, stage1_results, stage2_results, stage3_result,
                stage1_failures=stage1_failures,
            )

            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

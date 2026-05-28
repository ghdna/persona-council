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

from . import storage
from .config import PERSONA_MODEL, CHAIRMAN_MODEL, TITLE_MODEL
from .council import (
    run_full_council, generate_conversation_title,
    stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final,
    calculate_aggregate_rankings,
)

app = FastAPI(title="Persona Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────
# Models catalog — what providers offer, filtered by available keys
# ─────────────────────────────────────────────────────────────────────────
# Curated list. Add/remove model identifiers here as new ones become available.
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

    available_models: List[str] = []
    for provider, models in PROVIDER_MODELS.items():
        # Direct key OR OpenRouter fallback unlocks the models
        if keys[provider] or keys["openrouter"]:
            available_models.extend(models)

    # OpenRouter-only models
    if keys["openrouter"]:
        available_models.extend(OPENROUTER_ONLY_MODELS)

    # Pick a sensible default: configured PERSONA_MODEL if usable, else first available
    if PERSONA_MODEL in available_models:
        default_model = PERSONA_MODEL
    elif available_models:
        default_model = available_models[0]
    else:
        default_model = None

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
        conversation_id, stage1_results, stage2_results, stage3_result
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
            stage1_results = await stage1_collect_responses(
                request.content, mode=request.mode, model=request.model
            )
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

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
                conversation_id, stage1_results, stage2_results, stage3_result
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

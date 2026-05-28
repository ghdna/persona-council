# CLAUDE.md - Technical Notes for Persona Council

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Project Overview

Persona Council is a multi-persona deliberation system extending [Karpathy's llm-council](https://github.com/karpathy/llm-council). The original orchestrates across multiple LLMs (model diversity). This fork adds persona-bound prompting so the same pattern works with a single LLM (prompt diversity), and supports direct provider integration (Anthropic, OpenAI, Gemini) without requiring OpenRouter.

Three council modes:
- **`model`** — Karpathy's original (N models, no personas)
- **`persona`** — Single model, N persona prompts (default)
- **`hybrid`** — N models, one persona per model

Mode and model are selected per-conversation in the UI and overridden via the `mode` / `model` fields on `SendMessageRequest`.

## Architecture

### Backend Structure (`backend/`)

**`config.py`**
- Reads provider API keys from env (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`)
- Internal defaults for `PERSONA_MODEL`, `CHAIRMAN_MODEL`, `TITLE_MODEL`, `COUNCIL_MODELS`, `PERSONA_MODEL_MAP` (used only when UI doesn't override)
- Lists `PERSONAS` and points to `PERSONAS_DIR` (`personas/` at repo root)
- Backend runs on **port 8001**

**`providers/`** — provider router (replaces Karpathy's single-file `openrouter.py`)
- `router.py`: `query_model(model, messages, timeout)` dispatches based on model prefix + available keys.
  - `anthropic/*` → `providers.anthropic` if `ANTHROPIC_API_KEY` set, else OpenRouter
  - `openai/*` → `providers.openai` if `OPENAI_API_KEY` set, else OpenRouter
  - `google/*` or `gemini/*` → `providers.gemini` if `GOOGLE_API_KEY` set, else OpenRouter
  - Anything else (`xai/*`, `deepseek/*`, etc.) → OpenRouter only
- `anthropic.py`: Anthropic Messages API. Extracts system message from messages array into Anthropic's separate `system` field.
- `openai.py`: OpenAI Chat Completions API. Format identical to OpenAI/OpenRouter standard.
- `gemini.py`: Google Gemini API. Converts OpenAI-style messages to Gemini's `contents` / `systemInstruction` format. Uses `model` role instead of `assistant`.
- `openrouter.py`: OpenRouter fallback. Receives the full prefixed model identifier.
- Each provider returns `(result, error)` tuples. Router aggregates errors into module-level `last_errors` dict keyed by full model identifier.

**`council.py`** - The Core Orchestrator
- `get_council_members(mode, persona_model_override)`: Returns list of `{member_id, model, persona}` dicts based on mode. Mode and persona_model can both be overridden per request.
- `stage1_collect_responses(user_query, mode, model)`: Parallel queries via `query_members_parallel`. Each query uses `build_messages(content, persona)` which extracts the persona prompt as a `system` role message.
- `stage2_collect_rankings(user_query, stage1_results)`: Anonymizes responses as `Response A`, `Response B`, etc. Builds `label_to_member` mapping (held in backend memory only, never sent to LLM). Same model+persona pairs as stage1 evaluate the anonymized responses.
- `stage3_synthesize_final(...)`: Chairman synthesizes from all responses + rankings.
- `parse_ranking_from_text()`: Extracts `FINAL RANKING:` section.
- `calculate_aggregate_rankings()`: Computes average rank position across all peer evaluations.
- `generate_conversation_title(user_query, title_model_override)`: Uses TITLE_MODEL or per-request override (whichever model the UI picked, so title gen stays within the same provider).

**`storage.py`** — JSON-based conversation storage in `data/conversations/`. Schema-agnostic; persona/member_id fields persist automatically.

**`main.py`** — FastAPI app with CORS for `localhost:5173` and `localhost:3000`.
- `GET /api/providers` — returns `{keys, available_models, default_model, config_defaults}` based on which provider keys are set. Frontend uses this to populate the model dropdown.
- `POST /api/conversations/{id}/message` and `/message/stream` — accept optional `mode` and `model` overrides in the request body and thread them through to council stages and title generator.
- `PROVIDER_MODELS` catalog: which models to expose in the UI per provider. Edit here to add or remove dropdown options.

### Frontend Structure (`frontend/src/`)

**`App.jsx`**
- Manages: conversations list, current conversation, mode, selectedModel, providers.
- On mount: fetches `/api/providers`, sets `selectedModel = providers.default_model`.
- `mode` and `selectedModel` are passed to ChatInterface as props and to API calls as parameters.

**`api.js`**
- `getProviders()`: GET `/api/providers`
- `sendMessageStream(conversationId, content, mode, model, onEvent)`: POST with `{content, mode, model}` body; processes Server-Sent Events.

**`components/ChatInterface.jsx`**
- Renders mode dropdown (always) and model dropdown (only in `persona` mode — `showModelSelector = mode === 'persona'`).
- Mode/model dropdowns appear only on empty state (single-Q&A flow per conversation).
- Renders provider warning if no API keys are configured (gracefully blocks submission).
- Shows `mode` and `model` badges next to "Persona Council" label after assistant responds.

**`components/Stage1.jsx`**
- Tab view of individual responses.
- Tab labels use persona name (`formatMember`) when present, else model name. Subtitle in tab content shows `via <model>` when persona is active.

**`components/Stage2.jsx`**
- Tab view of RAW evaluation text from each member.
- `deAnonymizeText()` replaces `Response X` labels with `**<persona/model name>**` for human-readable display. The LLM only ever saw the anonymized labels.
- "Extracted Ranking" section shows the parsed ranking list (transparency for users to validate parsing). Kept from Karpathy's original by design.
- "Aggregate Rankings (Street Cred)" shows average rank across all peer evaluations.

**`components/Stage3.jsx`**
- Final synthesized answer from Chairman.
- Green-tinted background (#0d2818 in dark mode) to highlight the conclusion.

**Styling (`*.css`)**
- **Dark mode theme** (GitHub-dark-inspired palette). Karpathy's original was light mode; the fork inverts.
- Primary background: `#0d1117`
- Surface background: `#161b22`
- Borders: `#30363d`
- Primary text: `#c9d1d9`; secondary: `#8b949e`; tertiary: `#6e7681`
- Accent (blue): `#58a6ff`
- Aggregate Rankings highlight: `#0e1a2e` background, `#1f3a5f` border
- Stage 3 highlight: `#0d2818` background, `#1a4a2a` border (subtle green for the conclusion)
- Code blocks: `#1c2128` background

## Key Design Decisions

### Three-mode orchestration

`get_council_members()` returns different member lists based on mode. Stage 1 honors the mode. Stages 2 and 3 derive their work from stage1's output, so they're mode-agnostic.

The mode override flows: UI dropdown → `App.jsx` mode state → `api.sendMessageStream(..., mode, ...)` → `SendMessageRequest.mode` → `run_full_council(mode=...)` → `get_council_members(mode=...)`.

The model override flows similarly but only applies meaningfully in `persona` mode (overrides `PERSONA_MODEL` + `CHAIRMAN_MODEL` + `TITLE_MODEL`). In `model` and `hybrid` modes the configured `COUNCIL_MODELS` and `PERSONA_MODEL_MAP` are used.

### Provider routing

The router prefers direct provider APIs when keys are set. Falls back to OpenRouter for unsupported prefixes or missing keys. Users can pay only one provider (their existing key) and run `persona` mode without OpenRouter at all. This is the fork's core architectural commitment.

### Stage 2 anonymization (and its limit)

Strict label anonymization: `Response A`, `Response B`, etc. The label-to-member mapping never leaves backend memory.

**Known limit:** In `persona` mode, the same underlying LLM writes all N responses (each under a different persona system prompt). The model can sometimes recognize its own writing style even without a label. This is a fundamental tradeoff of single-LLM-multi-persona. Karpathy's original (different model architectures) doesn't have this issue. Worth mentioning if a user is making decisions where Stage 2 bias matters.

### De-anonymization is frontend-only

The backend returns anonymized text. `Stage2.jsx::deAnonymizeText()` rewrites labels to persona names in bold using the `label_to_member` mapping returned alongside the raw stage2 data. This means raw LLM output is always anonymized; the UI just renders it more readably.

### Error Handling Philosophy

- Continue with successful responses if some members fail (graceful degradation)
- Never fail the entire request due to single member failure
- All provider errors are captured in `providers.router.last_errors` and surfaced to the UI when Stage 3 (Chairman) fails
- Errors include HTTP status + body, timeout details, or exception type — enough to diagnose without backend log access

### UI/UX Transparency

- All raw outputs are inspectable via tabs
- Parsed rankings shown below raw text for validation (Extracted Ranking section)
- Mode and model badges on assistant messages so users see which configuration ran
- Provider warning banner when no API keys configured (blocks submission with actionable instructions)

## Important Implementation Details

### Relative Imports

All backend modules use relative imports (e.g., `from .config import ...`). Run as `python -m backend.main` from project root.

### Port Configuration
- Backend: 8001
- Frontend: 5173 (Vite default)

### Per-request overrides

`SendMessageRequest` accepts `mode: Optional[str]` and `model: Optional[str]`. If unset, backend uses config defaults. This means the API is usable from scripts without UI involvement — the UI is just one client.

### Provider routing summary

| Prefix | Direct provider | Fallback |
|---|---|---|
| `anthropic/` | `ANTHROPIC_API_KEY` → Anthropic API | OpenRouter |
| `openai/` | `OPENAI_API_KEY` → OpenAI API | OpenRouter |
| `google/` or `gemini/` | `GOOGLE_API_KEY` (or `GEMINI_API_KEY`) → Gemini API | OpenRouter |
| `xai/`, `deepseek/`, etc. | (no direct integration) | OpenRouter only |

If no key matches for a model, `query_model` returns None with an error recorded in `last_errors`.

## Common Gotchas

1. **Module Import Errors**: Always run backend as `python -m backend.main` from project root, not from backend directory
2. **CORS Issues**: Frontend must match allowed origins in `main.py` CORS middleware
3. **Ranking Parse Failures**: If models don't follow the `FINAL RANKING:` format, fallback regex extracts any "Response X" patterns in order
4. **No API keys configured**: UI shows a provider warning banner and disables submission. Backend's `/api/providers` returns empty `available_models`.
5. **Model identifier with period vs hyphen** (Anthropic): Anthropic's native API uses hyphens (`claude-sonnet-4-5`). OpenRouter slugs sometimes use periods (`claude-sonnet-4.5`). Use hyphens for direct provider access.

## Future Enhancement Ideas

- Provider-direct support for xAI, DeepSeek, Mistral (currently OpenRouter-only)
- Per-persona prompt customization in the UI
- Stage 2 toggle to show raw LLM output (anonymized labels) for transparency demos
- Streaming token-by-token within each stage (currently streams stage-by-stage)
- Export conversations to markdown/PDF
- Cost estimation per provider before running
- Persona presets (e.g., "Strategy Board", "Engineering Review", "Editorial Council")

## Testing Notes

Use the `/api/providers` endpoint to verify provider configuration before running the full council:

```bash
curl http://localhost:8001/api/providers
```

Should return which keys are recognized and which models are usable.

## Data Flow Summary

```
User submits in UI with mode + model selection
    ↓
POST /api/conversations/{id}/message/stream with {content, mode, model}
    ↓
Stage 1: get_council_members(mode, model) → parallel queries via provider router
    ↓
Stage 2: anonymize → parallel ranking queries → parsed rankings
    ↓
Aggregate rankings calculated
    ↓
Stage 3: Chairman synthesis with full context
    ↓
SSE stream: stage1_complete → stage2_complete → stage3_complete → complete
    ↓
Frontend renders each stage as it arrives; de-anonymizes Stage 2 for display
```

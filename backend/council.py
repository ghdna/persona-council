"""3-stage Persona Council orchestration.

Three modes:
- "model": Karpathy's original - N models, no personas
- "persona": Single model with N personas (one model called N times with different system prompts)
- "hybrid": N models with personas (each persona assigned to a specific model)

Mode and model can be overridden per request (from the UI) — they default to config values.
"""

import asyncio
from typing import List, Dict, Any, Tuple, Optional
from .providers import query_model, last_errors
from .config import (
    MODE as DEFAULT_MODE,
    COUNCIL_MODELS, PERSONA_MODEL, PERSONAS, PERSONA_MODEL_MAP,
    CHAIRMAN_MODEL, CHAIRMAN_PERSONA, PERSONAS_DIR, TITLE_MODEL,
)


def load_persona(persona_name: str) -> str:
    """Load persona prompt from markdown file."""
    persona_file = PERSONAS_DIR / f"{persona_name}.md"
    if not persona_file.exists():
        raise FileNotFoundError(f"Persona file not found: {persona_file}")
    return persona_file.read_text()


def get_council_members(
    mode: Optional[str] = None,
    persona_model_override: Optional[str] = None,
) -> List[Dict[str, Optional[str]]]:
    """Return council members based on configured mode (or per-request override).

    Each member is a dict with:
    - member_id: unique identifier (persona name or model name)
    - model: the model identifier to use
    - persona: persona name if applicable, else None

    In `persona` mode, persona_model_override (if provided) replaces PERSONA_MODEL.
    """
    actual_mode = mode or DEFAULT_MODE
    actual_persona_model = persona_model_override or PERSONA_MODEL

    if actual_mode == "model":
        return [
            {"member_id": model, "model": model, "persona": None}
            for model in COUNCIL_MODELS
        ]
    elif actual_mode == "persona":
        return [
            {"member_id": persona, "model": actual_persona_model, "persona": persona}
            for persona in PERSONAS
        ]
    elif actual_mode == "hybrid":
        return [
            {
                "member_id": persona,
                "model": PERSONA_MODEL_MAP.get(persona, actual_persona_model),
                "persona": persona,
            }
            for persona in PERSONAS
        ]
    else:
        raise ValueError(f"Unknown MODE: {actual_mode}. Must be 'model', 'persona', or 'hybrid'.")


def build_messages(user_content: str, persona: Optional[str]) -> List[Dict[str, str]]:
    """Build messages array, including persona system prompt if specified."""
    messages = []
    if persona:
        persona_prompt = load_persona(persona)
        messages.append({"role": "system", "content": persona_prompt})
    messages.append({"role": "user", "content": user_content})
    return messages


async def query_members_parallel(
    members: List[Dict],
    user_content: str
) -> List[Optional[Dict[str, Any]]]:
    """Query all council members in parallel with their persona-bound messages."""
    tasks = [
        query_model(member["model"], build_messages(user_content, member["persona"]))
        for member in members
    ]
    return await asyncio.gather(*tasks)


async def stage1_collect_responses(
    user_query: str,
    mode: Optional[str] = None,
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Stage 1: Collect responses from each council member."""
    members = get_council_members(mode=mode, persona_model_override=model)
    responses = await query_members_parallel(members, user_query)

    stage1_results = []
    for member, response in zip(members, responses):
        if response is not None:
            stage1_results.append({
                "member_id": member["member_id"],
                "model": member["model"],
                "persona": member["persona"],
                "response": response.get('content', '')
            })

    return stage1_results


def format_member_display(member_id: str) -> str:
    """Convert a member_id (persona kebab-case or provider/model) to a readable name."""
    if not member_id:
        return ''
    if '/' in member_id:
        return member_id.split('/')[-1]
    return ' '.join(w.capitalize() for w in member_id.split('-'))


def deanonymize_ranking_text(text: str, label_to_member: Dict[str, str], bold: bool = True) -> str:
    """Replace 'Response A/B/C' labels with the actual member display names.

    bold=True wraps the name in markdown bold (**Name**) for UI rendering.
    bold=False uses plain text (for LLM consumption).
    """
    if not label_to_member or not text:
        return text
    result = text
    # Sort labels by length descending so 'Response AA' would be replaced before 'Response A'
    for label in sorted(label_to_member.keys(), key=len, reverse=True):
        member_id = label_to_member[label]
        name = format_member_display(member_id)
        replacement = f"**{name}**" if bold else name
        result = result.replace(label, replacement)
    return result


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Stage 2: Each member ranks the anonymized responses.

    Uses the same model+persona pairs from stage1_results, so mode/model is implicit.
    The raw ranking text (with 'Response A/B/C' labels) is preserved in `ranking`.
    A display-ready version (with persona names in bold) is added as `ranking_display`.
    """
    labels = [chr(65 + i) for i in range(len(stage1_results))]
    label_to_member = {
        f"Response {label}": result['member_id']
        for label, result in zip(labels, stage1_results)
    }

    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    members_for_ranking = [
        {"member_id": r["member_id"], "model": r["model"], "persona": r["persona"]}
        for r in stage1_results
    ]

    responses = await query_members_parallel(members_for_ranking, ranking_prompt)

    stage2_results = []
    for member, response in zip(members_for_ranking, responses):
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            # Pre-compute display-ready persona names for the parsed ranking list.
            # E.g., ["Response A", "Response C", ...] -> ["Contrarian", "Expansionist", ...]
            parsed_display = [
                format_member_display(label_to_member.get(label, label)) or label
                for label in parsed
            ]
            stage2_results.append({
                "member_id": member["member_id"],
                "model": member["model"],
                "persona": member["persona"],
                "ranking": full_text,
                "ranking_display": deanonymize_ranking_text(full_text, label_to_member, bold=True),
                "parsed_ranking": parsed,
                "parsed_ranking_display": parsed_display,
            })

    return stage2_results, label_to_member


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    label_to_member: Dict[str, str],
    chairman_model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Stage 3: Chairman synthesizes final response.

    The Chairman receives the rankings with anonymized labels (Response A, B, C)
    REPLACED by the actual member names. The anonymization was needed only during
    Stage 2 ranking to prevent bias; by Stage 3 the Chairman should see who said what.
    """
    actual_chairman = chairman_model_override or CHAIRMAN_MODEL

    def format_member_label(result):
        if result.get('persona'):
            return f"{result['persona'].replace('-', ' ').title()} (via {result['model']})"
        return result['model']

    stage1_text = "\n\n".join([
        f"Member: {format_member_label(result)}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    # Strip anonymization labels from ranking text before sending to Chairman (no markdown bold)
    stage2_text = "\n\n".join([
        f"Member: {format_member_label(result)}\nRanking: {deanonymize_ranking_text(result['ranking'], label_to_member, bold=False)}"
        for result in stage2_results
    ])

    chairman_user_prompt = f"""You are the Chairman of the council. Multiple advisors have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom."""

    messages = build_messages(chairman_user_prompt, CHAIRMAN_PERSONA)
    response = await query_model(actual_chairman, messages)

    if response is None:
        error_detail = last_errors.get(actual_chairman, "no detail captured")
        return {
            "model": actual_chairman,
            "persona": CHAIRMAN_PERSONA,
            "response": (
                f"**Chairman synthesis failed.**\n\n"
                f"Model: `{actual_chairman}`\n\n"
                f"Error: `{error_detail}`\n\n"
                f"Common causes:\n"
                f"- Provider API key missing for this model's prefix\n"
                f"- Model identifier not recognized by the provider\n"
                f"- Rate limiting (try again in a moment)\n"
                f"- Insufficient credits\n\n"
                f"Check the backend terminal for the full error trace."
            )
        }

    return {
        "model": actual_chairman,
        "persona": CHAIRMAN_PERSONA,
        "response": response.get('content', '')
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """Parse the FINAL RANKING section from a model's response."""
    import re

    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_member: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Calculate aggregate rankings across all council members."""
    from collections import defaultdict

    member_positions = defaultdict(list)

    for ranking in stage2_results:
        parsed_ranking = parse_ranking_from_text(ranking['ranking'])
        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_member:
                member_name = label_to_member[label]
                member_positions[member_name].append(position)

    aggregate = []
    for member, positions in member_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "member_id": member,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    aggregate.sort(key=lambda x: x['average_rank'])
    return aggregate


async def generate_conversation_title(
    user_query: str,
    title_model_override: Optional[str] = None,
) -> str:
    """Generate a short title for a conversation."""
    actual_title_model = title_model_override or TITLE_MODEL

    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]
    response = await query_model(actual_title_model, messages, timeout=30.0)

    if response is None:
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()
    title = title.strip('"\'')

    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(
    user_query: str,
    mode: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[List, List, Dict, Dict]:
    """Run the complete 3-stage council process."""
    stage1_results = await stage1_collect_responses(user_query, mode=mode, model=model)

    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All council members failed to respond. Please try again."
        }, {}

    stage2_results, label_to_member = await stage2_collect_rankings(user_query, stage1_results)
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_member)
    stage3_result = await stage3_synthesize_final(
        user_query, stage1_results, stage2_results, label_to_member,
        chairman_model_override=model,
    )

    metadata = {
        "mode": mode or DEFAULT_MODE,
        "model": model,
        "label_to_member": label_to_member,
        "label_to_model": label_to_member,  # backward-compat alias
        "aggregate_rankings": aggregate_rankings,
    }

    return stage1_results, stage2_results, stage3_result, metadata

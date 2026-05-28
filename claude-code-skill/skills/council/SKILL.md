---
name: council
description: |
  Five-persona council with Chairman synthesis on any decision or draft. Single-LLM variant
  of Andrej Karpathy's llm-council architecture, using persona-bound subagents for isolation.
  Stage 1: parallel isolated takes. Stage 2: anonymized peer review. Stage 3: Chairman call.
license: MIT
---

# Persona Council Skill

Multi-persona council pattern for solo decision-making in Claude Code. One LLM, multiple persona-bound subagents, three-stage flow.

Persona files are stored at `personas/` in the workspace root (shared with the web app variant).

## When to Use

User types `/council <input>` for decisions where being wrong has real cost:
- Career moves
- Strategic bets
- Drafts pre-publish (high-stakes audience)
- Architectural / technical calls
- Hiring or comp decisions
- Pricing / scoping calls

Default Claude is fine for chat questions. Use the council when the decision warrants the discipline.

## Three-Stage Process

### Stage 1: Parallel Persona Takes (5 isolated subagents)

Read all five persona prompts from the workspace root:
- `personas/contrarian.md`
- `personas/first-principles-skeptic.md`
- `personas/expansionist.md`
- `personas/outsider.md`
- `personas/executor.md`

Spawn five Agent subagents **in a single message with five Agent tool calls** (parallel execution). For each:
- `subagent_type`: `general-purpose`
- `description`: `<Persona> take` (e.g., "Contrarian take")
- `prompt`: The full persona file content, followed by:
  ```
  User's input:

  <user input verbatim>

  Return only your take per your instructions above. No preamble, no caveats. 3-5 sentences.
  ```

Collect all five takes verbatim.

### Stage 2: Anonymized Peer Review

Assign random labels (Advisor A, B, C, D, E) to the five takes. Track the mapping internally; do not reveal it to the subagents.

Spawn five Agent subagents in parallel. For each persona, include their own take labeled correctly + the four other takes anonymized:
- `subagent_type`: `general-purpose`
- `description`: `Peer review by <persona>`
- `prompt`:
  ```
  You are <persona name>. You produced this take:

  <persona's own take>

  Four other advisors also weighed in. Their takes are below, anonymized. Rank them 1 (strongest) to 4 (weakest) on accuracy and insight. One sentence justification per ranking.

  Advisor A: <anonymized take>
  Advisor B: <anonymized take>
  Advisor C: <anonymized take>
  Advisor D: <anonymized take>

  Format: "1. Advisor X — <one sentence>. 2. Advisor Y — <one sentence>." etc.
  ```

Collect all five rankings.

### Stage 3: Chairman Synthesis

Read `personas/chairman.md`.

Spawn one Agent subagent:
- `subagent_type`: `general-purpose`
- `description`: `Chairman synthesis`
- `prompt`: The Chairman file content, followed by:
  ```
  Five original takes:

  The Contrarian: <take>
  The First-Principles Skeptic: <take>
  The Expansionist: <take>
  The Outsider: <take>
  The Executor: <take>

  Peer rankings (de-anonymized):

  The Contrarian's ranking: <rankings>
  The First-Principles Skeptic's ranking: <rankings>
  The Expansionist's ranking: <rankings>
  The Outsider's ranking: <rankings>
  The Executor's ranking: <rankings>

  Produce the synthesis per your instructions above.
  ```

## Output to User

Present the full council:

```
## Stage 1: First Opinions

**The Contrarian:** <take>

**The First-Principles Skeptic:** <take>

**The Expansionist:** <take>

**The Outsider:** <take>

**The Executor:** <take>

---

## Stage 2: Peer Review (top-ranked across council)

<2-3 sentences naming which takes were most consistently top-ranked and why>

---

## Stage 3: Chairman Synthesis

<Chairman's structured output verbatim>
```

## Rules

- **Stage 1 isolation is non-negotiable.** Each persona MUST be a separate Agent invocation. No shared context.
- **Stage 2 anonymization is non-negotiable.** Personas must not know which advisor wrote which take.
- **Chairman MUST commit.** No hedging, no "it depends," no "you might want to consider." A real recommendation with a real next step.

## Credits

Architecture extended from Andrej Karpathy's [llm-council](https://github.com/karpathy/llm-council).

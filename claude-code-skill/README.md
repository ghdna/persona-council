# Persona Council — Claude Code Skill

A slash-command version of the Persona Council pattern for [Claude Code](https://claude.com/claude-code). Type `/council <your decision>` to run a five-persona council with Chairman synthesis inside any Claude Code session.

This is the lightweight variant of the full [Persona Council](../README.md) web app. No API keys, no setup beyond copying the skill files and persona prompts into your Claude Code workspace.

## Install

From the persona-council repo root:

```bash
cp -r claude-code-skill/.claude /path/to/your-workspace/
cp -r claude-code-skill/skills/council /path/to/your-workspace/skills/
cp -r personas /path/to/your-workspace/
```

Three copies: the slash command, the orchestrator skill, and the persona prompts (which are shared with the web app, kept at the workspace root).

## Use

In your Claude Code session:

```
/council Should I accept the role at X?
/council Review this LinkedIn draft: <paste>
/council Architecture: Postgres or DynamoDB for the new service
```

The skill spawns five isolated persona subagents (Contrarian, First-Principles Skeptic, Expansionist, Outsider, Executor), runs anonymized peer review, and synthesizes via a Chairman.

## Architecture vs. the web app

| | Web app version | Claude Code skill |
|---|---|---|
| Setup | OpenRouter API key + Python deps + npm | Copy three directories |
| Front-end | Karpathy's React UI forked | Claude Code chat |
| Models | OpenAI / Anthropic / Gemini / Grok via OpenRouter | Whatever model your Claude Code session runs |
| Isolation | Separate API calls per persona | Separate Agent subagents per persona |
| Best for | Comparing across models or running multi-mode | Solo decisions inside your existing dev workflow |

Both versions read the same persona markdown files (`personas/*.md` at the workspace/repo root). Edit them once, both versions update.

## Customize

Each persona is its own file in `personas/`. Edit a persona to sharpen its lens, swap in a different role (e.g., a "Legal Skeptic" or "Cost Hawk"), or add new personas of your own.

The orchestrator (`skills/council/SKILL.md`) controls the three-stage flow. Modify it to skip stages, add stages, or change the output format.

## Credits

Architecture extended from [Andrej Karpathy's llm-council](https://github.com/karpathy/llm-council).

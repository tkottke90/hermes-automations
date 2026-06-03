---
name: llm-wiki
description: "Karpathy's LLM Wiki: build/query interlinked markdown KB."
version: 3.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [wiki, knowledge-base, research, notes, markdown]
    category: research
---

# LLM Wiki

Build and maintain a persistent, compounding knowledge base as interlinked markdown files.

## When This Skill Activates

- User asks to create, build, or start a wiki or knowledge base
- User asks to ingest, add, or process a source into their wiki
- User asks a question and an existing wiki is present
- User asks to lint, audit, or health-check their wiki
- User references their wiki, knowledge base, or "notes" in a research context

---

## Step 1 — Resolve the Wiki Path

Always run this first, before anything else:

```bash
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-route.py "<user context or topic>"
```

Output is JSON. Three possible outcomes:

| JSON key | Meaning | Action |
|----------|---------|--------|
| `path` | Resolved wiki path | Proceed to Step 2 |
| `ambiguous` | Two wikis matched equally | Ask user: "Did you mean X or Y wiki?" |
| `no_match` | No wiki matched | Offer to create a new wiki — see `ops/init.md` |

**Environment variables** (set in `~/.hermes/.env`):
- `WIKI_ROOT` — vault-level `wikis/` directory containing multiple wikis (uses registry routing)
- `WIKI_PATH` — single wiki path override (bypasses routing entirely)
- If neither is set, defaults to `~/wiki`

---

## Step 2 — Orient (existing wikis only)

Load the wiki's current state before doing any work:

```bash
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-orient.py "<wiki_path>"
```

This outputs SCHEMA.md + index.md + the last 30 log entries in one formatted block.
Read the output before proceeding. This prevents duplicate pages, missed cross-references,
and schema violations.

For large wikis (100+ pages), also search for the topic before creating anything new:
```bash
grep -r "<topic>" "<wiki_path>" --include="*.md" -l
```

---

## Step 3 — Run the Operation

| What the user wants | Operation file |
|--------------------|---------------|
| Create a new wiki | `ops/init.md` |
| Add a source / URL / note | `ops/ingest.md` |
| Ask a question about the wiki | `ops/query.md` |
| Lint / health-check / audit | `ops/lint.md` |

Wiki architecture reminder:
```
wiki/
├── SCHEMA.md           # conventions, structure rules, tag taxonomy
├── index.md            # content catalog with one-line summaries
├── log.md              # append-only chronological action log
├── raw/                # immutable source material (never modify)
├── entities/           # pages for people, orgs, products, models
├── concepts/           # pages for topics, techniques, ideas
├── comparisons/        # side-by-side analyses
└── queries/            # filed query results worth keeping
```

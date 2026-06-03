# LLM Wiki — Refactored Skill

This is a refactored version of the original `llm-wiki` skill from Hermes Agent. The goal is to reduce
the token overhead loaded per operation by extracting mechanical work into Python scripts and splitting
the monolithic SKILL.md into focused per-operation documents.

---

## Problem: The Original Skill

The original `~/.hermes/skills/research/llm-wiki/SKILL.md` is **845 lines / ~43KB**. At ~3 chars/token
for dense markdown, that loads **~14–18k tokens** into every wiki-adjacent context window — regardless
of whether the session is initializing a wiki, ingesting a source, running a query, or linting.

The overhead is amplified on smaller or local models where every token of mechanical instruction
increases error risk and burns context that could hold actual wiki content.

---

## Token Breakdown by Section (Original)

| Section | Lines | Est. Tokens | Mechanical? |
|---------|-------|-------------|-------------|
| Wiki location + routing | 70 | ~400 | ~80% code |
| Multi-wiki routing algorithm | 50 | ~300 | 100% code |
| Orientation on resume | 30 | ~150 | 100% code |
| Initialize new wiki | 120 | ~700 | 90% code (templates) |
| SCHEMA.md template | 110 | ~600 | code-generated |
| index.md + log.md templates | 40 | ~200 | code-generated |
| Core op: Ingest | 100 | ~600 | 60% code |
| sha256 inline code block | 15 | ~80 | 100% code |
| Core op: Query | 35 | ~180 | ~20% code |
| Core op: Lint | 70 | ~400 | ~90% code |
| Working patterns | 60 | ~300 | ~50% code |
| Pitfalls | 150 | ~800 | distillable |
| Obsidian / homelab / integration | 120 | ~600 | separate concern |
| Game design domain pattern | 35 | ~180 | sub-skill |

**Three biggest token spends that are not LLM work:**
1. **Templates** (SCHEMA.md, index.md, log.md) — ~800 tokens of boilerplate read and reproduced on every init
2. **Lint check descriptions** — ~400 tokens describing algorithmic checks run by the LLM by hand
3. **Pitfalls** — ~800 tokens of accumulated edge cases, most irrelevant to any given operation

---

## Division of Work: What Belongs in Code vs. LLM

| Operation | Was LLM doing | Now |
|-----------|--------------|-----|
| Route to correct wiki | Parse registry table, apply scoring algorithm | `wiki-route.py` → JSON path |
| Orient at session start | Read 3 files, summarize | `wiki-orient.py` → formatted context block |
| Initialize wiki | Write templates from memory | `wiki-init.py` → creates structure; LLM customizes domain/tags only |
| Ingest: sha256 | Run inline Python from memory | `wiki-ingest-prep.py` → hash + drift detection |
| Ingest: re-ingest detection | Search raw/ for matching URL | `wiki-ingest-prep.py` → `is_new`, `drift` |
| Ingest: nav update | Append to index.md + log.md | `wiki-nav-update.py` → mechanical writes |
| Lint: all 12 checks | Scan files with pseudocode guidance | `wiki-lint.py` → structured JSON report |

---

## Structure

```
llm-wiki/
├── README.md               ← this file
├── SKILL.md                ← lean dispatch (~300 tokens): route + orient + op pointer
├── ops/
│   ├── init.md             ← new wiki workflow (~250 tokens)
│   ├── ingest.md           ← ingest workflow (~400 tokens, judgment-heavy parts only)
│   ├── query.md            ← query workflow (~150 tokens)
│   └── lint.md             ← lint workflow (~80 tokens: run script, interpret output)
└── scripts/
    ├── wiki-route.py       ← resolve wiki path from WIKI_ROOT registry
    ├── wiki-orient.py      ← read + format SCHEMA/index/log for LLM context
    ├── wiki-init.py        ← create directory structure + skeleton files
    ├── wiki-ingest-prep.py ← sha256, drift detection, existing page lookup
    ├── wiki-nav-update.py  ← append to index.md + log.md
    └── wiki-lint.py        ← run all 12 lint checks → structured JSON report
```

---

## Expected Token Reduction per Operation

| Session type | Original | After refactor |
|--------------|----------|---------------|
| Routing only | ~16k | ~300 (script call) |
| Init session | ~16k | ~800 (SKILL.md + ops/init.md) |
| Ingest session | ~16k | ~1,500 (SKILL.md + ops/ingest.md + orient output) |
| Query session | ~16k | ~800 (SKILL.md + ops/query.md + orient output) |
| Lint session | ~16k | ~400 (SKILL.md + ops/lint.md + script output) |

The orient output (SCHEMA + index + recent log) is dynamic — it scales with wiki size but
is actual wiki content rather than instruction overhead.

---

## What Stays in the Original Skill

The original `~/.hermes/skills/research/llm-wiki/SKILL.md` is left intact. It remains the
fallback for full-featured contexts (large models with ample context windows) and is the
canonical reference for any behavior not covered here.

This refactored version is intended for use with smaller/local models or sessions where
context budget is constrained.

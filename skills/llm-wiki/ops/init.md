# Op: Initialize a New Wiki

## When to use
The wiki-route script returned `no_match`, or the user explicitly asked to create a new wiki.

---

## Step 1 — Ask domain focus (before writing anything)

Ask one targeted question before initializing. The answer shapes the tag taxonomy meaningfully:

> "What's the primary focus of this wiki? For example: infrastructure & services, research papers,
> project documentation, or something else?"

Don't proceed to init until you have a specific domain answer.

---

## Step 2 — Run wiki-init.py

```bash
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-init.py \
  "<wiki_path>" \
  --name "<short-slug>" \
  --domain "<domain description from user>" \
  --tags "<comma,separated,tags>" \
  [--register "$WIKI_ROOT"]
```

This creates the full directory structure and skeleton files:
- `SCHEMA.md` — skeleton with domain filled in, tag taxonomy left empty
- `index.md` — empty sectioned catalog with today's date
- `log.md` — creation entry
- All subdirectories (`raw/`, `entities/`, `concepts/`, `comparisons/`, `queries/`)
- Registers in `$WIKI_ROOT/readme.md` and adds a routing note (if `--register` is provided)

---

## Step 3 — Customize SCHEMA.md

The script writes a skeleton. You must fill in the **Tag Taxonomy** section.

Read the generated SCHEMA.md, then rewrite the `## Tag Taxonomy` section with 10–20 tags
appropriate to the domain. Structure them in 3–5 named groups. Example for infrastructure:

```
- Hosts: host, vm, container, server
- Services: service, proxy, monitoring, auth, storage
- Network: dns, vlan, subnet, firewall
- Meta: runbook, comparison, incident, config
```

Rule: every tag on a wiki page must appear in this taxonomy. Tags not listed here are invalid.
Add new tags to the taxonomy **before** using them on pages.

---

## Step 4 — Seed from known context (if applicable)

If the current conversation or memory already contains domain knowledge (IPs, services, tools,
concepts), proactively create seed pages rather than leaving the wiki empty.

- Entity pages for known hosts, services, tools
- Concept pages for recurring patterns or gotchas already discussed

An empty scaffold is not useful. A seeded wiki is immediately useful.

---

## Step 5 — Confirm and suggest first ingest

Tell the user:
- Wiki created at `<path>`
- Domain + tags configured
- Any pages seeded
- Suggested first sources to ingest

---

## Pitfalls

- **Ask domain focus first** — a generic wiki initialized without a specific focus gets a
  useless tag taxonomy that fits nothing well.
- **Add a disambiguation routing note** — when registering in `WIKI_ROOT`, the script adds
  a routing note automatically. If creating manually, add one. Without it, the router may
  fail to match future queries to this wiki when domain overlaps with another wiki's tags.

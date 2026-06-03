# Op: Ingest a Source

Orientation (SKILL.md Step 2) must be complete before starting here.

---

## Step 1 — Pre-flight: run wiki-ingest-prep.py

```bash
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-ingest-prep.py \
  "<wiki_path>" \
  [--file "/path/to/source.md"] \
  [--url "https://example.com/article"] \
  [--keywords "topic1,topic2,topic3"]
```

Output JSON fields:
- `sha256` — hash of the source body (use this in raw/ frontmatter)
- `is_new` / `drift` — whether this URL was seen before and whether content changed
- `existing_raw` — path to prior raw file if re-ingest
- `existing_pages` — wiki pages already covering related topics
- `suggested_raw_path` — where to save the raw file

**If `drift: true`**: the source content changed since last ingest. Proceed as a new ingest
but note the drift in the raw/ frontmatter and log entry.

**If `is_new: false` and `drift: false`**: source unchanged. Skip unless user explicitly wants
a re-ingest.

**User's Intake folder**: `/Users/thomaskottke/Nextcloud/Documents/Vault_v2/Intake/` — check
here first when the user says "add this note" or references a local .md file.

---

## Step 2 — Capture the raw source

Save to `raw/articles/`, `raw/papers/`, or `raw/transcripts/` depending on type.
Use the `suggested_raw_path` from Step 1, or name descriptively: `raw/articles/topic-YYYY-MM-DD.md`.

For URL sources: use `web_extract` to fetch markdown, then save to raw/.
For local .md files: read the file directly, write a condensed summary to raw/ (strip nav chrome,
iframes, FAQ boilerplate — keep substantive content). The condensed copy is what wiki pages cite.
For pasted text or conversation findings: write directly to raw/ — use `source_url: "conversation:<date>"`.

Add this frontmatter to every raw file:
```yaml
---
source_url: <url or "conversation:YYYY-MM-DD">
ingested: YYYY-MM-DD
sha256: <value from wiki-ingest-prep.py>
---
```

---

## Step 3 — Discuss takeaways (interactive sessions only)

In a live session with the user: briefly surface what's interesting or relevant to their domain
before writing pages. If the user explains *why* they're ingesting a source, capture that framing —
it shapes how the wiki page should be written (their practice, not just a neutral summary).

Skip this step in automated or cron contexts.

---

## Step 4 — Check existing pages

The `existing_pages` field from Step 1 gives you a head start. Also scan `index.md` (already
read during orientation). For large wikis (100+ pages), run an additional search:

```bash
grep -r "<key terms from source>" "<wiki_path>" --include="*.md" -l
```

Knowing what exists is the difference between a growing wiki and a pile of duplicates.

---

## Step 5 — Write or update wiki pages

**Page threshold** (from SCHEMA.md):
- Create a new page when an entity/concept appears in 2+ sources, or is central to this one
- Add to an existing page when the source mentions something already covered
- Don't create a page for passing mentions or minor details

**For new pages:**
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query
tags: [only tags from SCHEMA.md taxonomy]
sources: [raw/articles/source-name.md]
confidence: high | medium | low
---
```

**For existing pages:** add new information, bump `updated:` date, add the source to `sources:`.
If new info contradicts existing content: note both positions with dates, add `contradictions: [page]`
to frontmatter, mark `contested: true`.

**Confidence promotion**: if this source corroborates an existing `medium`-confidence page, bump
it to `high` and add the source to its `sources:` list.

**Provenance markers**: on pages synthesizing 3+ sources, append `^[raw/articles/source.md]` at
the end of paragraphs whose claims trace to a specific source.

**Every page must link to at least 2 other pages via `[[wikilinks]]`.**

---

## Step 6 — Back-link sweep

After creating new pages, find existing pages that *should* link forward to the new ones.
For each: read the page, add a `[[wikilink]]` under its "Related Pages" section, bump `updated:`.

For a brand-new wiki with no existing pages: instead create **stub pages** for every outbound
`[[wikilink]]` that doesn't have a file yet. Stubs need: frontmatter (with `confidence: low`),
`> Stub — needs content`, 2–3 open questions, and a "Related Pages" link back to the spawning page.
Add all stubs to index.md with a `*(stub)*` annotation.

---

## Step 7 — Update navigation

```bash
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-nav-update.py "<wiki_path>" \
  --add "<rel_path>" --summary "<one-line summary>" \
  --log "ingest | <Source Title>" \
  --files "<file1.md>,<file2.md>,..."
```

Run once per new page, or use `--log` alone for updates to existing pages.

---

## Step 8 — Report to user

List every file created or updated. A single source touching 5–15 pages is normal — it's the
compounding effect.

---

## Pitfalls

- **Never modify files in `raw/`** — sources are immutable. Corrections go in wiki pages.
- **sha256: use plain Python `open()`, not `read_file`** — `read_file` returns a paginated dict,
  not a plain string. The ingest-prep script handles this correctly.
- **Frontmatter patch: include surrounding lines** — when patching `updated: YYYY-MM-DD`, include
  the title line above it as context to avoid fuzzy over-match eating adjacent frontmatter fields.
  Safe pattern: `old_string: "title: My Title\ncreated: ...\nupdated: old-date"`
- **Bump `updated:` on every substantive patch** — even adding a single cross-link. Staleness
  detection depends on it.
- **Tags must be in SCHEMA.md taxonomy** — add new tags to SCHEMA.md first, then use them.
- **No YAML comments inside frontmatter** — `#` comments inside `---` blocks corrupt Obsidian
  parsing and break Dataview queries. Put notes in the page body or log.md only.
- **Entity renames require a full sweep** — if an entity page is renamed, search the entire wiki
  for the old name/slug/IP and patch every reference: wikilinks, prose, index.md entry.
- **Docker service ports: document HOST port, not container-internal** — `ports: "32500:5000"`
  means document `32500`, not `5000`.
- **Ask before touching 10+ existing pages** — confirm scope with user first.
- **Out-of-scope sections**: when a source contains content SCHEMA excludes, note it in the raw
  summary file and the log entry. Don't silently drop it.
- **Incomplete source notes**: only create concept pages for complete portions. Note incomplete
  sections at the bottom of the raw file under "Note on Completion".

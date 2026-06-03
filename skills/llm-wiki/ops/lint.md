# Op: Lint / Health-Check the Wiki

No orientation needed — the lint script reads the wiki directly.

---

## Run the lint script

```bash
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-lint.py "<wiki_path>"
# or with WIKI_ROOT for registry sync check:
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-lint.py "<wiki_path>" --wiki-root "$WIKI_ROOT"
# JSON output for structured processing:
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-lint.py "<wiki_path>" --format json
```

The script runs all checks and returns a structured report.

---

## Checks performed

| Check | What it finds |
|-------|--------------|
| Orphan pages | Pages with no inbound `[[wikilinks]]` from other pages |
| Broken wikilinks | `[[links]]` pointing to pages that don't exist |
| Index completeness | Wiki files not listed in index.md |
| Frontmatter validation | Missing required fields; tags not in taxonomy |
| Page size | Pages over 200 lines (candidates for splitting) |
| Tag audit | Tags used on pages that aren't in SCHEMA.md taxonomy |
| Source drift | sha256 mismatch in raw/ files (raw/ was modified, or source URL changed) |
| Log rotation | log.md exceeds 500 entries (rotate to log-YYYY.md) |
| Stale content | Pages with `updated:` > 90 days old |
| Quality signals | Pages with `confidence: low` or `contested: true` |
| Contradictions | Pages with `contradictions:` frontmatter set |
| Registry sync | Wiki subdirs present on disk but missing from WIKI_ROOT registry |

---

## Interpret the report

Present findings to the user grouped by severity:

1. **Broken links** — fix immediately; broken links degrade the knowledge graph
2. **Orphan pages** — add cross-links or merge into related pages
3. **Source drift** — raw/ should be immutable; flag for user review
4. **Contested / contradiction pages** — surface for user resolution
5. **Stale content** — flag for potential re-ingest or archiving
6. **Style / quality issues** — low-confidence pages, missing frontmatter fields, oversized pages

---

## After the report

Append to log.md:
```bash
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-nav-update.py "<wiki_path>" \
  --log "lint | <N> issues found"
```

If log rotation is flagged: rename `log.md` to `log-YYYY.md` and create a fresh `log.md`
with the standard header template.

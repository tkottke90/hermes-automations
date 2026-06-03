#!/usr/bin/env python3
"""
Initialize a new wiki directory structure.

Usage:
    python wiki-init.py /path/to/new-wiki --name "ai-ml" --domain "LLM/AI research"
    python wiki-init.py /path/to/new-wiki --name "homelab" --domain "Servers, networking" \
        --tags "homelab,devops,infra" --register /path/to/wikis

Creates the full directory structure and skeleton files. SCHEMA.md is a skeleton —
the LLM fills in the Tag Taxonomy section before first use.

Exits 1 if the wiki already exists (SCHEMA.md found).
"""
import argparse
import json
import os
import re
import sys
from datetime import date


TODAY = date.today().isoformat()

SCHEMA_SKELETON = """\
# Wiki Schema

## Domain
{domain}

## Conventions
- File names: lowercase, hyphens, no spaces (e.g., `example-topic.md`)
- Every wiki page starts with YAML frontmatter (see below)
- Use `[[wikilinks]]` to link between pages (minimum 2 outbound links per page)
- When updating a page, always bump the `updated` date
- Every new page must be added to `index.md` under the correct section
- Every action must be appended to `log.md`
- On pages synthesizing 3+ sources, append `^[raw/articles/source.md]` at the end
  of paragraphs whose claims trace to a specific source

## Frontmatter
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary
tags: [from taxonomy below]
sources: [raw/articles/source-name.md]
confidence: high | medium | low
contested: true   # optional — set when page has unresolved contradictions
---
```

## Tag Taxonomy
<!-- TODO: Define 10-20 top-level tags for this domain.
     Add new tags here BEFORE using them on pages. Example structure:

     - Category1: tag1, tag2, tag3
     - Category2: tag4, tag5, tag6

     Rule: every tag on a page must appear in this taxonomy.
-->

## Page Thresholds
- **Create a page** when an entity/concept appears in 2+ sources OR is central to one source
- **Add to existing page** when a source mentions something already covered
- **DON'T create a page** for passing mentions, minor details, or out-of-domain content
- **Split a page** when it exceeds ~200 lines — break into sub-topics with cross-links
- **Archive a page** when its content is fully superseded — move to `_archive/`

## Update Policy
When new information conflicts with existing content:
1. Check the dates — newer sources generally supersede older ones
2. If genuinely contradictory, note both positions with dates and sources
3. Mark in frontmatter: `contradictions: [page-name]` and `contested: true`
4. Flag for user review in the lint report
"""

INDEX_TEMPLATE = """\
# Wiki Index

> Content catalog. Every wiki page listed under its type with a one-line summary.
> Read this first to find relevant pages for any query.
> Last updated: {today} | Total pages: 0

## Entities
<!-- Alphabetical within section -->

## Concepts

## Comparisons

## Queries
"""

LOG_TEMPLATE = """\
# Wiki Log

> Chronological record of all wiki actions. Append-only.
> Format: `## [YYYY-MM-DD] action | subject`
> Actions: ingest, update, query, lint, create, archive, delete
> When this file exceeds 500 entries, rotate: rename to log-YYYY.md, start fresh.

## [{today}] create | Wiki initialized
- Domain: {domain}
- Structure created with SCHEMA.md, index.md, log.md
"""


def init_wiki(wiki_path, name, domain, tags, wiki_root=None, dry_run=False):
    schema_path = os.path.join(wiki_path, 'SCHEMA.md')
    if os.path.exists(schema_path):
        return {'error': f'Wiki already exists at {wiki_path} (SCHEMA.md found). Delete it first to re-initialize.'}

    dirs = [
        wiki_path,
        os.path.join(wiki_path, 'raw', 'articles'),
        os.path.join(wiki_path, 'raw', 'papers'),
        os.path.join(wiki_path, 'raw', 'transcripts'),
        os.path.join(wiki_path, 'raw', 'assets'),
        os.path.join(wiki_path, 'entities'),
        os.path.join(wiki_path, 'concepts'),
        os.path.join(wiki_path, 'comparisons'),
        os.path.join(wiki_path, 'queries'),
    ]

    files = {
        schema_path: SCHEMA_SKELETON.format(domain=domain),
        os.path.join(wiki_path, 'index.md'): INDEX_TEMPLATE.format(today=TODAY),
        os.path.join(wiki_path, 'log.md'): LOG_TEMPLATE.format(today=TODAY, domain=domain),
    }

    if dry_run:
        return {'dry_run': True, 'dirs': dirs, 'files': list(files.keys())}

    for d in dirs:
        os.makedirs(d, exist_ok=True)

    for path, content in files.items():
        with open(path, 'w') as f:
            f.write(content)

    result = {
        'wiki_path': wiki_path,
        'files_created': list(files.keys()),
        'next_step': 'Fill in the Tag Taxonomy section of SCHEMA.md before first use.',
    }

    if wiki_root:
        reg_result = register_wiki(wiki_path, name, domain, tags, wiki_root)
        result.update(reg_result)

    return result


def register_wiki(wiki_path, name, domain, tags, wiki_root):
    wiki_root = os.path.expanduser(wiki_root)
    registry_path = os.path.join(wiki_root, 'readme.md')

    try:
        with open(registry_path) as f:
            content = f.read()
    except FileNotFoundError:
        return {'registry_warning': f'Registry not found at {registry_path}'}

    # Compute relative path from vault root (parent of wikis dir)
    vault_root = os.path.dirname(wiki_root.rstrip('/'))
    try:
        rel_path = os.path.relpath(wiki_path, vault_root)
    except ValueError:
        rel_path = wiki_path

    tag_str = tags if tags else 'general'
    new_row = f'| {name} | {rel_path}/ | {domain} | {tag_str} | active |'

    # Insert after the last table row in the Active Wikis section
    table_row_re = re.compile(r'(\|[^\n]+\|\n)(?!\|)', re.DOTALL)
    m = table_row_re.search(content)
    if m:
        content = content[:m.end()] + new_row + '\n' + content[m.end():]
    else:
        content += f'\n## Active Wikis\n\n| Name | Path | Domain | Tags | Status |\n|---|---|---|---|---|\n{new_row}\n'

    # Add routing note
    routing_line = f'- Anything specifically about {domain} → {name}'
    if '## Routing Notes' in content:
        content = content.replace('## Routing Notes\n', f'## Routing Notes\n{routing_line}\n', 1)
    else:
        content += f'\n## Routing Notes\n{routing_line}\n'

    with open(registry_path, 'w') as f:
        f.write(content)

    return {'registered_in': registry_path, 'routing_note_added': routing_line}


def main():
    parser = argparse.ArgumentParser(description='Initialize a new wiki directory')
    parser.add_argument('wiki_path', help='Path for the new wiki')
    parser.add_argument('--name', required=True, help='Short slug (e.g. ai-ml)')
    parser.add_argument('--domain', required=True, help='Domain description')
    parser.add_argument('--tags', default='', help='Comma-separated tags for the registry')
    parser.add_argument('--register', metavar='WIKI_ROOT', help='Register in WIKI_ROOT/readme.md')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be created without writing')
    args = parser.parse_args()

    wiki_root = args.register or os.environ.get('WIKI_ROOT', '')
    result = init_wiki(
        os.path.expanduser(args.wiki_path),
        args.name,
        args.domain,
        args.tags,
        wiki_root=wiki_root or None,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    if 'error' in result:
        sys.exit(1)


if __name__ == '__main__':
    main()

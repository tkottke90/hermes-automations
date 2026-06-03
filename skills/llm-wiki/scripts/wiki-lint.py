#!/usr/bin/env python3
"""
Run all lint checks on a wiki directory.

Usage:
    python wiki-lint.py /path/to/wiki
    python wiki-lint.py /path/to/wiki --format json
    python wiki-lint.py /path/to/wiki --wiki-root /path/to/wikis
    python wiki-lint.py /path/to/wiki --check orphans broken_links page_size

Checks performed:
    orphans          - Pages with no inbound [[wikilinks]]
    broken_links     - [[links]] pointing to non-existent pages
    index            - Wiki files not listed in index.md
    frontmatter      - Missing required fields or tags not in SCHEMA.md taxonomy
    page_size        - Pages over 200 lines
    tag_audit        - Tags used that aren't in SCHEMA.md taxonomy
    source_drift     - sha256 mismatch in raw/ files
    log_rotation     - log.md exceeds 500 entries
    stale            - Pages with updated: > 90 days ago
    quality          - contested pages, low-confidence pages
    registry_sync    - Wiki dirs on disk missing from WIKI_ROOT registry

Exit codes:
    0  - no issues
    1  - issues found
    2  - error (wiki not found, etc.)
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta


WIKI_SUBDIRS = ('entities', 'concepts', 'comparisons', 'queries')
REQUIRED_FRONTMATTER = {'title', 'created', 'updated', 'type', 'tags', 'sources'}
FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---', re.DOTALL)
WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')
ALL_CHECKS = ['orphans', 'broken_links', 'index', 'frontmatter', 'page_size',
              'tag_audit', 'source_drift', 'log_rotation', 'stale', 'quality', 'registry_sync']


# ── Helpers ──────────────────────────────────────────────────────────────────

def parse_frontmatter(content):
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split('\n'):
        if ':' in line and not line.strip().startswith('#'):
            key, _, val = line.partition(':')
            fm[key.strip()] = val.strip()
    return fm


def extract_body(content):
    lines = content.split('\n')
    dashes = 0
    for i, line in enumerate(lines):
        if line.strip() == '---':
            dashes += 1
            if dashes == 2:
                return '\n'.join(lines[i + 1:])
    return content


def read_page(wiki_path, rel_path):
    try:
        with open(os.path.join(wiki_path, rel_path)) as f:
            return f.read()
    except OSError:
        return ''


def get_wiki_pages(wiki_path):
    pages = []
    for subdir in WIKI_SUBDIRS:
        d = os.path.join(wiki_path, subdir)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith('.md') and not f.startswith('_'):
                    pages.append(f'{subdir}/{f}')
    return pages


def normalize_link(link_text):
    """Strip alias and .md suffix from a wikilink target."""
    return link_text.split('|')[0].strip().removesuffix('.md')


# ── Checks ───────────────────────────────────────────────────────────────────

def check_orphans(wiki_path, pages):
    page_stems = {p.removesuffix('.md'): p for p in pages}
    page_basenames = {os.path.basename(p).removesuffix('.md'): p for p in pages}

    inbound = defaultdict(set)
    for page in pages:
        content = read_page(wiki_path, page)
        for link in WIKILINK_RE.findall(content):
            target = normalize_link(link)
            # Try full path match, then basename match
            resolved = page_stems.get(target) or page_basenames.get(target)
            if resolved and resolved != page:
                inbound[resolved].add(page)

    return [p for p in pages if not inbound[p]]


def check_broken_links(wiki_path, pages):
    page_stems = set(p.removesuffix('.md') for p in pages)
    page_basenames = set(os.path.basename(p).removesuffix('.md') for p in pages)

    broken = []
    for page in pages:
        content = read_page(wiki_path, page)
        for link in WIKILINK_RE.findall(content):
            target = normalize_link(link)
            if target not in page_stems and target not in page_basenames:
                broken.append({'page': page, 'link': f'[[{link}]]'})
    return broken


def check_index_completeness(wiki_path, pages):
    index_path = os.path.join(wiki_path, 'index.md')
    try:
        with open(index_path) as f:
            index_content = f.read()
    except FileNotFoundError:
        return [{'error': 'index.md not found'}]

    missing = []
    for page in pages:
        stem = os.path.basename(page).removesuffix('.md')
        if f'[[{stem}' not in index_content and f'[[{page}' not in index_content:
            missing.append(page)
    return missing


def check_frontmatter(wiki_path, pages):
    issues = []
    for page in pages:
        content = read_page(wiki_path, page)
        if not content.startswith('---'):
            issues.append({'page': page, 'issue': 'missing frontmatter'})
            continue
        fm = parse_frontmatter(content)
        missing = sorted(REQUIRED_FRONTMATTER - set(fm.keys()))
        if missing:
            issues.append({'page': page, 'issue': 'missing fields', 'fields': missing})
    return issues


def check_tag_audit(wiki_path, pages):
    schema_path = os.path.join(wiki_path, 'SCHEMA.md')
    try:
        with open(schema_path) as f:
            schema = f.read()
    except FileNotFoundError:
        return [{'error': 'SCHEMA.md not found — cannot validate tags'}]

    taxonomy_m = re.search(r'## Tag Taxonomy(.*?)(?=\n##|\Z)', schema, re.DOTALL)
    if not taxonomy_m:
        return []

    known_tags = set(re.findall(r'\b([a-z][a-z0-9-]{1,})\b', taxonomy_m.group(1).lower()))
    # Remove common prose words that appear in example comments
    known_tags -= {'the', 'and', 'for', 'use', 'add', 'new', 'tag', 'here', 'tags', 'first'}

    issues = []
    for page in pages:
        content = read_page(wiki_path, page)
        fm = parse_frontmatter(content)
        tags_raw = fm.get('tags', '')
        # Parse YAML list or comma string
        tags = re.findall(r'\b([a-z][a-z0-9-]+)\b', tags_raw.lower())
        unknown = [t for t in tags if t not in known_tags and len(t) > 2]
        if unknown:
            issues.append({'page': page, 'unknown_tags': unknown})
    return issues


def check_page_size(wiki_path, pages, max_lines=200):
    large = []
    for page in pages:
        content = read_page(wiki_path, page)
        n = content.count('\n')
        if n > max_lines:
            large.append({'page': page, 'lines': n})
    return sorted(large, key=lambda x: x['lines'], reverse=True)


def check_source_drift(wiki_path):
    raw_dir = os.path.join(wiki_path, 'raw')
    if not os.path.isdir(raw_dir):
        return []
    issues = []
    for root, _, files in os.walk(raw_dir):
        for fname in files:
            if not fname.endswith('.md'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath) as f:
                    content = f.read()
            except OSError:
                continue
            fm = parse_frontmatter(content)
            stored = fm.get('sha256', '').strip()
            if not stored:
                continue
            body = extract_body(content) if content.startswith('---') else content
            computed = hashlib.sha256(body.encode()).hexdigest()
            if computed != stored:
                rel = os.path.relpath(fpath, wiki_path)
                issues.append({'file': rel, 'stored': stored[:12] + '...', 'computed': computed[:12] + '...'})
    return issues


def check_log_rotation(wiki_path, threshold=500):
    log_path = os.path.join(wiki_path, 'log.md')
    try:
        with open(log_path) as f:
            content = f.read()
    except FileNotFoundError:
        return {'error': 'log.md not found'}
    entries = len(re.findall(r'^## \[', content, re.MULTILINE))
    if entries > threshold:
        return {'needs_rotation': True, 'entries': entries, 'threshold': threshold}
    return {'entries': entries, 'threshold': threshold}


def check_stale(wiki_path, pages, days=90):
    today = date.today()
    cutoff = today - timedelta(days=days)
    stale = []
    for page in pages:
        content = read_page(wiki_path, page)
        fm = parse_frontmatter(content)
        updated = fm.get('updated', '').strip()
        if not updated:
            continue
        try:
            d = date.fromisoformat(updated)
            if d < cutoff:
                stale.append({'page': page, 'updated': updated, 'days_ago': (today - d).days})
        except ValueError:
            pass
    return sorted(stale, key=lambda x: x['days_ago'], reverse=True)


def check_quality(wiki_path, pages):
    contested, low_confidence = [], []
    for page in pages:
        content = read_page(wiki_path, page)
        fm = parse_frontmatter(content)
        if fm.get('contested', '').lower() == 'true':
            contested.append({'page': page, 'contradictions': fm.get('contradictions', '')})
        conf = fm.get('confidence', '').strip().lower()
        if conf == 'low':
            low_confidence.append({'page': page, 'confidence': 'low'})
        elif not conf and fm.get('sources', '').strip() in ('', '[]'):
            low_confidence.append({'page': page, 'note': 'no confidence field and no sources'})
    return {'contested': contested, 'low_confidence': low_confidence}


def check_registry_sync(wiki_path, wiki_root):
    if not wiki_root:
        return None
    wiki_root_abs = os.path.expanduser(wiki_root)
    registry_path = os.path.join(wiki_root_abs, 'readme.md')
    try:
        with open(registry_path) as f:
            registry = f.read()
    except FileNotFoundError:
        return {'error': f'Registry not found: {registry_path}'}

    unregistered = []
    try:
        for entry in os.scandir(wiki_root_abs):
            if entry.is_dir() and os.path.exists(os.path.join(entry.path, 'SCHEMA.md')):
                if entry.name not in registry:
                    unregistered.append(entry.name)
    except OSError as e:
        return {'error': str(e)}
    return unregistered


# ── Reporting ─────────────────────────────────────────────────────────────────

def severity_order(check_name):
    order = ['broken_links', 'orphans', 'source_drift', 'quality', 'stale',
             'index', 'frontmatter', 'tag_audit', 'page_size', 'log_rotation', 'registry_sync']
    try:
        return order.index(check_name)
    except ValueError:
        return 99


def format_text_report(results, wiki_path):
    lines = [f'# Wiki Lint Report: {wiki_path}', '']
    total_issues = 0

    def section(name, label, items, fmt):
        nonlocal total_issues
        if not items:
            lines.append(f'✓ {label}')
            return
        count = len(items) if isinstance(items, list) else sum(len(v) for v in items.values() if isinstance(v, list))
        total_issues += count
        lines.append(f'✗ {label} ({count})')
        for item in (items if isinstance(items, list) else []):
            lines.append(f'  {fmt(item)}')

    # Broken links
    bl = results.get('broken_links', [])
    if bl:
        total_issues += len(bl)
        lines.append(f'✗ Broken wikilinks ({len(bl)})')
        for item in bl:
            lines.append(f"  {item['page']} → {item['link']}")
    else:
        lines.append('✓ Broken wikilinks')

    # Orphans
    orp = results.get('orphans', [])
    if orp:
        total_issues += len(orp)
        lines.append(f'✗ Orphan pages ({len(orp)})')
        for p in orp:
            lines.append(f'  {p}')
    else:
        lines.append('✓ Orphan pages')

    # Source drift
    sd = results.get('source_drift', [])
    if sd:
        total_issues += len(sd)
        lines.append(f'✗ Source drift ({len(sd)})')
        for item in sd:
            lines.append(f"  {item['file']}  stored={item['stored']}  computed={item['computed']}")
    else:
        lines.append('✓ Source drift')

    # Quality signals
    qual = results.get('quality', {})
    contested = qual.get('contested', [])
    low_conf = qual.get('low_confidence', [])
    if contested or low_conf:
        total_issues += len(contested) + len(low_conf)
        lines.append(f'✗ Quality signals ({len(contested)} contested, {len(low_conf)} low-confidence)')
        for item in contested:
            lines.append(f"  [contested] {item['page']}")
        for item in low_conf:
            note = f"  ({item.get('note', 'confidence: low')})"
            lines.append(f"  [low-conf]  {item['page']}{note}")
    else:
        lines.append('✓ Quality signals')

    # Stale content
    stale = results.get('stale', [])
    if stale:
        total_issues += len(stale)
        lines.append(f'✗ Stale pages ({len(stale)})')
        for item in stale:
            lines.append(f"  {item['page']}  last updated {item['updated']} ({item['days_ago']} days ago)")
    else:
        lines.append('✓ Stale content')

    # Index completeness
    idx = results.get('index', [])
    if idx:
        total_issues += len(idx)
        lines.append(f'✗ Missing from index.md ({len(idx)})')
        for p in idx:
            lines.append(f'  {p}')
    else:
        lines.append('✓ Index completeness')

    # Frontmatter
    fm_issues = results.get('frontmatter', [])
    if fm_issues:
        total_issues += len(fm_issues)
        lines.append(f'✗ Frontmatter issues ({len(fm_issues)})')
        for item in fm_issues:
            detail = ', '.join(item.get('fields', [])) or item.get('issue', '')
            lines.append(f"  {item['page']}  [{detail}]")
    else:
        lines.append('✓ Frontmatter')

    # Tag audit
    ta = results.get('tag_audit', [])
    ta_real = [x for x in ta if 'error' not in x]
    if ta_real:
        total_issues += len(ta_real)
        lines.append(f'✗ Unknown tags ({len(ta_real)} pages)')
        for item in ta_real:
            lines.append(f"  {item['page']}  tags: {', '.join(item['unknown_tags'])}")
    else:
        lines.append('✓ Tag audit')

    # Page size
    ps = results.get('page_size', [])
    if ps:
        total_issues += len(ps)
        lines.append(f'✗ Oversized pages ({len(ps)})')
        for item in ps:
            lines.append(f"  {item['page']}  {item['lines']} lines")
    else:
        lines.append('✓ Page size')

    # Log rotation
    lr = results.get('log_rotation', {})
    if isinstance(lr, dict) and lr.get('needs_rotation'):
        total_issues += 1
        lines.append(f"✗ Log rotation needed ({lr['entries']} entries > {lr['threshold']})")
    else:
        entries = lr.get('entries', '?') if isinstance(lr, dict) else '?'
        lines.append(f'✓ Log rotation ({entries} entries)')

    # Registry sync
    rs = results.get('registry_sync')
    if rs and isinstance(rs, list) and rs:
        total_issues += len(rs)
        lines.append(f'✗ Unregistered wikis ({len(rs)})')
        for name in rs:
            lines.append(f'  {name}')
    elif rs is not None:
        lines.append('✓ Registry sync')

    lines.append('')
    lines.append(f'Total issues: {total_issues}')
    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Run lint checks on a wiki')
    parser.add_argument('wiki_path', help='Path to the wiki')
    parser.add_argument('--format', choices=['text', 'json'], default='text')
    parser.add_argument('--wiki-root', help='WIKI_ROOT path for registry sync check')
    parser.add_argument('--check', nargs='+', choices=ALL_CHECKS, help='Run only specific checks')
    args = parser.parse_args()

    wiki_path = os.path.expanduser(args.wiki_path)
    if not os.path.isdir(wiki_path):
        print(json.dumps({'error': f'Wiki not found: {wiki_path}'}))
        sys.exit(2)

    checks = args.check or ALL_CHECKS
    wiki_root = args.wiki_root or os.environ.get('WIKI_ROOT', '')
    pages = get_wiki_pages(wiki_path)

    results = {}

    if 'orphans' in checks:
        results['orphans'] = check_orphans(wiki_path, pages)
    if 'broken_links' in checks:
        results['broken_links'] = check_broken_links(wiki_path, pages)
    if 'index' in checks:
        results['index'] = check_index_completeness(wiki_path, pages)
    if 'frontmatter' in checks:
        results['frontmatter'] = check_frontmatter(wiki_path, pages)
    if 'tag_audit' in checks:
        results['tag_audit'] = check_tag_audit(wiki_path, pages)
    if 'page_size' in checks:
        results['page_size'] = check_page_size(wiki_path, pages)
    if 'source_drift' in checks:
        results['source_drift'] = check_source_drift(wiki_path)
    if 'log_rotation' in checks:
        results['log_rotation'] = check_log_rotation(wiki_path)
    if 'stale' in checks:
        results['stale'] = check_stale(wiki_path, pages)
    if 'quality' in checks:
        results['quality'] = check_quality(wiki_path, pages)
    if 'registry_sync' in checks:
        results['registry_sync'] = check_registry_sync(wiki_path, wiki_root)

    if args.format == 'json':
        print(json.dumps(results, indent=2))
    else:
        print(format_text_report(results, wiki_path))

    # Exit 1 if any real issues found
    has_issues = any([
        results.get('broken_links'),
        results.get('orphans'),
        results.get('source_drift'),
        results.get('index'),
        results.get('frontmatter'),
        [x for x in results.get('tag_audit', []) if 'error' not in x],
        results.get('page_size'),
        results.get('stale'),
        results.get('quality', {}).get('contested'),
        results.get('quality', {}).get('low_confidence'),
        results.get('registry_sync') and isinstance(results['registry_sync'], list) and results['registry_sync'],
        isinstance(results.get('log_rotation'), dict) and results['log_rotation'].get('needs_rotation'),
    ])
    sys.exit(1 if has_issues else 0)


if __name__ == '__main__':
    main()

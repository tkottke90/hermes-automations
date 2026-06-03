#!/usr/bin/env python3
"""
Resolve the correct wiki path from WIKI_ROOT registry.

Usage:
    python wiki-route.py "kubernetes homelab networking"
    python wiki-route.py --list

Checks WIKI_PATH first (direct override), then WIKI_ROOT registry, then ~/wiki default.

Output JSON:
    {"path": "/abs/path", "name": "homelab", "source": "WIKI_ROOT"}
    {"ambiguous": true, "candidates": [{"name": ..., "path": ...}, ...]}
    {"no_match": true, "available": ["wiki1", "wiki2"]}
    {"path": "~/wiki", "source": "default"}
"""
import json
import os
import re
import sys


def parse_registry(registry_path):
    try:
        with open(registry_path) as f:
            content = f.read()
    except FileNotFoundError:
        return [], ""

    wikis = []
    row_re = re.compile(r'^\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|', re.MULTILINE)
    for m in row_re.finditer(content):
        cells = [c.strip() for c in m.groups()]
        name, path, domain, tags, status = cells
        if name.lower() in ('name', '---', ''):
            continue
        if 'active' not in status.lower() and status.strip():
            continue
        wikis.append({
            'name': name,
            'path': path,
            'domain': domain,
            'tags': [t.strip() for t in tags.split(',')],
        })

    routing_notes = ''
    notes_m = re.search(r'## Routing Notes\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
    if notes_m:
        routing_notes = notes_m.group(1).strip()

    return wikis, routing_notes


def score_wiki(wiki, context_lower, routing_notes):
    score = 0

    if wiki['name'].lower() in context_lower:
        score += 10

    for word in re.split(r'\W+', wiki['domain'].lower()):
        if len(word) > 3 and word in context_lower:
            score += 2

    for tag in wiki['tags']:
        if tag.lower().strip() in context_lower:
            score += 3

    # Routing notes: lines like "- Anything about X → wiki-name"
    for line in routing_notes.split('\n'):
        sep = None
        if '->' in line:
            sep = '->'
        elif '→' in line:
            sep = '→'
        if not sep:
            continue
        parts = line.split(sep, 1)
        if len(parts) != 2:
            continue
        triggers_raw, target = parts
        if wiki['name'].lower() not in target.lower():
            continue
        for trigger in re.split(r'[,\-]', triggers_raw):
            t = trigger.strip().lower()
            if t and len(t) > 2 and t in context_lower:
                score += 8

    return score


def resolve_path(path_field, wiki_root):
    p = path_field.strip().rstrip('/')
    if os.path.isabs(p):
        return p
    vault_root = os.path.dirname(wiki_root.rstrip('/'))
    return os.path.join(vault_root, p)


def main():
    wiki_path_env = os.environ.get('WIKI_PATH', '').strip()
    if wiki_path_env:
        print(json.dumps({'path': os.path.expanduser(wiki_path_env), 'source': 'WIKI_PATH'}))
        return

    wiki_root = os.environ.get('WIKI_ROOT', '').strip()
    if not wiki_root:
        print(json.dumps({'path': os.path.expanduser('~/wiki'), 'source': 'default'}))
        return

    wiki_root = os.path.expanduser(wiki_root)
    registry_path = os.path.join(wiki_root, 'readme.md')

    if '--list' in sys.argv:
        wikis, _ = parse_registry(registry_path)
        print(json.dumps({'wikis': wikis, 'registry': registry_path}, indent=2))
        return

    context = ' '.join(a for a in sys.argv[1:] if not a.startswith('-')).lower()

    wikis, routing_notes = parse_registry(registry_path)
    if not wikis:
        print(json.dumps({'error': f'No active wikis in registry: {registry_path}'}))
        sys.exit(1)

    scored = sorted(
        [(score_wiki(w, context, routing_notes), w) for w in wikis],
        key=lambda x: x[0],
        reverse=True,
    )

    top_score = scored[0][0]

    if top_score == 0:
        print(json.dumps({'no_match': True, 'available': [w['name'] for _, w in scored]}))
        return

    top_wikis = [w for s, w in scored if s == top_score]
    if len(top_wikis) > 1:
        candidates = [{'name': w['name'], 'path': resolve_path(w['path'], wiki_root)} for w in top_wikis]
        print(json.dumps({'ambiguous': True, 'candidates': candidates}))
        return

    winner = top_wikis[0]
    print(json.dumps({
        'path': resolve_path(winner['path'], wiki_root),
        'name': winner['name'],
        'domain': winner['domain'],
        'score': top_score,
        'source': 'WIKI_ROOT',
    }))


if __name__ == '__main__':
    main()

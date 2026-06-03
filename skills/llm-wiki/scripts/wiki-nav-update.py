#!/usr/bin/env python3
"""
Update wiki navigation files after creating or modifying pages.

Usage:
    # Add a new page to index.md
    python wiki-nav-update.py /wiki --add entities/gpt-4.md --summary "OpenAI GPT-4 model"

    # Append a log entry
    python wiki-nav-update.py /wiki --log "ingest | GPT-4 technical report" --files "entities/gpt-4.md,concepts/moe.md"

    # Update page count and date in index header
    python wiki-nav-update.py /wiki --update-header

    # Typical post-ingest call (all at once):
    python wiki-nav-update.py /wiki \
        --add entities/gpt-4.md --summary "OpenAI GPT-4 model" \
        --log "ingest | GPT-4 technical report" \
        --files "entities/gpt-4.md,concepts/moe.md"
"""
import argparse
import json
import os
import re
import sys
from datetime import date


TODAY = date.today().isoformat()
WIKI_SUBDIRS = ('entities', 'concepts', 'comparisons', 'queries')
SECTION_MAP = {
    'entities': 'Entities',
    'concepts': 'Concepts',
    'comparisons': 'Comparisons',
    'queries': 'Queries',
}


def count_pages(wiki_path):
    total = 0
    for subdir in WIKI_SUBDIRS:
        d = os.path.join(wiki_path, subdir)
        if os.path.isdir(d):
            total += sum(1 for f in os.listdir(d) if f.endswith('.md'))
    return total


def add_to_index(wiki_path, rel_path, summary):
    index_path = os.path.join(wiki_path, 'index.md')
    try:
        with open(index_path) as f:
            content = f.read()
    except FileNotFoundError:
        return {'error': 'index.md not found'}

    stem = os.path.basename(rel_path).removesuffix('.md')
    # Skip if already present
    if f'[[{stem}' in content or f'[[{rel_path}' in content:
        return {'skipped': True, 'reason': f'{stem} already in index'}

    subdir = rel_path.split('/')[0] if '/' in rel_path else ''
    section = SECTION_MAP.get(subdir, 'Entities')
    entry = f'- [[{rel_path}]] — {summary}'
    section_header = f'## {section}'

    if section_header in content:
        # Append entry before the next ## section or EOF
        pattern = re.compile(
            rf'({re.escape(section_header)}\n(?:[^\n]*\n)*?)(?=\n## |\Z)',
            re.DOTALL
        )
        m = pattern.search(content)
        if m:
            block = m.group(1).rstrip('\n')
            content = content[:m.start()] + block + f'\n{entry}\n' + content[m.end():]
        else:
            content += f'\n{entry}\n'
    else:
        content += f'\n{section_header}\n{entry}\n'

    with open(index_path, 'w') as f:
        f.write(content)
    return {'added': entry, 'section': section}


def update_index_header(wiki_path):
    index_path = os.path.join(wiki_path, 'index.md')
    try:
        with open(index_path) as f:
            content = f.read()
    except FileNotFoundError:
        return {'error': 'index.md not found'}

    page_count = count_pages(wiki_path)
    content = re.sub(r'Total pages: \d+', f'Total pages: {page_count}', content)
    content = re.sub(r'Last updated: \d{4}-\d{2}-\d{2}', f'Last updated: {TODAY}', content)

    with open(index_path, 'w') as f:
        f.write(content)
    return {'page_count': page_count, 'date': TODAY}


def append_log(wiki_path, action_subject, files=None):
    log_path = os.path.join(wiki_path, 'log.md')
    try:
        with open(log_path) as f:
            existing = f.read()
    except FileNotFoundError:
        return {'error': 'log.md not found'}

    entry = f'\n## [{TODAY}] {action_subject}\n'
    if files:
        for fname in files.split(','):
            fname = fname.strip()
            if fname:
                entry += f'- {fname}\n'

    with open(log_path, 'a') as f:
        f.write(entry)

    total = len(re.findall(r'^## \[', existing + entry, re.MULTILINE))
    result = {'appended': action_subject, 'total_log_entries': total}
    if total > 500:
        result['rotation_needed'] = True
        result['rotation_note'] = f'Rename log.md to log-{TODAY[:4]}.md and start a fresh log.md'
    return result


def main():
    parser = argparse.ArgumentParser(description='Update wiki navigation files')
    parser.add_argument('wiki_path', help='Path to the wiki')
    parser.add_argument('--add', metavar='REL_PATH', help='Relative page path to add to index.md')
    parser.add_argument('--summary', help='One-line summary for the index entry')
    parser.add_argument('--log', metavar='ACTION | SUBJECT', help='Log entry text')
    parser.add_argument('--files', help='Comma-separated files touched (appended to log entry)')
    parser.add_argument('--update-header', action='store_true', help='Refresh page count and date in index header')
    args = parser.parse_args()

    wiki_path = os.path.expanduser(args.wiki_path)
    results = {}

    if args.add:
        if not args.summary:
            print('--summary is required with --add', file=sys.stderr)
            sys.exit(1)
        results['index_add'] = add_to_index(wiki_path, args.add, args.summary)

    if args.log:
        results['log'] = append_log(wiki_path, args.log, args.files)

    if args.update_header or args.add:
        results['header'] = update_index_header(wiki_path)

    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()

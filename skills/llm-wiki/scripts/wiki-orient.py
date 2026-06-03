#!/usr/bin/env python3
"""
Load and format wiki orientation context for an LLM session.

Usage:
    python wiki-orient.py /path/to/wiki
    python wiki-orient.py /path/to/wiki --log-lines 30
    python wiki-orient.py /path/to/wiki --json

Reads SCHEMA.md, index.md, and the tail of log.md, then outputs a formatted
orientation block ready to be included in an LLM context window.
"""
import json
import os
import sys


WIKI_SUBDIRS = ('entities', 'concepts', 'comparisons', 'queries')


def read_file(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def read_tail(path, n_lines):
    try:
        with open(path) as f:
            lines = f.readlines()
        return ''.join(lines[-n_lines:])
    except FileNotFoundError:
        return None


def count_pages(wiki_path):
    total = 0
    for subdir in WIKI_SUBDIRS:
        d = os.path.join(wiki_path, subdir)
        if os.path.isdir(d):
            total += sum(1 for f in os.listdir(d) if f.endswith('.md'))
    return total


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('-'):
        print('Usage: wiki-orient.py /path/to/wiki [--log-lines N] [--json]', file=sys.stderr)
        sys.exit(1)

    wiki_path = os.path.expanduser(args[0])
    log_lines = 30
    as_json = '--json' in args

    for i, a in enumerate(args):
        if a == '--log-lines' and i + 1 < len(args):
            try:
                log_lines = int(args[i + 1])
            except ValueError:
                pass

    schema = read_file(os.path.join(wiki_path, 'SCHEMA.md'))
    index = read_file(os.path.join(wiki_path, 'index.md'))
    log_tail = read_tail(os.path.join(wiki_path, 'log.md'), log_lines)
    page_count = count_pages(wiki_path)

    missing = [f for f, content in [('SCHEMA.md', schema), ('index.md', index)] if content is None]

    if as_json:
        print(json.dumps({
            'schema': schema,
            'index': index,
            'log_tail': log_tail,
            'page_count': page_count,
            'wiki_path': wiki_path,
            'missing': missing,
        }, indent=2))
        return

    print(f'# Wiki Orientation: {wiki_path}')
    print(f'> {page_count} pages total')
    if missing:
        print(f'> WARNING: Missing files: {", ".join(missing)}')
    print()

    if schema:
        print('## SCHEMA.md\n')
        print(schema.rstrip())
        print()

    if index:
        print('## index.md\n')
        print(index.rstrip())
        print()

    if log_tail:
        print(f'## log.md (last {log_lines} lines)\n')
        print(log_tail.rstrip())


if __name__ == '__main__':
    main()

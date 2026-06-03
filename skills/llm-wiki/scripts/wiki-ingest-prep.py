#!/usr/bin/env python3
"""
Pre-flight checks before ingesting a source into the wiki.

Usage:
    python wiki-ingest-prep.py /path/to/wiki --file /path/to/source.md
    python wiki-ingest-prep.py /path/to/wiki --file /path/to/source.md --url https://example.com
    python wiki-ingest-prep.py /path/to/wiki --url https://example.com
    python wiki-ingest-prep.py /path/to/wiki --keywords "gpt-4,transformers,openai"

Output JSON:
{
  "sha256": "abc123...",
  "is_new": true,
  "drift": false,
  "existing_raw": null,
  "stored_sha256": null,
  "existing_pages": ["entities/openai.md"],
  "suggested_raw_path": "raw/articles/example-com-2026-06-03.md"
}

Notes:
    - sha256 is computed over the body only (everything after the closing --- frontmatter).
    - Uses plain Python open(), NOT hermes read_file, which returns a paginated dict.
    - existing_pages are wiki pages mentioning any of the provided keywords.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date


FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---', re.DOTALL)
WIKI_SUBDIRS = ('entities', 'concepts', 'comparisons', 'queries')
TODAY = date.today().isoformat()


def parse_frontmatter(content):
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split('\n'):
        if ':' in line:
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


def compute_sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def find_existing_raw(wiki_path, url):
    raw_dir = os.path.join(wiki_path, 'raw')
    if not os.path.isdir(raw_dir):
        return None
    for root, _, files in os.walk(raw_dir):
        for fname in files:
            if not fname.endswith('.md'):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath) as fh:
                    content = fh.read()
                fm = parse_frontmatter(content)
                if fm.get('source_url', '').strip() == url.strip():
                    return os.path.relpath(fpath, wiki_path)
            except OSError:
                pass
    return None


def search_wiki_pages(wiki_path, keywords):
    matches = set()
    kw_lower = [k.lower().strip() for k in keywords if k.strip()]
    for subdir in WIKI_SUBDIRS:
        d = os.path.join(wiki_path, subdir)
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if not fname.endswith('.md'):
                continue
            fpath = os.path.join(d, fname)
            try:
                with open(fpath) as fh:
                    content = fh.read().lower()
                if any(kw in content for kw in kw_lower):
                    matches.add(os.path.join(subdir, fname))
            except OSError:
                pass
    return sorted(matches)


def suggest_raw_path(url='', filename=''):
    if filename:
        stem = os.path.basename(filename).removesuffix('.md')
        stem = re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-')[:60]
        return f'raw/articles/{stem}.md'
    if url:
        slug = re.sub(r'https?://(www\.)?', '', url.lower())
        slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')[:50]
        return f'raw/articles/{slug}-{TODAY}.md'
    return f'raw/articles/source-{TODAY}.md'


def main():
    parser = argparse.ArgumentParser(description='Pre-flight wiki ingest checks')
    parser.add_argument('wiki_path', help='Path to the wiki')
    parser.add_argument('--file', help='Local source file to ingest')
    parser.add_argument('--url', default='', help='URL being ingested')
    parser.add_argument('--keywords', default='', help='Comma-separated keywords to search existing pages')
    args = parser.parse_args()

    wiki_path = os.path.expanduser(args.wiki_path)
    result = {}

    # Compute sha256 from file
    if args.file:
        file_path = os.path.expanduser(args.file)
        try:
            with open(file_path) as f:
                raw = f.read()
            body = extract_body(raw) if raw.startswith('---') else raw
            result['sha256'] = compute_sha256(body)
        except FileNotFoundError:
            print(json.dumps({'error': f'File not found: {file_path}'}))
            sys.exit(1)

    # Re-ingest detection
    url = args.url.strip()
    if url:
        existing_raw = find_existing_raw(wiki_path, url)
        result['existing_raw'] = existing_raw
        result['is_new'] = existing_raw is None

        if existing_raw and result.get('sha256'):
            existing_path = os.path.join(wiki_path, existing_raw)
            try:
                with open(existing_path) as f:
                    existing_content = f.read()
                fm = parse_frontmatter(existing_content)
                stored = fm.get('sha256', '').strip()
                result['stored_sha256'] = stored or None
                result['drift'] = bool(stored) and stored != result['sha256']
            except OSError:
                result['drift'] = False
                result['stored_sha256'] = None
        else:
            result['drift'] = False
            result['stored_sha256'] = None
    else:
        result['is_new'] = True
        result['drift'] = False
        result['existing_raw'] = None
        result['stored_sha256'] = None

    # Search existing wiki pages
    keywords = [k for k in args.keywords.split(',') if k.strip()]
    if not keywords and args.file:
        # Derive keywords from filename
        stem = os.path.basename(args.file).removesuffix('.md')
        keywords = [p for p in re.split(r'[-_\s]+', stem) if len(p) > 2][:6]

    result['existing_pages'] = search_wiki_pages(wiki_path, keywords) if keywords else []
    result['suggested_raw_path'] = suggest_raw_path(url, args.file or '')

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

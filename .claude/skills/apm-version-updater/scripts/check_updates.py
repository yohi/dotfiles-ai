#!/usr/bin/env python3
"""Detect and report updatable pinned dependencies in apm.yml.

Scans apm.yml for version-pinned dependencies and best-effort resolves the
latest available version or commit hash for each. Handles four kinds:

  plugin     top-level `plugin:` npm packages   (e.g. @yohi/justice@2.3.0)
  mcp-npm    npm package inside an MCP `args:`   (e.g. @yohi/nexus@1.22.0)
  mcp-git    git+https://....git@<commit-hash>   (e.g. chronos-graph)
  apm-skill  dependencies.apm `owner/repo#<tag>` (e.g. obra/superpowers#v6.0.2)

`@latest` entries are reported for information only (never auto-changed).

Output is ASCII only. Network calls (npm, git) are best-effort; a failure is
reported as 'unresolved' rather than aborting the whole run.

Usage:
  python check_updates.py [--apm PATH] [--json] [--no-network]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TIMEOUT = 30

GIT_HASH_RE = re.compile(r'git\+(https?://[^\s@"]+?\.git)@([0-9a-fA-F]{7,40})')
SKILL_REF_RE = re.compile(
    r'-\s*"?([A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?://[^\s#"]+)?)#([^\s"]+?)"?\s*$'
)
NPM_RE = re.compile(
    r'-\s*"?(@?[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?)'
    r'@([0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.\-]*|latest)"?\s*$'
)
SEMVER_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)')
FULL_SHA_RE = re.compile(r'^[0-9a-fA-F]{40}$')


def run(cmd):
    """Run a command, returning stripped stdout or None on any failure."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def url_to_slug(url):
    slug = re.sub(r'^https?://[^/]+/', '', url)
    return re.sub(r'\.git$', '', slug)


def norm(value):
    return (value or '').lstrip('vV').strip().lower()


def short(value):
    if value and FULL_SHA_RE.match(value):
        return value[:12]
    return value


def detect(text):
    """Return a list of pinned-dependency records found in apm.yml text."""
    records = []
    section = None
    for idx, line in enumerate(text.splitlines(), start=1):
        top = re.match(r'^([A-Za-z0-9_-]+):', line)
        if top:
            section = top.group(1)

        m = GIT_HASH_RE.search(line)
        if m:
            url, sha = m.group(1), m.group(2)
            slug = url_to_slug(url)
            records.append({
                'kind': 'mcp-git', 'name': slug, 'current': sha,
                'line': idx, 'spec': 'hash', 'repo': slug, 'git_url': url,
            })
            continue

        m = SKILL_REF_RE.search(line)
        if m and '/' in m.group(1):
            name, ref = m.group(1), m.group(2)
            repo = name.split('//')[0]
            records.append({
                'kind': 'apm-skill', 'name': name, 'current': ref,
                'line': idx, 'spec': 'tag', 'repo': repo,
                'git_url': 'https://github.com/%s.git' % repo,
            })
            continue

        m = NPM_RE.search(line)
        if m:
            name, ver = m.group(1), m.group(2)
            kind = 'plugin' if section == 'plugin' else 'mcp-npm'
            records.append({
                'kind': kind, 'name': name, 'current': ver,
                'line': idx, 'spec': 'latest' if ver == 'latest' else 'semver',
            })
    return records


def latest_npm(name):
    return run(['npm', 'view', name, 'version'])


def latest_tag(url):
    out = run(['git', 'ls-remote', '--tags', '--refs', url])
    if not out:
        return None
    best, best_key = None, None
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) != 2:
            continue
        tag = parts[1].replace('refs/tags/', '')
        m = SEMVER_RE.match(tag)
        if not m:
            continue
        key = tuple(int(x) for x in m.groups())
        if best_key is None or key > best_key:
            best, best_key = tag, key
    return best


def latest_head(url):
    out = run(['git', 'ls-remote', url, 'HEAD'])
    if not out:
        return None
    fields = out.split()
    return fields[0] if fields else None


def resolve(rec):
    """Populate rec['latest'] and rec['update'] (best-effort)."""
    if rec['spec'] == 'latest':
        rec['latest'] = '(tracks latest)'
        rec['update'] = False
        return
    latest = None
    if rec['kind'] in ('plugin', 'mcp-npm'):
        latest = latest_npm(rec['name'])
    elif rec['kind'] == 'apm-skill':
        latest = latest_tag(rec['git_url'])
    elif rec['kind'] == 'mcp-git':
        latest = latest_head(rec['git_url'])
    rec['latest'] = latest or 'unresolved'
    rec['update'] = bool(latest) and norm(latest) != norm(rec['current'])


def render_table(records):
    headers = ['KIND', 'NAME', 'CURRENT', 'LATEST', 'UPDATE']
    rows = []
    for r in records:
        rows.append([
            r['kind'], r['name'], short(r['current']),
            short(r.get('latest', '?')),
            'yes' if r.get('update') else ('-' if r['spec'] != 'latest' else 'track'),
        ])
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = []
    fmt = '  '.join('%-*s' for _ in headers)
    flat = []
    for i, h in enumerate(headers):
        flat.extend([widths[i], h])
    lines.append(fmt % tuple(flat))
    lines.append('  '.join('-' * w for w in widths))
    for row in rows:
        flat = []
        for i, cell in enumerate(row):
            flat.extend([widths[i], cell])
        lines.append(fmt % tuple(flat))
    updates = sum(1 for r in records if r.get('update'))
    lines.append('')
    lines.append('%d update(s) available out of %d pinned dependencies.'
                 % (updates, len(records)))
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apm', default='apm.yml', help='path to apm.yml')
    parser.add_argument('--json', action='store_true', help='emit JSON')
    parser.add_argument('--no-network', action='store_true',
                        help='inventory only, skip latest resolution')
    args = parser.parse_args(argv)

    apm_path = Path(args.apm)
    if not apm_path.is_file():
        fallback = Path(__file__).resolve().parents[4] / 'apm.yml'
        if fallback.is_file():
            apm_path = fallback
        else:
            sys.stderr.write('error: apm.yml not found (tried %s)\n' % args.apm)
            return 2

    records = detect(apm_path.read_text(encoding='utf-8'))

    if not args.no_network:
        for rec in records:
            resolve(rec)
    else:
        for rec in records:
            rec.setdefault('latest', '(skipped)')
            rec.setdefault('update', False)

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print(render_table(records))
    return 0


if __name__ == '__main__':
    sys.exit(main())

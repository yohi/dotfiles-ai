#!/usr/bin/env python3
"""Detect and report updatable pinned dependencies in apm.yml.

Scans apm.yml for version-pinned dependencies and best-effort resolves the
latest available version or commit hash for each. Handles four kinds:

  plugin     top-level `plugin:` npm packages   (e.g. @yohi/justice@2.3.0)
  mcp-npm    npm package inside an MCP `args:`   (e.g. @yohi/nexus@1.22.0)
  mcp-git    git+https://....git@<commit-hash>   (e.g. chronos-graph)
  apm-skill  dependencies.apm `owner/repo#<tag>` (e.g. obra/superpowers#v6.0.2)

`@latest` entries are reported for information only (never auto-changed).

Output is ASCII only. Network calls (npm, git, HTTP) are best-effort; a
failure is reported as 'unresolved' rather than aborting the whole run.

Usage:
  python check_updates.py [--apm PATH] [--json] [--no-network]
  python check_updates.py --models
  python check_updates.py --validate-models [--apm PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT = 30

MODEL_SCHEMA_URL = "https://models.dev/model-schema.json"
BEDROCK_ALLOWED_PREFIXES = ("global.anthropic.claude-", "openai.gpt-")

GIT_HASH_RE = re.compile(r'git\+(https?://[^\s@"]+?\.git)@([0-9a-fA-F]{7,40})')
SKILL_REF_RE = re.compile(
    r'-\s*"?([A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?://[^\s#"]+)?)#([^\s"]+?)"?\s*$'
)
NPM_RE = re.compile(
    r'-\s*"?(@?[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?)'
    r'@([0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.\-]*|latest)"?\s*$'
)
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?![\d.+\-])")
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def run(cmd, include_stderr=False):
    """Run a command, returning stripped stdout or None on any failure."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        if include_stderr:
            sys.stderr.write(
                "timeout after %ds: %s\n" % (TIMEOUT, " ".join(cmd))
            )
        return None
    except (FileNotFoundError, OSError):
        if include_stderr:
            sys.stderr.write("command not found: %s\n" % cmd[0])
        return None
    if proc.returncode != 0:
        if include_stderr:
            err = (proc.stderr or "").strip()
            sys.stderr.write("%s failed: %s\n" % (" ".join(cmd), err))
        return None
    return proc.stdout.strip()


def url_to_slug(url):
    slug = re.sub(r"^https?://[^/]+/", "", url)
    return re.sub(r"\.git$", "", slug)


def norm(value):
    return (value or "").lstrip("vV").strip().lower()


def short(value):
    if value and FULL_SHA_RE.match(value):
        return value[:12]
    return value


def same_hash(current, latest):
    """Return True if current matches latest, supporting short hashes."""
    current = (current or "").strip().lower()
    latest = (latest or "").strip().lower()
    if FULL_SHA_RE.match(current):
        return current == latest
    return latest.startswith(current)


def fetch_model_schema():
    """Fetch and return the models.dev model schema as a dict."""
    req = urllib.request.Request(
        MODEL_SCHEMA_URL,
        headers={"User-Agent": "apm-updater/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def extract_models(schema):
    """Extract the list of model identifiers from the schema."""
    try:
        return schema["$defs"]["Model"]["enum"]
    except (KeyError, TypeError):
        return []


def list_models(json_mode=False):
    """Print or return the available models from models.dev."""
    schema = fetch_model_schema()
    if schema is None:
        sys.stderr.write(
            "error: failed to fetch model schema from %s\n" % MODEL_SCHEMA_URL
        )
        return None
    models = extract_models(schema)
    if not models:
        sys.stderr.write("error: no models found in schema\n")
        return None

    if json_mode:
        print(json.dumps(sorted(models), indent=2))
        return 0

    groups = {}
    for model in models:
        provider = model.split("/", 1)[0] if "/" in model else "unknown"
        groups.setdefault(provider, []).append(model)

    lines = ["MODEL SCHEMA: %d model(s)" % len(models), ""]
    for provider in sorted(groups):
        lines.append("[%s]" % provider)
        for model in sorted(groups[provider]):
            lines.append("  %s" % model)
        lines.append("")
    print("\n".join(lines))
    return 0


def validate_apm_models(apm_path: Path) -> int:
    """Check apm.yml provider/model whitelist entries against the schema."""
    schema = fetch_model_schema()
    if schema is None:
        sys.stderr.write(
            "error: failed to fetch model schema from %s\n" % MODEL_SCHEMA_URL
        )
        return 1
    valid_models = set(extract_models(schema))

    text = apm_path.read_text(encoding="utf-8")
    issues = []
    in_provider_section = False
    provider_indent = 0
    provider_name = None
    provider_name_indent = None
    list_key = None
    list_key_indent = None

    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        top = re.match(r"^([A-Za-z0-9_-]+):", stripped)
        if top:
            section = top.group(1)
            if in_provider_section:
                if indent <= provider_indent:
                    in_provider_section = False
                    provider_name = None
                    provider_name_indent = None
                    list_key = None
                    list_key_indent = None
                else:
                    if (
                        provider_name_indent is not None
                        and indent <= provider_name_indent
                    ):
                        provider_name = None
                        provider_name_indent = None
                    if list_key_indent is not None and indent <= list_key_indent:
                        list_key = None
                        list_key_indent = None

            if section == "provider" and indent == 0:
                in_provider_section = True
                provider_indent = indent
                provider_name = None
                provider_name_indent = None
                list_key = None
                list_key_indent = None
                continue

            if in_provider_section:
                if section in ("whitelist", "models") and provider_name is not None:
                    list_key = section
                    list_key_indent = indent
                else:
                    provider_name = section
                    provider_name_indent = indent
            continue

        if not in_provider_section or not provider_name or not list_key:
            continue

        m = re.match(r'^\s*-\s*"?([^"\s#]+)"?\s*$', line)
        if not m:
            continue

        model = m.group(1)
        if provider_name == "amazon-bedrock":
            full_model = "amazon-bedrock/%s" % model
            if not model.startswith(BEDROCK_ALLOWED_PREFIXES):
                issues.append((idx, model, "not allowed in Bedrock whitelist"))
                continue
        else:
            full_model = "%s/%s" % (provider_name, model)

        if full_model not in valid_models:
            issues.append((idx, model, "not in models.dev schema (%s)" % full_model))
    if issues:
        print("MODEL VALIDATION ISSUES: %d" % len(issues))
        for line_no, model, reason in issues:
            print("  line %d: %s (%s)" % (line_no, model, reason))
    else:
        print("MODEL VALIDATION: all whitelist entries match models.dev schema")
    return 0 if not issues else 1


def validate_duplicates(apm_path: Path) -> int:
    """Detect duplicate entries in provider/model whitelists."""
    text = apm_path.read_text(encoding="utf-8")
    issues = []
    in_provider_section = False
    provider_indent = 0
    provider_name = None
    provider_name_indent = None
    list_key = None
    list_key_indent = None
    seen = {}

    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        top = re.match(r"^([A-Za-z0-9_-]+):", stripped)
        if top:
            section = top.group(1)
            if in_provider_section:
                if indent <= provider_indent:
                    in_provider_section = False
                    provider_name = None
                    provider_name_indent = None
                    list_key = None
                    list_key_indent = None
                    seen = {}
                else:
                    if (
                        provider_name_indent is not None
                        and indent <= provider_name_indent
                    ):
                        provider_name = None
                        provider_name_indent = None
                        seen = {}
                    if list_key_indent is not None and indent <= list_key_indent:
                        list_key = None
                        list_key_indent = None
                        seen = {}

            if section == "provider" and indent == 0:
                in_provider_section = True
                provider_indent = indent
                provider_name = None
                provider_name_indent = None
                list_key = None
                list_key_indent = None
                seen = {}
                continue

            if in_provider_section:
                if section in ("whitelist", "models") and provider_name is not None:
                    list_key = section
                    list_key_indent = indent
                    seen = {}
                else:
                    provider_name = section
                    provider_name_indent = indent
                    seen = {}
            continue

        if not in_provider_section or not provider_name or not list_key:
            continue

        m = re.match(r'^\s*-\s*"?([^"\s#]+)"?\s*$', line)
        if not m:
            continue

        model = m.group(1)
        if model in seen:
            issues.append((idx, provider_name, list_key, model, seen[model]))
        else:
            seen[model] = idx

    if issues:
        print("DUPLICATE ENTRIES: %d" % len(issues))
        for line_no, provider, key, model, first_line in issues:
            print(
                "  line %d: %s/%s '%s' (first at line %d)"
                % (line_no, provider, key, model, first_line),
            )
    else:
        print("DUPLICATE ENTRIES: none")
    return 0 if not issues else 1


def check_model(identifier: str) -> int:
    """Check if a model identifier exists in the models.dev schema."""
    schema = fetch_model_schema()
    if schema is None:
        sys.stderr.write(
            "error: failed to fetch model schema from %s\n" % MODEL_SCHEMA_URL
        )
        return 1
    valid_models = set(extract_models(schema))
    if identifier in valid_models:
        print("VALID: %s" % identifier)
        return 0
    suffix = identifier.split("/")[-1] if "/" in identifier else identifier
    suggestions = [m for m in valid_models if m.endswith("/" + suffix)]
    print("INVALID: %s" % identifier)
    if suggestions:
        print("suggestions:")
        for s in sorted(suggestions)[:10]:
            print("  %s" % s)
    return 1


def detect(text):
    """Return a list of pinned-dependency records found in apm.yml text."""
    records = []
    section = None
    for idx, line in enumerate(text.splitlines(), start=1):
        top = re.match(r"^([A-Za-z0-9_-]+):", line)
        if top:
            section = top.group(1)

        m = GIT_HASH_RE.search(line)
        if m:
            url, sha = m.group(1), m.group(2)
            slug = url_to_slug(url)
            records.append(
                {
                    "kind": "mcp-git",
                    "name": slug,
                    "current": sha,
                    "line": idx,
                    "spec": "hash",
                    "repo": slug,
                    "git_url": url,
                }
            )
            continue

        m = SKILL_REF_RE.search(line)
        if m and "/" in m.group(1):
            name, ref = m.group(1), m.group(2)
            repo = name.split("//")[0]
            records.append(
                {
                    "kind": "apm-skill",
                    "name": name,
                    "current": ref,
                    "line": idx,
                    "spec": "tag",
                    "repo": repo,
                    "git_url": "https://github.com/%s.git" % repo,
                }
            )
            continue

        m = NPM_RE.search(line)
        if m:
            name, ver = m.group(1), m.group(2)
            kind = "plugin" if section == "plugin" else "mcp-npm"
            records.append(
                {
                    "kind": kind,
                    "name": name,
                    "current": ver,
                    "line": idx,
                    "spec": "latest" if ver == "latest" else "semver",
                }
            )
    return records


def latest_npm(name, verbose=False):
    return run(["npm", "view", name, "version"], include_stderr=verbose)


def latest_tag(url):
    out = run(["git", "ls-remote", "--tags", "--refs", url])
    if not out:
        return None
    best, best_key = None, None
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        tag = parts[1].replace("refs/tags/", "")
        m = SEMVER_RE.match(tag)
        if not m:
            continue
        key = tuple(int(x) for x in m.groups())
        if best_key is None or key > best_key:
            best, best_key = tag, key
    return best


def latest_head(url):
    out = run(["git", "ls-remote", url, "HEAD"])
    if not out:
        return None
    fields = out.split()
    return fields[0] if fields else None


def resolve(rec, verbose=False):
    """Populate rec['latest'] and rec['update'] (best-effort)."""
    if rec["spec"] == "latest":
        rec["latest"] = "(tracks latest)"
        rec["update"] = False
        return
    latest = None
    if rec["kind"] in ("plugin", "mcp-npm"):
        latest = latest_npm(rec["name"], verbose=verbose)
    elif rec["kind"] == "apm-skill":
        latest = latest_tag(rec["git_url"])
    elif rec["kind"] == "mcp-git":
        latest = latest_head(rec["git_url"])
    rec["latest"] = latest or "unresolved"
    if rec["kind"] == "mcp-git":
        rec["update"] = bool(latest) and not same_hash(rec["current"], latest)
    else:
        rec["update"] = bool(latest) and norm(latest) != norm(rec["current"])


def render_table(records):
    headers = ["KIND", "NAME", "CURRENT", "LATEST", "UPDATE"]
    rows = []
    for r in records:
        rows.append(
            [
                r["kind"],
                r["name"],
                short(r["current"]),
                short(r.get("latest", "?")),
                "yes"
                if r.get("update")
                else ("-" if r["spec"] != "latest" else "track"),
            ]
        )
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = []
    fmt = "  ".join("%-*s" for _ in headers)
    flat = []
    for i, h in enumerate(headers):
        flat.extend([widths[i], h])
    lines.append(fmt % tuple(flat))
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        flat = []
        for i, cell in enumerate(row):
            flat.extend([widths[i], cell])
        lines.append(fmt % tuple(flat))
    updates = sum(1 for r in records if r.get("update"))
    lines.append("")
    lines.append(
        "%d update(s) available out of %d pinned dependencies."
        % (updates, len(records))
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apm", default="apm.yml", help="path to apm.yml")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="print diagnostic messages"
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="inventory only, skip latest resolution",
    )
    parser.add_argument(
        "--models",
        action="store_true",
        help="list models from models.dev schema",
    )
    parser.add_argument(
        "--validate-models",
        action="store_true",
        help="validate apm.yml model whitelist entries against models.dev schema",
    )
    parser.add_argument(
        "--validate-duplicates",
        action="store_true",
        help="detect duplicate model entries in provider whitelists",
    )
    parser.add_argument(
        "--check-model",
        metavar="PROVIDER/MODEL",
        help="check if a model identifier exists in models.dev schema",
    )
    args = parser.parse_args(argv)

    if args.models:
        return list_models(json_mode=args.json)

    if args.check_model:
        return check_model(args.check_model)

    apm_path = Path(args.apm)
    if not apm_path.is_file():
        repo_root = run(["git", "rev-parse", "--show-toplevel"])
        if repo_root:
            fallback = Path(repo_root) / "apm.yml"
            if fallback.is_file():
                apm_path = fallback
            else:
                sys.stderr.write(
                    "error: apm.yml not found (tried %s and %s)\n"
                    % (args.apm, fallback)
                )
                return 2
        else:
            sys.stderr.write("error: apm.yml not found (tried %s)\n" % args.apm)
            return 2

    if args.validate_duplicates:
        return validate_duplicates(apm_path)

    if args.validate_models:
        return validate_apm_models(apm_path)

    records = detect(apm_path.read_text(encoding="utf-8"))

    if not args.no_network:
        for rec in records:
            resolve(rec, verbose=args.verbose)
    else:
        for rec in records:
            rec.setdefault("latest", "(skipped)")
            rec.setdefault("update", False)

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print(render_table(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())

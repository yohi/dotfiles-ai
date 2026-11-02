#!/usr/bin/env python3
"""Project selected OMO v1 routing into an advisory V2 migration snapshot.

The output never contains credentials, provider definitions or executable
plugins. OMO fallback/category logic is NOT installed as V2 runtime behavior.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = "dotfiles-ai/oc2-agent-routes/v1"
SOURCE = "opencode/omo.jsonc"
MAX_SOURCE = 256 * 1024
MAX_OUTPUT = 128 * 1024

# Native role adapters are intentionally narrower than full OMO functionality.
# In particular, Justice gate controllers are NOT imported as V2 agents.
ROLES = {
    "sisyphus": ("primary", "General coding and task coordination; OMO orchestration not installed."),
    "hephaestus": ("primary", "Focused software implementation; no OMO planning machinery."),
    "atlas": ("primary", "Task and execution coordination, without OMO todo hooks."),
    "prometheus": ("primary", "Prepare implementation plans without automatic delegation."),
    "oracle": ("subagent", "Advise on design decisions without modifying files."),
    "librarian": ("subagent", "Research code and documentation without modifying files."),
    "metis": ("subagent", "Assess ambiguities, risks and plans without modifying files."),
    "momus": ("subagent", "Review plans and changes without modifying files."),
}
READ_ONLY = frozenset({"oracle", "librarian", "metis", "momus"})
MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]*/[A-Za-z0-9._:/-]+$")
JSONC_TRAILING = re.compile(r'"(?:\\.|[^"\\])*"|,(\s*[}\]])', re.S)


class RouteError(ValueError):
    pass


def _jsonc(text: str) -> dict:
    # Strict JSON with comments and trailing commas; preserves quoted URLs.
    out: list[str] = []
    quoted = escaped = line = block = False
    i = 0
    while i < len(text):
        c = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if line:
            if c == "\n":
                line = False
                out.append(c)
            else:
                out.append(" ")
        elif block:
            if c == "*" and nxt == "/":
                block = False
                out.extend("  ")
                i += 1
            else:
                out.append("\n" if c == "\n" else " ")
        elif quoted:
            out.append(c)
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
            out.append(c)
        elif c == "/" and nxt == "/":
            line = True
            out.extend("  ")
            i += 1
        elif c == "/" and nxt == "*":
            block = True
            out.extend("  ")
            i += 1
        else:
            out.append(c)
        i += 1
    if quoted or block:
        raise RouteError("incomplete OMO JSONC")
    cleaned = JSONC_TRAILING.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(), "".join(out))
    try:
        doc = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RouteError("OMO source is not valid JSONC") from exc
    if not isinstance(doc, dict):
        raise RouteError("OMO root must be a mapping")
    return doc


def _model(value: object) -> str:
    if not isinstance(value, str) or not MODEL_RE.fullmatch(value):
        raise RouteError("OMO model ID is not a qualified provider/model")
    return value


def _candidate(value: object) -> dict:
    if isinstance(value, str):
        return {"model": _model(value)}
    if not isinstance(value, dict):
        raise RouteError("invalid OMO routing candidate")
    model = _model(value.get("model"))
    result = {"model": model}
    # OMO reasoning is not necessarily the V2 model variant; preserve as
    # advisory source metadata only, never copy it into active config.
    if "reasoning" in value:
        reasoning = value["reasoning"]
        if not isinstance(reasoning, str) or reasoning not in (
            "minimal", "low", "medium", "high", "xhigh", "max"
        ):
            raise RouteError("unknown OMO reasoning label")
        result["source_reasoning"] = reasoning
    return result


def _entry(value: object) -> dict:
    if not isinstance(value, dict):
        raise RouteError("invalid OMO routing entry")
    if value.get("disable") is True:
        return {"disabled": True}
    result = {"primary": _candidate(value)}
    fallback = value.get("fallback_models", [])
    if not isinstance(fallback, list) or len(fallback) > 12:
        raise RouteError("invalid OMO fallback list")
    result["fallback_candidates"] = [_candidate(x) for x in fallback]
    # Some categories also have models[]; preserve only the candidate data.
    variants = value.get("models", [])
    if not isinstance(variants, list) or len(variants) > 12:
        raise RouteError("invalid OMO model candidates")
    if variants:
        result["category_candidates"] = [_candidate(x) for x in variants]
    if isinstance(value.get("ultrawork"), dict):
        result["ultrawork_candidate"] = _candidate(value["ultrawork"])
    return result


def _routes(section: object) -> dict:
    if not isinstance(section, dict):
        raise RouteError("missing OMO profile")
    profiles = {}
    for group in ("agents", "categories"):
        items = section.get(group)
        if not isinstance(items, dict):
            raise RouteError("missing OMO " + group)
        if len(items) > 64:
            raise RouteError("oversized OMO route group")
        profiles[group] = {}
        for name, item in sorted(items.items()):
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name):
                raise RouteError("invalid OMO route ID")
            profiles[group][name] = _entry(item)
    return profiles


def build(repo: Path) -> tuple[dict, str]:
    source = repo / SOURCE
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_SOURCE:
        raise RouteError("OMO source missing, linked or oversized")
    raw = source.read_bytes()
    try:
        doc = _jsonc(raw.decode("utf-8"))
    except UnicodeError as exc:
        raise RouteError("OMO source must be UTF-8") from exc
    profiles = doc.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != {"personal", "work"}:
        raise RouteError("unsupported OMO profile structure")
    personal = _routes(doc.get("[opencode]"))
    work_override = profiles["work"]
    if not isinstance(work_override, dict):
        raise RouteError("invalid work profile")
    work = _routes(work_override.get("[opencode]"))
    # Do not inherit personal fallback models into work's Bedrock-only policy.
    if set(personal["agents"]) != set(work["agents"]):
        raise RouteError("work agent routes incomplete")
    if set(personal["categories"]) != set(work["categories"]):
        raise RouteError("work category routes incomplete")
    for routes in work.values():
        for row in routes.values():
            for candidate in (
                [row["primary"]] + row.get("fallback_candidates", [])
                + row.get("category_candidates", [])
            ) if "primary" in row else []:
                if not candidate["model"].startswith("amazon-bedrock/"):
                    raise RouteError("work route escapes Bedrock-only profile")
    for role in ROLES:
        if role not in personal["agents"] or role not in work["agents"]:
            raise RouteError("required OMO role missing")
    native = {}
    for role, (mode, description) in ROLES.items():
        item = {"description": description, "mode": mode}
        if role in READ_ONLY:
            item["permissions"] = [
                {"action": "edit", "resource": "*", "effect": "deny"},
                {"action": "shell", "resource": "*", "effect": "deny"},
            ]
        native[role] = item
    payload = {
        "schema": SCHEMA,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "default_agent": "sisyphus",
        "native_agents": native,
        "routing_activation": "disabled-no-provider-broker",
        "routes": {"personal": personal, "work": work},
        "limitations": [
            "OMO plugin, hooks, team mode, category router and fallbacks not installed",
            "Model IDs are advisory and are never copied into active V2 agents",
            "Justice review/gate authority is not delegated to these agents",
        ],
    }
    encoded = (json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > MAX_OUTPUT:
        raise RouteError("routing snapshot too large")
    return payload, hashlib.sha256(encoded).hexdigest()

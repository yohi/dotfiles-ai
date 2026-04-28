# APM Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate dotfiles-ai from custom sync scripts to Microsoft APM for declarative, portable AI agent configuration.

**Architecture:** Use APM (`apm.yml`) as the Single Source of Truth for dependencies and client config injection, while retaining Docker MCP Gateway for backend server management.

**Tech Stack:** Microsoft APM, Python, Makefile, Bash

---

### Task 1: Create APM Manifest

**Files:**
- Create: `apm.yml`

- [ ] **Step 1: Write the `apm.yml` configuration**

```yaml
# apm.yml
name: dotfiles-ai
version: 1.0.0
description: "AI Agent settings, skills, and unified MCP configuration for dotfiles"

dependencies:
  apm:
    - "obra/superpowers#main"
    - "anthropics/skills#main"

  mcp:
    - name: docker-mcp-gateway
      transport: sse
      url: "http://127.0.0.1:10888/sse"

exports:
  skills:
    - "agent-skills/**"

hooks:
  post_install:
    - command: "make sync-mcp"
      description: "Re-rendering Docker MCP Gateway backend configs and restarting service."
```

- [ ] **Step 2: Commit**

```bash
git add apm.yml
git commit -m "feat: add apm manifest for centralized agent configuration"
```

---

### Task 2: Delete Obsolete Files

**Files:**
- Delete: Multiple obsolete files replaced by APM

- [ ] **Step 1: Remove external skills manager and templates**

```bash
git rm agent-skills/EXTERNAL_SKILLS.md
git rm _scripts/install-external-skills.sh
git rm _scripts/sync-mcp-configs.sh
git rm claude/settings.json.template
git rm gemini/settings.json.template
git rm ide/cursor/mcp.json.template
git rm ide/vscode/settings.json.template
# If these files don't exist because of earlier cleanup, use rm -f and ignore git rm errors
```

- [ ] **Step 2: Remove obsolete Makefiles**

```bash
git rm _mk/superpowers.mk
```

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove obsolete scripts and templates replaced by apm"
```

---

### Task 3: Refactor Gateway Config Renderer

**Files:**
- Modify: `_scripts/render-mcp-configs.py`

- [ ] **Step 1: Overwrite python script to remove client config generation**

```bash
cat << 'EOF' > _scripts/render-mcp-configs.py
#!/usr/bin/env python3

from __future__ import annotations
import os
import re
import sys
from pathlib import Path
from typing import Any, cast, Match, Dict, List
import yaml

def get_gateway_token() -> str:
    token = os.environ.get("MCP_GATEWAY_TOKEN")
    if not token:
        repo_root = Path(__file__).parent.parent.resolve()
        env_path = repo_root / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            match = re.search(r"^\s*MCP_GATEWAY_TOKEN\s*=\s*(.+)$", content, re.MULTILINE)
            if match:
                token = match.group(1).strip().strip('"').strip("'")
    return token or ""

def load_client_config() -> dict[str, Any]:
    repo_root = Path(__file__).parent.parent.resolve()
    servers_yaml_path = repo_root / "mcp" / "servers.yaml"
    if not servers_yaml_path.exists():
        return {}
    with servers_yaml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
        if isinstance(data, dict):
            return cast(Dict[str, Any], data)
        return {}

def replace_placeholders(data: Any, gateway_url: str, expand_paths: bool = False) -> Any:
    home = str(Path.home())
    repo_root = str(Path(__file__).parent.parent.resolve())
    program_dir = os.environ.get("PROGRAM_DIR", str(Path.home() / "program" / "private"))

    if isinstance(data, dict):
        return {k: replace_placeholders(v, gateway_url, expand_paths) for k, v in data.items()}
    if isinstance(data, list):
        return [replace_placeholders(v, gateway_url, expand_paths) for v in data]
    if isinstance(data, str):
        s = data.replace("__GATEWAY_URL__", gateway_url)
        s = s.replace("__HOME__", home)
        s = s.replace("__REPO_ROOT__", repo_root)
        s = s.replace("__PROGRAM__", program_dir)

        def _get_env(m: Match[str]) -> str:
            var_name = m.group(1)
            default_val = m.group(2)
            val = os.environ.get(var_name)
            if val is not None:
                return cast(str, val)
            if default_val is not None:
                return cast(str, default_val)
            raise ValueError(f"Required environment variable '${var_name}' is not set and has no default value.")

        s = re.sub(r"\${(\w+)(?::-([^}]+))?}", _get_env, s)

        if expand_paths:
            if s.startswith("/") or s.startswith("~"):
                s = str(Path(s).expanduser().resolve())
        return cast(str, s)
    return data

def main() -> int:
    repo_root = Path(__file__).parent.parent.resolve()
    servers_yaml_path = repo_root / "mcp" / "servers.yaml"
    
    config = load_client_config()
    if not config:
        print(f"Error: {servers_yaml_path} not found or empty.")
        return 1

    defaults = cast(Dict[str, Any], config.get("defaults", {}))
    gateway_url = cast(str, defaults.get("gateway_url", "http://127.0.0.1:10888/sse"))

    all_servers_raw = cast(Dict[str, Any], config.get("servers", {}))
    gateway_servers_raw = cast(Dict[str, Any], replace_placeholders(all_servers_raw, gateway_url))
    
    gateway_servers: dict[str, Any] = {}
    for name, cfg in gateway_servers_raw.items():
        if isinstance(cfg, dict) and cfg.get("type") in ["server", "local"]:
            srv = {k: v for k, v in cfg.items() if k not in ["title", "description"]}
            gateway_servers[name] = srv

    gateway_config = {
        "mcpServers": gateway_servers,
        "gateway": {"enabled_servers": list(gateway_servers.keys())},
    }
    
    config_yaml_path = repo_root / "mcp" / "config.yaml"
    config_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    config_yaml_path.write_text(
        yaml.dump(gateway_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    catalog_servers: dict[str, Any] = {}
    enabled_servers = cast(List[str], gateway_config["gateway"]["enabled_servers"])
    for name in enabled_servers:
        if name in all_servers_raw:
            catalog_servers[name] = replace_placeholders(all_servers_raw[name], gateway_url, expand_paths=True)

    catalog_config = {
        "version": 3,
        "name": "custom",
        "displayName": "Custom Servers",
        "registry": catalog_servers,
    }
    
    registry = cast(Dict[str, Any], catalog_config["registry"])
    for name, cfg in registry.items():
        if isinstance(cfg, dict):
            if "title" not in cfg:
                cfg["title"] = name.capitalize()
            if "description" not in cfg:
                cfg["description"] = f"Custom MCP server: {name}"

    catalog_yaml_path = repo_root / "mcp" / "catalogs" / "custom.yaml"
    catalog_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_yaml_path.write_text(
        yaml.dump(catalog_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    print("✅ Gateway backend configuration rendered successfully.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"render-mcp-configs: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
EOF
```

- [ ] **Step 2: Verify the script executes successfully**

```bash
python3 _scripts/render-mcp-configs.py
```
Expected: "✅ Gateway backend configuration rendered successfully."

- [ ] **Step 3: Commit**

```bash
git add _scripts/render-mcp-configs.py
git commit -m "refactor: remove client config rendering logic, keep gateway only"
```

---

### Task 4: Refactor Makefile Workflow

**Files:**
- Modify: `_mk/main.mk`

- [ ] **Step 1: Replace setup target in `_mk/main.mk`**

Use sed to completely rewrite the `setup:` block to use `apm install` instead of `setup-agents setup-ides`.

```bash
sed -i '/^setup:/,/^$/c\setup: install-requirements\n\t$(Q_ECHO) "🚀 APMによるエージェント設定の自動セットアップを実行中..."\n\t@if command -v apm >/dev/null 2>&1; then \\\n\t\tapm install; \\\n\telse \\\n\t\techo "❌ APMがインストールされていません。 https://github.com/microsoft/apm に従いインストールしてください。"; \\\n\t\texit 1; \\\n\tfi\n\t$(Q_ECHO) "✅ dotfiles-ai のコア設定が適用されました"\n' _mk/main.mk
```

- [ ] **Step 2: Clean up obsolete Makefile includes**

Remove the `include _mk/superpowers.mk` line since the file was deleted.

```bash
sed -i '/-include _mk\/superpowers.mk/d' _mk/main.mk
```

- [ ] **Step 3: Test Make Setup**

```bash
make setup
```
Expected: Should run `apm install` and complete without failing on missing superpower includes or agents setups. *(Note: If APM is not installed locally, it will exit 1 with the message. This is expected behavior).*

- [ ] **Step 4: Commit**

```bash
git add _mk/main.mk
git commit -m "refactor: transition make setup to trigger apm install"
```

# APM Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate dotfiles-ai from custom sync scripts to Microsoft APM for declarative, portable AI agent configuration.

**Architecture:** Use APM (`apm.yml`) as the Single Source of Truth for dependencies and client config injection, while retaining Docker MCP Gateway for backend server management.

**Tech Stack:** Microsoft APM, Python, Makefile, Bash

---

## Task 1: Create APM Manifest

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
    - "obra/superpowers#6efe32c9e2dd002d0c394e861e0529675d1ab32e"
    - "anthropics/skills#5128e1865d670f5d6c9cef000e6dfc4e951fb5b9"

  mcp:
    - name: docker-mcp-gateway
      transport: sse
      url: "http://127.0.0.1:10888/sse"

scripts:
  sync-mcp: "make sync-mcp"
```

- [ ] **Step 2: Commit**

```bash
git add apm.yml
git commit -m "feat: add apm manifest for centralized agent configuration"
```

---

## Task 2: Delete Obsolete Files

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

## Task 3: Refactor Gateway Config Renderer

**Files:**
- Modify: `_scripts/render-mcp-configs.py`

- [ ] **Step 1: Overwrite python script to remove client config generation**

Note: `get_gateway_token()` has been removed. The token should be provided via environment variables (`MCP_GATEWAY_TOKEN`).

```bash
cat << 'EOF' > _scripts/render-mcp-configs.py
#!/usr/bin/env python3

from __future__ import annotations
import os
import re
import sys
import shutil
from pathlib import Path
from typing import Any, cast, Match, Dict, List
import yaml

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

def deploy_systemd_service(src_path: Path, dest_dir: Path, repo_root: str, enabled_servers: str) -> None:
    if not src_path.exists():
        return
    
    content = src_path.read_text(encoding="utf-8")
    content = content.replace("__REPO_ROOT__", repo_root)
    content = content.replace("__ENABLED_SERVERS__", enabled_servers)
    
    dest_path = dest_dir / src_path.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(content, encoding="utf-8")
    print(f"  -> Deployed {src_path.name} to {dest_path}")

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
    
    # Filter candidates first to avoid unnecessary placeholder expansion failures
    gateway_candidates = {
        name: cfg for name, cfg in all_servers_raw.items()
        if isinstance(cfg, dict) and cfg.get("type") in ["server", "local"]
    }
    gateway_servers_expanded = cast(Dict[str, Any], replace_placeholders(gateway_candidates, gateway_url))
    
    gateway_servers: dict[str, Any] = {}
    for name, cfg in gateway_servers_expanded.items():
        srv = {k: v for k, v in cfg.items() if k not in ["title", "description"]}
        gateway_servers[name] = srv

    enabled_servers_list = list(gateway_servers.keys())
    gateway_config = {
        "mcpServers": gateway_servers,
        "gateway": {"enabled_servers": enabled_servers_list},
    }
    
    # Render config.yaml
    config_yaml_path = repo_root / "mcp" / "config.yaml"
    config_yaml_path.parent.mkdir(parents=True, exist_ok=True)
    config_yaml_path.write_text(
        yaml.safe_dump(gateway_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # Render catalogs/custom.yaml
    catalog_servers: dict[str, Any] = {}
    for name in enabled_servers_list:
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
        yaml.safe_dump(catalog_config, indent=2, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    print("✅ Gateway backend configuration rendered locally.")

    # Deployment to ~/.docker/mcp
    dot_docker_mcp = Path.home() / ".docker" / "mcp"
    dot_docker_mcp.mkdir(parents=True, exist_ok=True)
    
    # Copy config.yaml
    shutil.copy2(config_yaml_path, dot_docker_mcp / "config.yaml")
    
    # Catalogs directory symlink/setup
    dot_docker_catalogs = dot_docker_mcp / "catalogs"
    dot_docker_catalogs.mkdir(parents=True, exist_ok=True)
    
    # Create symlink for custom.yaml
    custom_catalog_dest = dot_docker_catalogs / "custom.yaml"
    if custom_catalog_dest.is_symlink() or custom_catalog_dest.exists():
        custom_catalog_dest.unlink()
    custom_catalog_dest.symlink_to(catalog_yaml_path)
    
    # Bootstrap symlink if it exists in repo
    bootstrap_src = repo_root / "mcp" / "catalogs" / "bootstrap.yaml"
    if bootstrap_src.exists():
        bootstrap_dest = dot_docker_catalogs / "bootstrap.yaml"
        if bootstrap_dest.is_symlink() || bootstrap_dest.exists():
            bootstrap_dest.unlink()
        bootstrap_dest.symlink_to(bootstrap_src)

    print(f"✅ Configs deployed to {dot_docker_mcp}")

    # Deploy systemd services
    systemd_user_dir = Path.home() / ".config" / "systemd" / "user"
    enabled_servers_str = ",".join(enabled_servers_list)
    
    deploy_systemd_service(
        repo_root / "mcp" / "docker-mcp-gateway.service",
        systemd_user_dir,
        str(repo_root),
        enabled_servers_str
    )
    deploy_systemd_service(
        repo_root / "mcp" / "mcp-watchdog.service",
        systemd_user_dir,
        str(repo_root),
        enabled_servers_str
    )

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
Expected: "✅ Gateway backend configuration rendered locally."

- [ ] **Step 3: Commit**

```bash
git add _scripts/render-mcp-configs.py
git commit -m "refactor: remove client config rendering logic, keep gateway only"
```

---

## Task 4: Refactor Makefile Workflow

**Files:**
- Modify: `_mk/main.mk`

- [ ] **Step 1: Replace setup target in `_mk/main.mk`**

Perform a manual edit of the `setup` target in `_mk/main.mk`. Use the markers below to identify the block.

**Before:**
```makefile
setup: install-requirements
	$(Q_ECHO) "🚀 APMによるエージェント設定の自動セットアップを実行中..."
	@if command -v apm >/dev/null 2>&1; then \
		apm install; \
	else \
		echo "❌ APMがインストールされていません。 https://github.com/microsoft/apm に従いインストールしてください。"; \
		exit 1; \
	fi
	$(Q_ECHO) "✅ dotfiles-ai のコア設定が適用されました"
```

**After:**
```makefile
# APM-SETUP-BEGIN
setup: install-requirements
	$(Q_ECHO) "🚀 APMによるエージェント設定の自動セットアップを実行中..."
	@if command -v apm >/dev/null 2>&1; then \
		apm install; \
	else \
		echo "❌ APMがインストールされていません。 https://github.com/microsoft/apm に従いインストールしてください。"; \
		exit 1; \
	fi
	@$(MAKE) sync-agents
	$(Q_ECHO) "✅ dotfiles-ai のコア設定が適用されました"
# APM-SETUP-END
```

- [ ] **Step 2: Clean up obsolete Makefile includes**

Remove the `-include _mk/superpowers.mk` line since the file was deleted.

- [ ] **Step 3: Test Make Setup**

```bash
make setup
```
Expected: Should run `apm install` and `make sync-agents` and complete without failing on missing superpower includes or agents setups.

- [ ] **Step 4: Commit**

```bash
git add _mk/main.mk
git commit -m "refactor: transition make setup to trigger apm install"
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

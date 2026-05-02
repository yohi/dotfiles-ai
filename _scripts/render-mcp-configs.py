#!/usr/bin/env python3

from __future__ import annotations
import os
import json
import re
import shutil
from pathlib import Path
from typing import Any, cast, Match, Dict
import yaml

json5: Any
try:
    import json5
except ImportError:
    json5 = None


def load_client_config() -> dict[str, Any]:
    repo_root = Path(__file__).parent.parent.resolve()
    apm_yaml_path = repo_root / "apm.yml"
    if not apm_yaml_path.exists():
        return {}
    with apm_yaml_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return cast(Dict[str, Any], data) if isinstance(data, dict) else {}


def replace_placeholders(
    data: Any, gateway_url: str, expand_paths: bool = False
) -> Any:
    home = str(Path.home())
    repo_root = str(Path(__file__).parent.parent.resolve())
    program_dir = os.environ.get("PROGRAM_DIR")
    if not program_dir:
        cg_path = os.environ.get("CHRONOS_GRAPH_PATH")
        if cg_path:
            program_dir = str(Path(cg_path).expanduser().parent)
        else:
            program_dir = str(Path.home() / "program" / "private")

    if isinstance(data, dict):
        return {
            k: replace_placeholders(v, gateway_url, expand_paths)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [replace_placeholders(v, gateway_url, expand_paths) for v in data]
    if isinstance(data, str):
        s = (
            data.replace("__GATEWAY_URL__", gateway_url)
            .replace("__HOME__", home)
            .replace("__REPO_ROOT__", repo_root)
            .replace("__PROGRAM__", program_dir)
        )

        def _get_env(m: Match[str]) -> str:
            v, d = m.group(1), m.group(2)
            val = os.environ.get(v)
            if val is not None:
                return cast(str, val)
            if d is not None:
                return cast(str, d)
            return ""

        s = re.sub(r"\${(\w+)(?::-([^}]*))?}", _get_env, s)
        if expand_paths and (s.startswith("/") or s.startswith("~")):
            s = str(Path(s).expanduser().resolve())
        return cast(str, s)
    return data


def deploy_systemd_service(
    src_path: Path, dest_dir: Path, repo_root: str, enabled_servers: str
) -> None:
    if not src_path.exists():
        return
    content = (
        src_path.read_text(encoding="utf-8")
        .replace("__REPO_ROOT__", repo_root)
        .replace("__ENABLED_SERVERS__", enabled_servers)
    )
    dest_path = dest_dir / src_path.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(content, encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).parent.parent.resolve()
    config = load_client_config()
    if not config:
        return 1

    app_config = cast(Dict[str, Any], config.get("config", {}))
    combined_mcp_list = config.get("dependencies", {}).get("mcp", []) + app_config.get(
        "mcp_gateway", []
    )
    all_servers_raw = {
        s["name"]: s for s in combined_mcp_list if isinstance(s, dict) and "name" in s
    }

    defaults = cast(Dict[str, Any], app_config.get("defaults", {}))
    gateway_url = cast(str, defaults.get("gateway_url", "http://127.0.0.1:10888/sse"))

    gateway_candidates = {
        n: s
        for n, s in all_servers_raw.items()
        if s.get("type") in ["server", "stdio"] or s.get("transport") == "stdio"
    }

    def std_for_gateway(srv_dict):
        res = {}
        for n, c in srv_dict.items():
            s = c.copy()
            if "transport" in s and "type" not in s:
                s["type"] = s.pop("transport")
            s = {
                k: v
                for k, v in s.items()
                if k not in ["title", "description", "name", "registry", "port"]
            }
            if "env" in s and isinstance(s["env"], dict):
                s["env"] = [{"name": k, "value": v} for k, v in s["env"].items()]
            if "command" in s and isinstance(s["command"], str):
                s["command"] = [s["command"]]
            res[n] = s
        return res

    gateway_servers = replace_placeholders(
        std_for_gateway(gateway_candidates), gateway_url, expand_paths=True
    )
    mcp_dir = repo_root / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    (mcp_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "mcpServers": gateway_servers,
                "gateway": {"enabled_servers": list(gateway_servers.keys())},
            },
            indent=2,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    catalog_servers = {}
    for n, sd in all_servers_raw.items():
        s = replace_placeholders(sd, gateway_url, expand_paths=True)
        s["name"] = n
        if "transport" in s and "type" not in s:
            s["type"] = s.pop("transport")
        if "env" in s and isinstance(s["env"], dict):
            s["env"] = [{"name": k, "value": v} for k, v in s["env"].items()]
        if "command" in s and isinstance(s["command"], str):
            s["command"] = [s["command"]]
        catalog_servers[n] = s
    (mcp_dir / "catalogs" / "custom.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 3,
                "name": "custom",
                "displayName": "Custom Servers",
                "registry": catalog_servers,
            },
            indent=2,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    dot_docker = Path.home() / ".docker" / "mcp"
    dot_docker.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mcp_dir / "config.yaml", dot_docker / "config.yaml")
    (dot_docker / "catalogs").mkdir(parents=True, exist_ok=True)
    target = dot_docker / "catalogs" / "custom.yaml"
    if target.exists():
        target.unlink()
    target.symlink_to(mcp_dir / "catalogs" / "custom.yaml")

    sys_dir = Path.home() / ".config" / "systemd" / "user"
    deploy_systemd_service(
        mcp_dir / "docker-mcp-gateway.service",
        sys_dir,
        str(repo_root),
        ",".join(gateway_servers.keys()),
    )
    deploy_systemd_service(
        mcp_dir / "mcp-watchdog.service",
        sys_dir,
        str(repo_root),
        ",".join(gateway_servers.keys()),
    )

    agents_config = app_config.get("agents", {})
    if not isinstance(agents_config, dict):
        print(
            f"  ⚠️ Warning: 'agents' in config must be a mapping, got {type(agents_config).__name__}"
        )
        agents_config = {}

    for an, ac in agents_config.items():
        if not isinstance(ac, dict):
            continue
        ps = replace_placeholders(ac.get("path", ""), gateway_url, expand_paths=True)
        cp = repo_root / ps if not ps.startswith("/") else Path(ps).expanduser()
        if not cp.exists():
            continue
        rk = ac.get("root_key", "mcpServers")
        ms_raw = ac.get("servers", [])
        ms = {n: {"inherit": n} for n in ms_raw} if isinstance(ms_raw, list) else ms_raw
        aservs = {}
        for sn, mp in ms.items():
            inherit_name = mp.get("inherit", sn)
            inv = all_servers_raw.get(inherit_name)
            if isinstance(inv, dict):
                s = replace_placeholders(inv.copy(), gateway_url, expand_paths=True)
                if sn == "docker-mcp":
                    s["type"] = "sse"
                else:
                    # Bridge to unified gateway if it's a local/container server
                    if (
                        s.get("type") in ["stdio", "server", "local"]
                        or s.get("transport") == "stdio"
                    ):
                        s["type"] = "remote" if an == "opencode" else "sse"
                        s["url"] = f"{gateway_url}?server={sn}"
                        for k in [
                            "command",
                            "args",
                            "env",
                            "image",
                            "volumes",
                            "transport",
                            "port",
                            "registry",
                        ]:
                            s.pop(k, None)
                for k in [
                    "title",
                    "description",
                    "_generated_by",
                    "name",
                    "registry",
                    "transport",
                ]:
                    s.pop(k, None)
                if an == "opencode":
                    if s.get("type") == "sse":
                        s["type"] = "remote"
                    s["enabled"] = True
                aservs[sn] = s
        h = aservs.get("docker-mcp", {}).get("headers")
        if h:
            for s in aservs.values():
                if s.get("url") and s["url"].startswith(gateway_url):
                    s["headers"] = h
        try:
            txt = cp.read_text(encoding="utf-8")
            if ac.get("format", "json") in ["json", "opencode_jsonc"]:
                if json5 and (ac.get("format") == "opencode_jsonc" or "//" in txt):
                    d = json5.loads(txt)
                else:
                    d = json.loads(txt)
                d[rk] = aservs
                cp.write_text(
                    json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                print(f"  ✅ Updated: {cp}")
            elif ac.get("format") == "toml":
                import toml

                d = toml.loads(txt)
                d[rk] = aservs
                cp.write_text(toml.dumps(d), encoding="utf-8")
        except Exception as e:
            print(f"  ❌ Error {cp}: {e}")
    return 0


if __name__ == "__main__":
    main()

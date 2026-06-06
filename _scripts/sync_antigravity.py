import json
import os
import re
import shutil
import sys
from typing import Any
import yaml


def replace_env_vars(val: Any) -> Any:
    """Recursively expand environment variables in strings, lists, and dicts.

    Args:
        val: The value to process.

    Returns:
        The processed value with environment variables resolved.
    """
    if isinstance(val, str):
        # Match both ${env:VAR} and $VAR or ${VAR}
        matches = re.findall(r"\$\{env:([^}]+)\}", val)
        for var in matches:
            val = val.replace(f"${{env:{var}}}", os.environ.get(var, ""))
        # Standard env expansion
        val = os.path.expandvars(val)

        # Scan for remaining unresolved $VAR or ${VAR} syntax and replace with "" (or warning)
        unresolved_braced = re.findall(r"\$\{([^}]+)\}", val)
        for var in unresolved_braced:
            # Skip if it looks like a prefix/other template format, otherwise treat as env var
            if ":" not in var:
                val = val.replace(f"${{{var}}}", os.environ.get(var, ""))

        unresolved_simple = re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", val)
        for var in unresolved_simple:
            val = val.replace(f"${var}", os.environ.get(var, ""))
    elif isinstance(val, dict):
        return {k: replace_env_vars(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [replace_env_vars(x) for x in val]
    return val


def convert_lockfile(lockfile_path: str, output_path: str) -> None:
    """Convert the yaml lockfile to Antigravity's mcp_config.json format.

    Args:
        lockfile_path: Path to the YAML lockfile.
        output_path: Path to write the JSON configuration.

    Raises:
        FileNotFoundError: If lockfile_path does not exist.
        ValueError: If lock_data is not a dictionary.
        RuntimeError: If command resolution fails for 'uvx' or 'npx'.
    """
    if not os.path.exists(lockfile_path):
        raise FileNotFoundError(f"Error: {lockfile_path} not found.")

    with open(lockfile_path, "r", encoding="utf-8") as f:
        lock_data = yaml.safe_load(f)

    if not isinstance(lock_data, dict):
        raise ValueError("Invalid lockfile format: lock_data must be a mapping/dict.")

    mcp_configs = lock_data.get("mcp_configs", {})
    mcp_servers = {}

    for name, cfg in mcp_configs.items():
        # Clean config representation for Antigravity
        server_cfg = {}
        if "command" in cfg:
            server_cfg["command"] = cfg["command"]
        if "args" in cfg:
            server_cfg["args"] = cfg["args"]
        if "env" in cfg:
            server_cfg["env"] = cfg["env"]
        if "url" in cfg:
            server_cfg["serverUrl"] = cfg["url"]
        if "headers" in cfg:
            server_cfg["headers"] = cfg["headers"]

        # Standardize command path resolving for typical environment executables
        if "command" in server_cfg and server_cfg["command"] == "uvx":
            resolved_path = shutil.which("uvx")
            if resolved_path:
                server_cfg["command"] = resolved_path
            else:
                # Add cross-platform fallback paths (Windows friendly paths included)
                candidates = [
                    os.path.expanduser("~/.local/bin/uvx"),
                    "/usr/local/bin/uvx",
                    "/usr/bin/uvx",
                ]
                if os.name == "nt":
                    candidates.extend(
                        [
                            os.path.expandvars("%LOCALAPPDATA%\\Programs\\uv\\uvx.exe"),
                            os.path.expandvars("%USERPROFILE%\\.local\\bin\\uvx.exe"),
                        ]
                    )

                found = False
                for path in candidates:
                    normalized = os.path.normpath(path)
                    if os.path.exists(normalized):
                        server_cfg["command"] = normalized
                        found = True
                        break
                if not found:
                    raise RuntimeError("command resolution failed for 'uvx'")

        elif "command" in server_cfg and server_cfg["command"] == "npx":
            resolved_path = shutil.which("npx")
            if resolved_path:
                server_cfg["command"] = resolved_path
            else:
                # Add cross-platform fallback paths (Windows friendly paths included)
                candidates = [
                    os.path.expanduser("~/.linuxbrew/bin/npx"),
                    "/usr/local/bin/npx",
                    "/usr/bin/npx",
                ]
                if os.name == "nt":
                    candidates.extend(
                        [
                            os.path.expandvars("%APPDATA%\\npm\\npx.cmd"),
                            "C:\\Program Files\\nodejs\\npx.cmd",
                        ]
                    )

                found = False
                for path in candidates:
                    normalized = os.path.normpath(path)
                    if os.path.exists(normalized):
                        server_cfg["command"] = normalized
                        found = True
                        break
                if not found:
                    raise RuntimeError("command resolution failed for 'npx'")

        # Apply environment variable replacement
        mcp_servers[name] = replace_env_vars(server_cfg)

    output_data = {"mcpServers": mcp_servers}

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print(f"Successfully generated {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--lockfile", default="apm.lock.yaml")
    parser.add_argument("--output", default="antigravity/mcp_config.json")
    args = parser.parse_args()
    try:
        convert_lockfile(args.lockfile, args.output)
    except (FileNotFoundError, yaml.YAMLError, RuntimeError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

import json
import os
import re
import shutil
import sys
from typing import Any
import yaml


FALLBACK_COMMAND_PATHS = {
    "uvx": {
        "posix": [
            "~/.local/bin/uvx",
            "/usr/local/bin/uvx",
            "/usr/bin/uvx",
        ],
        "nt": [
            "%LOCALAPPDATA%\\Programs\\uv\\uvx.exe",
            "%USERPROFILE%\\.local\\bin\\uvx.exe",
        ],
    },
    "npx": {
        "posix": [
            "~/.linuxbrew/bin/npx",
            "/usr/local/bin/npx",
            "/usr/bin/npx",
        ],
        "nt": [
            "%APPDATA%\\npm\\npx.cmd",
            "C:\\Program Files\\nodejs\\npx.cmd",
        ],
    },
}


def command_candidates(command: str) -> list[str]:
    """Return possible filesystem candidate paths for a given command.

    Looks up fallback path candidates for known commands (e.g., 'uvx', 'npx')
    in FALLBACK_COMMAND_PATHS. On POSIX systems, returns the 'posix' paths.
    On Windows (os.name == 'nt'), extends the list with 'nt' paths.

    All returned paths are expanded with os.path.expanduser and
    os.path.expandvars.

    Args:
        command: The command name to look up.

    Returns:
        A list of expanded filesystem paths that may contain the command.

    Raises:
        KeyError: If command is not present in FALLBACK_COMMAND_PATHS.

    Example:
        >>> command_candidates("uvx")
        ['/home/user/.local/bin/uvx', '/usr/local/bin/uvx', '/usr/bin/uvx']
    """
    paths = FALLBACK_COMMAND_PATHS[command]["posix"].copy()
    if os.name == "nt":
        paths.extend(FALLBACK_COMMAND_PATHS[command]["nt"])
    return [os.path.expandvars(os.path.expanduser(path)) for path in paths]


def resolve_command(command: str) -> str:
    """Resolve an executable path from a command name.

    Attempts to locate the executable using shutil.which. If not found,
    falls back to checking candidate paths returned by command_candidates().
    Candidate paths are normalized with os.path.normpath and verified with
    os.path.exists.

    Args:
        command: The command name to resolve.

    Returns:
        The resolved absolute or relative path to the executable.

    Raises:
        RuntimeError: If the command cannot be resolved.

    Example:
        >>> resolve_command("uvx")  # if uvx is on PATH
        '/usr/local/bin/uvx'
    """
    resolved_path = shutil.which(command)
    if resolved_path:
        return resolved_path

    for path in command_candidates(command):
        normalized = os.path.normpath(path)
        if os.path.exists(normalized):
            return normalized

    raise RuntimeError(f"command resolution failed for '{command}'")


def _replace_env_in_string(val: str) -> str:
    """Expand environment variables in a single string value."""
    # Match ${env:VAR} (APM-specific format)
    for var in re.findall(r"\$\{env:([^}]+)\}", val):
        val = val.replace(f"${{env:{var}}}", os.environ.get(var, ""))

    # Standard env expansion for $VAR / ${VAR}
    val = os.path.expandvars(val)

    # Fallback: replace any remaining ${VAR} with "" if it is a simple identifier.
    for var in re.findall(r"\$\{([^}]+)\}", val):
        if ":" not in var:
            val = val.replace(f"${{{var}}}", os.environ.get(var, ""))

    # Fallback: replace any remaining $VAR with "".
    for var in re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", val):
        val = val.replace(f"${var}", os.environ.get(var, ""))

    return val


def replace_env_vars(val: Any) -> Any:
    """Recursively expand environment variables in strings, lists, and dicts."""
    if isinstance(val, str):
        return _replace_env_in_string(val)
    elif isinstance(val, dict):
        return {k: replace_env_vars(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [replace_env_vars(x) for x in val]
    return val


def _build_server_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Extract and normalize a single server configuration for Antigravity."""
    server_cfg: dict[str, Any] = {}
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
    if server_cfg.get("command") in FALLBACK_COMMAND_PATHS:
        server_cfg["command"] = resolve_command(server_cfg["command"])

    return replace_env_vars(server_cfg)


def _write_json_config(output_data: dict[str, Any], output_path: str) -> None:
    """Write JSON data to output_path, creating parent directories if needed."""
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)


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
    mcp_servers = {
        name: _build_server_config(cfg) for name, cfg in mcp_configs.items()
    }

    output_data = {"mcpServers": mcp_servers}
    _write_json_config(output_data, output_path)
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

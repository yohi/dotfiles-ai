#!/usr/bin/env python3
"""Environment configuration setup helper script."""
import os
import sys
import re
import getpass

def is_secret(key: str) -> bool:
    """Check if the environment variable key represents a sensitive secret.

    Args:
        key: The environment variable name.

    Returns:
        True if the key is sensitive, False otherwise.
    """
    key_lower = key.lower()
    return any(x in key_lower for x in ["key", "token", "secret", "password"])

def load_env(filepath: str) -> dict[str, str]:
    """Load existing environment variables from a file.

    Args:
        filepath: Path to the .env file.

    Returns:
        A dictionary mapping keys to values.
    """
    env: dict[str, str] = {}
    if not os.path.exists(filepath):
        return env
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Match KEY=VALUE (allow optional export prefix)
            match = re.match(r"^(?:export\s+)?([\w_]+)=(.*)$", line)
            if match:
                key, val = match.groups()
                # strip quotes if present
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                env[key] = val
    return env

def parse_example_keys(filepath: str) -> list[str]:
    """Parse environment variable keys defined in the example file.

    Args:
        filepath: Path to the .env.example file.

    Returns:
        A list of variable names.
    """
    keys: list[str] = []
    if not os.path.exists(filepath):
        return keys
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Match lines like:
            # KEY=VALUE
            # or commented out variables:
            # # KEY=VALUE (but skip general comments)
            match = re.match(r"^(?:#\s*)?(?:export\s+)?([\w_]+)=(.*)$", line)
            if match:
                key = match.group(1)
                # Skip common postgres placeholder/defaults if they are not real keys
                if key not in keys:
                    keys.append(key)
    return keys

def resolve_default_value(key: str, existing_env: dict[str, str]) -> str:
    """Resolve the default value for a key, checking existing env and fallback files/commands.

    Args:
        key: The variable name.
        existing_env: A dictionary of already configured variables.

    Returns:
        The resolved default value as a string.
    """
    current_val = existing_env.get(key, "").strip()
    
    if not current_val:
        current_val = os.environ.get(key, "").strip()
        
    if not current_val and key in ["GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"]:
        # Fallback A: ~/.gh_token
        gh_token_path = os.path.expanduser("~/.gh_token")
        if os.path.exists(gh_token_path):
            try:
                with open(gh_token_path, "r", encoding="utf-8") as gtf:
                    current_val = gtf.read().strip()
            except Exception:
                pass
        # Fallback B: gh auth token
        if not current_val:
            try:
                import subprocess
                res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
                current_val = res.stdout.strip()
            except Exception:
                pass
    return current_val

def collect_interactive_inputs(example_keys: list[str], existing_env: dict[str, str]) -> dict[str, str]:
    """Interactively prompt user for each environment variable value.

    Args:
        example_keys: List of keys defined in example file.
        existing_env: Dict of currently configured variables.

    Returns:
        A dict of final variable mappings.
    """
    new_env: dict[str, str] = {}
    print("\n[*] Interactive .env configuration setup")
    print("Press Enter to keep the default/current value.\n")

    for key in example_keys:
        current_val = resolve_default_value(key, existing_env)

        # Determine display default
        if current_val:
            if is_secret(key):
                display_default = "****"
            else:
                display_default = current_val
        else:
            display_default = "empty"

        try:
            prompt_str = f"[*] {key} [{display_default}]: "
            if is_secret(key):
                val = getpass.getpass(prompt_str).strip()
            else:
                val = input(prompt_str).strip()
        except KeyboardInterrupt:
            print("\n[!] Setup cancelled.")
            sys.exit(1)

        if val == "":
            # Keep existing value
            new_env[key] = current_val
        else:
            # If user typed "****" (though unlikely), keep current_val
            if val == "****" and current_val:
                new_env[key] = current_val
            else:
                new_env[key] = val
    return new_env

def write_env_file(example_path: str, env_path: str, new_env: dict[str, str]) -> None:
    """Generate and write the standard .env file.

    Args:
        example_path: Path to the .env.example template.
        env_path: Target path to write the .env file.
        new_env: Dict of configured environment variables.
    """
    output_lines: list[str] = []
    with open(example_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            match = re.match(r"^(?:#\s*)?(?:export\s+)?([\w_]+)=(.*)$", stripped)
            if match:
                key = match.group(1)
                if key in new_env and new_env[key]:
                    val = new_env[key]
                    env_val = val
                    if " " in env_val and not (env_val.startswith('"') and env_val.endswith('"')):
                        env_val = f'"{env_val}"'
                    output_lines.append(f"{key}={env_val}\n")
                else:
                    output_lines.append(f"# {key}=\n")
            else:
                output_lines.append(line)
                
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(output_lines)

def write_env_make_file(example_path: str, make_env_path: str, new_env: dict[str, str]) -> None:
    """Generate and write the Make-specific .env.make file.

    Args:
        example_path: Path to the .env.example template.
        make_env_path: Target path to write the .env.make file.
        new_env: Dict of configured environment variables.
    """
    make_output_lines: list[str] = []
    with open(example_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            match = re.match(r"^(?:#\s*)?(?:export\s+)?([\w_]+)=(.*)$", stripped)
            if match:
                key = match.group(1)
                if key in new_env and new_env[key]:
                    val = new_env[key]
                    # Strip any surrounding quotes, escape '$' as '$$' and '#' as '\#'
                    make_val = val.strip('"' + "'")
                    make_val = make_val.replace('$', '$$')
                    make_val = make_val.replace('#', r'\#')
                    make_output_lines.append(f"export {key}={make_val}\n")
                else:
                    make_output_lines.append(f"# export {key}=\n")
            else:
                make_output_lines.append(line.replace('$', '$$'))
                
    with open(make_env_path, "w", encoding="utf-8") as f:
        f.writelines(make_output_lines)

def set_file_permissions(paths: list[str]) -> None:
    """Set secure (0o600) file permissions for the generated files.

    Args:
        paths: List of file paths.
    """
    for path in paths:
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass

def main() -> None:
    """Main orchestration function for the environment setup script."""
    example_path = ".env.example"
    env_path = ".env"
    make_env_path = ".env.make"

    if not os.path.exists(example_path):
        print(f"[x] Error: {example_path} not found.")
        sys.exit(1)

    print("[*] Loading configurations...")
    existing_env = load_env(env_path)
    example_keys = parse_example_keys(example_path)

    new_env = collect_interactive_inputs(example_keys, existing_env)

    # Write standard .env file
    write_env_file(example_path, env_path, new_env)

    # Write Make-specific .env.make file
    write_env_make_file(example_path, make_env_path, new_env)

    # Set secure permissions
    set_file_permissions([env_path, make_env_path])

    print(f"\n[+] Successfully updated {env_path} and {make_env_path}")

if __name__ == "__main__":
    main()

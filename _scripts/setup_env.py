#!/usr/bin/env python3
import os
import sys
import re

def is_secret(key: str) -> bool:
    key_lower = key.lower()
    return any(x in key_lower for x in ["key", "token", "secret", "password"])

def load_env(filepath: str) -> dict:
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

def parse_example_keys(filepath: str) -> list:
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

def main():
    example_path = ".env.example"
    env_path = ".env"

    if not os.path.exists(example_path):
        print(f"[x] Error: {example_path} not found.")
        sys.exit(1)

    print("[*] Loading configurations...")
    existing_env = load_env(env_path)
    example_keys = parse_example_keys(example_path)

    new_env = {}
    print("\n📝 Interactive .env configuration setup")
    print("Press Enter to keep the default/current value.\n")

    for key in example_keys:
        # Resolve default value with fallbacks
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

        # Determine display default
        if current_val:
            if is_secret(key):
                display_default = "****"
            else:
                display_default = current_val
        else:
            display_default = "empty"

        try:
            val = input(f"🔹 {key} [{display_default}]: ").strip()
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

    # Now we write to .env, preserving the structure of .env.example if possible
    # We read .env.example line by line, and replace keys with their configured values
    output_lines = []
    make_output_lines = []
    with open(example_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            # Try to match key definition (active or commented out)
            match = re.match(r"^(?:#\s*)?(?:export\s+)?([\w_]+)=(.*)$", stripped)
            if match:
                key = match.group(1)
                if key in new_env and new_env[key]:
                    val = new_env[key]
                    # For standard .env:
                    # If value contains spaces, quote it
                    env_val = val
                    if " " in env_val and not (env_val.startswith('"') and env_val.endswith('"')):
                        env_val = f'"{env_val}"'
                    output_lines.append(f"{key}={env_val}\n")

                    # For Make-specific .env.make:
                    # Strip any surrounding quotes and escape '$' as '$$'
                    make_val = val.strip('"' + "'")
                    make_val = make_val.replace('$', '$$')
                    make_output_lines.append(f"{key}={make_val}\n")
                else:
                    output_lines.append(f"# {key}=\n")
                    make_output_lines.append(f"# {key}=\n")
            else:
                output_lines.append(line)
                make_output_lines.append(line.replace('$', '$$'))

    # Write back to .env
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(output_lines)

    # Write back to .env.make
    make_env_path = env_path + ".make"
    with open(make_env_path, "w", encoding="utf-8") as f:
        f.writelines(make_output_lines)

    # Set secure permissions
    for path in (env_path, make_env_path):
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass

    print(f"\n[+] Successfully updated {env_path} and {make_env_path}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import base64
import os
import re

def update_file(filepath: str, expected_header: str, is_make: bool):
    if not os.path.exists(filepath):
        return

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    header_match = re.search(r"^[ \t]*(?:export\s+)?ATLASSIAN_AUTH_HEADER=(.*)$", content, re.MULTILINE)
    current_header = header_match.group(1).strip().strip('"').strip("'") if header_match else None

    if current_header == expected_header:
        return

    print(f"[*] Updating ATLASSIAN_AUTH_HEADER in {filepath}...")

    if is_make:
        new_line = f"export ATLASSIAN_AUTH_HEADER={expected_header}"
    else:
        new_line = f'ATLASSIAN_AUTH_HEADER="{expected_header}"'

    if header_match:
        content = re.sub(
            r"^[ \t]*(?:export\s+)?ATLASSIAN_AUTH_HEADER=.*$",
            new_line,
            content,
            flags=re.MULTILINE
        )
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += f"{new_line}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] Updated {filepath}")

def main():
    env_path = ".env"
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as f:
        content = f.read()

    email_match = re.search(r"^[ \t]*(?:export\s+)?ATLASSIAN_EMAIL=(.+)$", content, re.MULTILINE)
    token_match = re.search(r"^[ \t]*(?:export\s+)?ATLASSIAN_API_TOKEN=(.+)$", content, re.MULTILINE)

    expected_header = ""
    if email_match and token_match:
        email = email_match.group(1).strip().strip('"').strip("'")
        token = token_match.group(1).strip().strip('"').strip("'")

        if email and token and not email.startswith("your-email") and not token.startswith("your-atlassian"):
            # Generate auth header
            raw_auth = f"{email}:{token}"
            encoded = base64.b64encode(raw_auth.encode("utf-8")).decode("utf-8")
            expected_header = f"Basic {encoded}"

    if expected_header:
        update_file(".env", expected_header, is_make=False)
        update_file(".env.make", expected_header, is_make=True)

if __name__ == "__main__":
    main()

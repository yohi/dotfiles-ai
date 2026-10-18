#!/usr/bin/env python3
"""Issue scoped temporary credentials for AWS MCP via aws login + STS.

Use only from a local AWS config credential_process profile. Never log
AssumeRole output (which contains session credentials).
"""

from __future__ import annotations

import argparse
import configparser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SESSION_POLICY_ARN = "arn:aws:iam::aws:policy/ReadOnlyAccess"
ROLE_ARN_RE = re.compile(r"^arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+$")


class CredentialError(Exception):
    """Expected local credential configuration or STS error."""


def _check_login_source(profile: str, config_path: Path) -> None:
    """Do not accept a source profile backed by permanent access keys."""
    config = configparser.RawConfigParser()
    if not config.read(config_path):
        raise CredentialError("AWS configuration file not found")
    section = "default" if profile == "default" else f"profile {profile}"
    if not config.has_section(section) or not config.get(section, "login_session", fallback="").strip():
        raise CredentialError("source profile must be configured by 'aws login'")
    if any(config.has_option(section, key) for key in
           ("aws_access_key_id", "aws_secret_access_key", "credential_process", "source_profile")):
        raise CredentialError("source profile contains an unsupported credential provider")


def _issue(role_arn: str, source_profile: str, region: str) -> dict[str, str | int]:
    if not ROLE_ARN_RE.fullmatch(role_arn):
        raise CredentialError("invalid AWS STS role ARN")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", source_profile):
        raise CredentialError("invalid source profile")
    config_path = Path(os.environ.get("AWS_CONFIG_FILE", str(Path.home() / ".aws" / "config"))).expanduser()
    _check_login_source(source_profile, config_path)

    # Explicit source profile, no ambient static credentials/role provider fallback.
    env = os.environ.copy()
    for key in (
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN", "AWS_PROFILE", "AWS_DEFAULT_PROFILE",
        "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_AUTHORIZATION_TOKEN", "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
    ):
        env.pop(key, None)
    env["AWS_EC2_METADATA_DISABLED"] = "true"

    command = [
        "aws", "sts", "assume-role", "--profile", source_profile,
        "--role-arn", role_arn,
        "--role-session-name", "aws-mcp-readonly",
        "--policy-arns", f"arn={SESSION_POLICY_ARN}",
        "--duration-seconds", "3600",
        "--region", region, "--output", "json", "--no-cli-pager",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                env=env, check=False, timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CredentialError("could not run AWS CLI AssumeRole") from exc
    if result.returncode != 0:
        # Do not forward AWS CLI output: may contain account or credential data.
        raise CredentialError("AWS STS AssumeRole failed; check login, trust policy and permissions")
    try:
        credentials = json.loads(result.stdout)["Credentials"]
        output = {
            "Version": 1,
            "AccessKeyId": credentials["AccessKeyId"],
            "SecretAccessKey": credentials["SecretAccessKey"],
            "SessionToken": credentials["SessionToken"],
            "Expiration": credentials["Expiration"],
        }
        if not all(isinstance(output[k], str) and output[k] for k in
                   ("AccessKeyId", "SecretAccessKey", "SessionToken", "Expiration")):
            raise ValueError("empty credentials")
        expiration = datetime.fromisoformat(output["Expiration"].replace("Z", "+00:00"))
        if expiration.tzinfo is None or expiration <= datetime.now(timezone.utc):
            raise ValueError("expired credentials")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise CredentialError("AWS STS returned invalid temporary credentials") from exc
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role-arn", default=os.environ.get("AWS_MCP_STS_ROLE_ARN"))
    parser.add_argument("--source-profile", default="signin")
    parser.add_argument("--region", default="ap-northeast-1")
    args = parser.parse_args()
    try:
        if not args.role_arn:
            raise CredentialError("role ARN is required")
        print(json.dumps(_issue(args.role_arn, args.source_profile, args.region)))
    except CredentialError as exc:
        print(f"AWS MCP STS credentials unavailable: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

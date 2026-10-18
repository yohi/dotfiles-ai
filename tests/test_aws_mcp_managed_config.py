"""Offline contract checks for the directly configured AWS Managed MCP server."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_managed_mcp_replaces_legacy_api_mcp() -> None:
    config = yaml.safe_load((ROOT / "apm.yml").read_text(encoding="utf-8"))
    servers = config["dependencies"]["mcp"]
    names = [s["name"] for s in servers if isinstance(s, dict)]
    assert names.count("aws-mcp") == 1
    assert "aws-api" not in names

    aws = next(s for s in servers if isinstance(s, dict) and s.get("name") == "aws-mcp")
    assert aws["registry"] is False
    assert aws["transport"] == "stdio"
    assert aws["command"] == "uvx"
    args = aws["args"]
    assert args[0] == "mcp-proxy-for-aws-cli==1.7.0"
    assert args[1] == "https://aws-mcp.ap-northeast-1.api.aws/mcp"
    assert args[args.index("--service") + 1] == "aws-mcp"
    assert args[args.index("--region") + 1] == "ap-northeast-1"
    assert args[args.index("--metadata") + 1] == "AWS_REGION=ap-northeast-1"
    assert args[args.index("--profile") + 1] == "aws-mcp-readonly"
    assert args[args.index("--retries") + 1] == "0"
    # --read-only hides the generic run_script API tool. Enforce AWS permissions
    # through an STS session policy instead; runtime authorization is not proven.
    assert "--read-only" not in args
    assert "--skip-auth" not in args
    assert aws["env"]["AWS_MCP_PROXY_PROFILES"] == "aws-mcp-readonly"
    assert aws["env"]["AWS_REGION"] == "ap-northeast-1"
    assert aws["env"]["AWS_DEFAULT_REGION"] == "ap-northeast-1"
    assert aws["timeout"] == 120000

    # Do not accidentally reintroduce AWS API MCP v1's bundled AWS CLI v1.
    assert "awslabs.aws-api-mcp-server" not in (ROOT / "apm.yml").read_text(
        encoding="utf-8"
    )


def test_sts_policy_is_required_in_helper() -> None:
    helper = (ROOT / "_scripts/aws-mcp-sts-credentials.py").read_text(
        encoding="utf-8"
    )
    assert 'SESSION_POLICY_ARN = "arn:aws:iam::aws:policy/ReadOnlyAccess"' in helper
    assert '"--policy-arns", f"arn={SESSION_POLICY_ARN}"' in helper
    assert '"--source-profile"' in helper

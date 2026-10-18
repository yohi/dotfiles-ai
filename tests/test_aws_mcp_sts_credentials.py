"""Offline contract tests for the AWS MCP credential_process shim."""

import importlib.util
from pathlib import Path
from datetime import datetime, timedelta, timezone
import subprocess
from unittest.mock import patch
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "_scripts" / "aws-mcp-sts-credentials.py"
spec = importlib.util.spec_from_file_location("aws_mcp_sts_credentials", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ROLE = "arn:aws:iam::111122223333:role/EXISTING_READONLY_ROLE"


@pytest.fixture(autouse=True)
def isolate_shared_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "nonexistent"))



def test_credential_process_success(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.write_text("[profile signin]\nlogin_session = arn:aws:iam::111122223333:user/sample\n")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "DO_NOT_USE")
    expiration = (datetime.now(timezone.utc) + timedelta(minutes=50)).isoformat()
    mock = subprocess.CompletedProcess([], 0, '{"Credentials":{"AccessKeyId":"ASIAXXXX","SecretAccessKey":"secret","SessionToken":"session","Expiration":"' + expiration + '"}}', "")
    with patch.object(mod.subprocess, "run", return_value=mock) as runner:
        out = mod._issue(ROLE, "signin", "ap-northeast-1")
    cmd = runner.call_args.args[0]
    assert cmd[cmd.index("--policy-arns") + 1] == "arn=arn:aws:iam::aws:policy/ReadOnlyAccess"
    assert cmd[cmd.index("--role-arn") + 1] == ROLE
    assert runner.call_args.kwargs["env"].get("AWS_ACCESS_KEY_ID") is None
    assert out["Version"] == 1
    assert out["Expiration"] == expiration


def test_login_profile_required(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.write_text("[profile signin]\naws_access_key_id = AKIAEXAMPLE\naws_secret_access_key = SECRET\n")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    with patch.object(mod.subprocess, "run") as runner:
        with pytest.raises(mod.CredentialError, match="aws login"):
            mod._issue(ROLE, "signin", "ap-northeast-1")
    runner.assert_not_called()


def test_assume_role_failure_does_not_surface_stderr(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.write_text("[profile signin]\nlogin_session = arn:aws:iam::111122223333:user/sample\n")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    with patch.object(mod.subprocess, "run", return_value=subprocess.CompletedProcess([], 254, "SECRET", "SECRET")):
        with pytest.raises(mod.CredentialError, match="STS AssumeRole failed") as exc:
            mod._issue(ROLE, "signin", "ap-northeast-1")
    assert "SECRET" not in str(exc.value)


def test_wrong_role_fails_closed(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.write_text("[profile signin]\nlogin_session = valid\n")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    with patch.object(mod.subprocess, "run") as runner:
        with pytest.raises(mod.CredentialError, match="invalid AWS STS role ARN"):
            mod._issue("invalid", "signin", "ap-northeast-1")
    runner.assert_not_called()


def test_static_keys_in_shared_file_are_rejected(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.write_text("[profile signin]\nlogin_session = console\n")
    credentials = tmp_path / "credentials"
    credentials.write_text("[signin]\naws_access_key_id = AKIAFAKE\naws_secret_access_key = secret\n")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(credentials))
    with patch.object(mod.subprocess, "run") as runner:
        with pytest.raises(mod.CredentialError, match="static credentials"):
            mod._issue(ROLE, "signin", "ap-northeast-1")
    runner.assert_not_called()

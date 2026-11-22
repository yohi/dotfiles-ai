"""Offline tests of Host V2 model configuration (no real services)."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "host/opencode2/sync_models.py"
spec = importlib.util.spec_from_file_location("sync_models", SCRIPT)
assert spec and spec.loader
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)

MANIFEST = '''
name: dotfiles-ai
x-variants:
  gpt_variants: &gpt_variants
    default: {reasoningEffort: max}
provider:
  openai:
    whitelist: [gpt-6-luna, gpt-6-sol]
  cloudflare-ai-gateway-custom:
    npm: '@ai-sdk/openai-compatible'
    name: 'Cloudflare AI Gateway (Custom)'
    options:
      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat'
      apiKey: ''
      headers:
        Authorization: ''
        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'
        cf-aig-collect-log-payload: 'true'
        cf-aig-max-attempts: '1'
        cf-aig-skip-cache: 'true'
    models:
      custom-ollama-cloud/kimi-k2.7-code:
        name: Kimi K2.7 Code (Ollama Cloud)
      misc/unused: {variants: *gpt_variants}
opencode_v2:
  default_model: openai/gpt-6-luna
  allowed_models:
    - openai/gpt-6-luna
    - cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code
  deny_provider_fallback: true
  deny_guest_auth: true
  providers:
    openai:
      enabled: true
      auth_method: docker_openai_oauth
    cloudflare-ai-gateway-custom:
      enabled: true
      auth_method: docker_custom_secret
'''


class HostV2ModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.apm = self.repo / "apm.yml"
        self.apm.write_text(MANIFEST)
        self.dir = self.home / ".config/opencode-v2/opencode"
        self.dir.mkdir(parents=True)
        self.target = self.dir / "opencode.json"
        self.v1 = self.home / ".config/opencode/opencode.json"
        self.v1.parent.mkdir(parents=True)
        self.v1.write_text("v1-sentinel")
        self.target.write_text(json.dumps({"$schema": "https://opencode.ai/config.json", "mcp": {"servers": {"x": {"disabled": True}}}, "plugins": []}))
        self.repo_patch = patch.object(models, "REPO", self.repo)
        self.repo_patch.start()
        self.addCleanup(self.repo_patch.stop)
        self.env_patch = patch.dict(os.environ, {"HOME": str(self.home), "OC_CF_API_TOKEN": "must-never-be-copied", "OC_CF_ACCOUNT_ID": "example-account"})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_check_no_write(self):
        before = self.target.read_bytes()
        self.assertEqual(models.main(["--check"]), 0)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertFalse((self.dir / "model-host-sync-state.json").exists())

    def test_apply_preserves_mcp_v1_and_uses_native_v2(self):
        original = self.apm.read_bytes()
        self.assertEqual(models.main(["--apply"]), 0)
        result = json.loads(self.target.read_text())
        self.assertEqual(result["model"], "openai/gpt-6-luna")
        self.assertEqual(result["mcp"]["servers"]["x"]["disabled"], True)
        self.assertEqual(self.v1.read_text(), "v1-sentinel")
        self.assertEqual(self.apm.read_bytes(), original)
        cloud = result["providers"][models.CUSTOM]
        self.assertEqual(cloud["package"], "@opencode/ai/providers/openai-compatible")
        self.assertEqual(list(cloud["models"]), ["custom-ollama-cloud/kimi-k2.7-code"])
        self.assertEqual(cloud["env"], ["OC_CF_API_TOKEN"])
        self.assertNotIn("must-never-be-copied", self.target.read_text())
        self.assertEqual(cloud["headers"]["Authorization"], "")
        self.assertEqual(cloud["headers"]["cf-aig-authorization"], "Bearer {env:OC_CF_API_TOKEN}")
        self.assertEqual(result["policies"], [
            {"action": "provider.use", "resource": "*", "effect": "deny"},
            {"action": "provider.use", "resource": "openai", "effect": "allow"},
            {"action": "provider.use", "resource": models.CUSTOM, "effect": "allow"},
        ])
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)

    def test_repeat_apply_safe(self):
        self.assertEqual(models.main(["--apply"]), 0)
        self.assertEqual(models.main(["--apply"]), 0)
        self.assertEqual(self.v1.read_text(), "v1-sentinel")

    def test_manual_provider_change_blocks(self):
        models.main(["--apply"])
        data = json.loads(self.target.read_text())
        data["providers"][models.CUSTOM]["settings"]["baseURL"] = "https://other.example"
        self.target.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, "changed after last sync"):
            models.main(["--apply"])
        self.assertIn("other.example", self.target.read_text())

    def test_unmanaged_default_model_blocks(self):
        data = json.loads(self.target.read_text())
        data["model"] = "openai/other"
        self.target.write_text(json.dumps(data))
        with self.assertRaisesRegex(RuntimeError, "unmanaged"):
            models.main(["--apply"])

    def test_custom_provider_endpoint_drift_blocks_without_writes(self):
        self.apm.write_text(MANIFEST.replace("gateway.ai.cloudflare.com", "other.invalid"))
        before = self.target.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "contract changed"):
            models.main(["--apply"])
        self.assertEqual(self.target.read_bytes(), before)

    def test_bad_model_catalog_stops(self):
        self.apm.write_text(MANIFEST.replace("gpt-6-luna, gpt-6-sol", "gpt-6-sol"))
        with self.assertRaisesRegex(RuntimeError, "missing from OpenAI catalog"):
            models.main(["--check"])

    def test_source_selection_must_be_approved(self):
        self.apm.write_text(MANIFEST.replace("docker_openai_oauth", "host_openai_oauth"))
        with self.assertRaisesRegex(RuntimeError, "unexpected SSOT provider"):
            models.main(["--apply"])

    def test_missing_v2_config_stops(self):
        self.target.unlink()
        with self.assertRaisesRegex(RuntimeError, "missing or unsafe"):
            models.main(["--apply"])


if __name__ == "__main__":
    unittest.main()

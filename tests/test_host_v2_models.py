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
enabled_providers:
  - openai
  - cloudflare-ai-gateway
  - cloudflare-ai-gateway-custom
  - cloudflare-ai-gateway-octg
  - opencode
  - ollama-cloud
  - opencode-go
  - amazon-bedrock
  - google
provider:
  openai:
    whitelist: [gpt-6-luna, gpt-6-sol]
  opencode:
    whitelist: [deepseek-v4.1-flash-free, glm-5.3-flash-free]
  opencode-go:
    whitelist: [kimi-k2.7-code, glm-5.3-flash]
  amazon-bedrock:
    whitelist: [global.anthropic.claude-sonnet-5-5]
  google:
    whitelist: [gemini-3.6-flash]
  cloudflare-ai-gateway:
    npm: ai-gateway-provider
    options:
      accountId: '${env:OC_CF_ACCOUNT_ID}'
      gatewayId: '${env:OC_CF_GATEWAY_ID}'
      apiKey: '${env:OC_CF_API_TOKEN}'
    models:
      openai/gpt-6-luna:
        name: GPT-6 Luna (Cloudflare)
        variants: *gpt_variants
      google-ai-studio/gemini-3.1-pro:
        name: Gemini 3.1 Pro (Cloudflare)
  cloudflare-ai-gateway-octg:
    npm: '@ai-sdk/openai'
    name: 'Cloudflare AI Gateway (OCTG)'
    options:
      apiKey: cloudflare-custom-provider
      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OCTG_CF_ACCOUNT_ID}/${env:OCTG_CF_GATEWAY_ID}/custom-octg/v1'
      headers:
        Authorization: ''
        cf-aig-authorization: 'Bearer ${env:OCTG_CF_API_TOKEN}'
        cf-aig-collect-log-payload: 'true'
        cf-aig-max-attempts: '1'
        cf-aig-skip-cache: 'true'
    models:
      gpt-6-luna:
        name: GPT-6 Luna (OCTG)
        variants: *gpt_variants

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
      custom-ollama-cloud/glm-5.3-flash:
        name: GLM 5.3 Flash (Ollama Cloud)
        variants: *gpt_variants
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
        self.assertEqual(list(cloud["models"]), [
            "custom-ollama-cloud/kimi-k2.7-code", "custom-ollama-cloud/glm-5.3-flash",
        ])
        self.assertEqual(cloud["env"], ["OC_CF_API_TOKEN"])
        self.assertNotIn("must-never-be-copied", self.target.read_text())
        self.assertEqual(cloud["headers"]["Authorization"], "")
        self.assertEqual(cloud["headers"]["cf-aig-authorization"], "Bearer {env:OC_CF_API_TOKEN}")
        self.assertEqual([p["resource"] for p in result["policies"]], ["*", *models.PROVIDERS])
        self.assertTrue(all(p["effect"] == "allow" for p in result["policies"][1:]))
        self.assertEqual(len(result["providers"]), 9)
        self.assertNotIn("cloudflare-ai-gateway-dynamic", result["providers"])
        self.assertEqual(result["providers"]["opencode-go"]["models"], {
            "kimi-k2.7-code": {"modelID": "kimi-k2.7-code"},
            "glm-5.3-flash": {"modelID": "glm-5.3-flash"},
        })
        self.assertEqual(result["providers"]["ollama-cloud"], {})
        self.assertEqual(result["providers"]["amazon-bedrock"]["models"], {
            "global.anthropic.claude-sonnet-5-5": {"modelID": "global.anthropic.claude-sonnet-5-5"},
        })
        self.assertEqual(result["providers"]["google"]["models"], {
            "gemini-3.6-flash": {"modelID": "gemini-3.6-flash"},
        })
        self.assertEqual(result["providers"][models.UNIFIED]["package"],
                         "@opencode/ai/providers/openai-compatible")
        self.assertEqual(result["providers"][models.OCTG]["package"],
                         "@opencode/ai/providers/openai/responses")
        self.assertEqual(result["providers"][models.UNIFIED]["models"]["openai/gpt-6-luna"]["settings"],
                         {"reasoningEffort": "max"})

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
        with self.assertRaisesRegex(RuntimeError, "unexpected Sandbox SSOT provider"):
            models.main(["--apply"])

    def test_enabled_provider_drift_fails_closed(self):
        self.apm.write_text(MANIFEST.replace("  - amazon-bedrock\n", ""))
        with self.assertRaisesRegex(RuntimeError, "parity scope changed"):
            models.main(["--apply"])

    def test_additional_paid_provider_requires_explicit_owner(self):
        self.apm.write_text(MANIFEST.replace("enabled_providers:\n", "enabled_providers:\n  - strange-paid-service\n"))
        with self.assertRaisesRegex(RuntimeError, "parity scope changed"):
            models.main(["--check"])

    def test_octg_endpoint_drift_stops_without_writing(self):
        self.apm.write_text(MANIFEST.replace("custom-octg/v1", "other-requests/v1"))
        previous = self.target.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "OCTG endpoint/authentication contract changed"):
            models.main(["--apply"])
        self.assertEqual(previous, self.target.read_bytes())

    def test_v2_managed_two_provider_configuration_upgrade(self):
        prior = {"model": "openai/gpt-6-luna", "providers": {
            models.CUSTOM: {"package": "@opencode/ai/providers/openai-compatible"}
        }, "policies": [{"action":"provider.use","resource":"*","effect":"deny"}]}
        config = json.loads(self.target.read_text())
        config.update(prior)
        self.target.write_text(json.dumps(config))
        (self.dir / "model-host-sync-state.json").write_text(json.dumps({
            "source":"apm.yml:opencode_v2", "managed_sha256":models.fingerprint(prior),
        }))
        self.assertEqual(models.main(["--apply"]), 0)
        upgraded = json.loads(self.target.read_text())
        self.assertEqual(len(upgraded["providers"]), 9)
        self.assertEqual(self.v1.read_text(), "v1-sentinel")

    def test_extra_model_variant_is_native_array(self):
        self.apm.write_text(MANIFEST.replace("default: {reasoningEffort: max}",
                                            "default: {reasoningEffort: max}\n    low: {reasoningEffort: low}"))
        expected = models.expected_config()
        entry = expected["providers"][models.UNIFIED]["models"]["openai/gpt-6-luna"]
        self.assertEqual(entry["settings"], {"reasoningEffort": "max"})
        self.assertEqual(entry["variants"], [{"id": "low", "settings": {"reasoningEffort": "low"}}])

    def test_credential_never_materializes_in_target(self):
        self.assertEqual(models.main(["--apply"]), 0)
        raw = self.target.read_text()
        self.assertNotIn("must-never-be-copied", raw)
        self.assertNotIn("example-account", raw)
        self.assertIn("{env:OC_CF_API_TOKEN}", raw)
        self.assertIn("{env:OCTG_CF_API_TOKEN}", raw)

    def test_missing_v2_config_stops(self):
        self.target.unlink()
        with self.assertRaisesRegex(RuntimeError, "missing or unsafe"):
            models.main(["--apply"])


if __name__ == "__main__":
    unittest.main()

"""Read-only and fail-closed tests for the Sandbox config snapshot generator."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_opencode_v2.py"
sys.path.insert(0, str(SCRIPT.parent))
import prepare_opencode_v2 as exporter  # noqa: E402


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "dotfiles-ai"
        self.root.mkdir()
        self.out = Path(self.tmp.name) / "export"
        self.apm = self.root / "apm.yml"
        self.apm.write_text(
            "shell: bash\nsnapshot: true\n"
            "plugin:\n - private/plugin\n"
            "dependencies:\n  mcp:\n    - name: privileged\n"
            "      command: /srv/test-only/secret\n"
            "provider:\n  hidden:\n    apiKey: TOP_SECRET_DO_NOT_EXPORT\n",
            encoding="utf-8",
        )

    def run_export(self, *flags: str, output: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable, str(SCRIPT), "--repo-root", str(self.root),
                "--out", str(output or self.out), *flags,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_whitelist_never_exports_plugins_mcp_or_secrets(self) -> None:
        before = self.apm.read_bytes()
        self.assertEqual(self.run_export().returncode, 0)
        server = json.loads((self.out / "opencode.jsonc").read_text())
        tui = json.loads((self.out / "cli.json").read_text())
        self.assertEqual(server["plugins"], [])
        self.assertEqual(server["mcp"], {})
        self.assertEqual(server["shell"], "bash")
        self.assertIs(server["snapshot"], True)
        self.assertEqual(tui["plugins"], [])
        for output in self.out.iterdir():
            content = output.read_text()
            self.assertNotIn("TOP_SECRET_DO_NOT_EXPORT", content)
            self.assertNotIn("/srv/test-only/secret", content)
            self.assertNotIn("private/plugin", content)
        self.assertEqual(self.apm.read_bytes(), before)

    def test_manifest_hashes_are_correct(self) -> None:
        self.assertEqual(self.run_export().returncode, 0)
        manifest = json.loads((self.out / "export-manifest.json").read_text())
        self.assertEqual(manifest["source_sha256"], hashlib.sha256(self.apm.read_bytes()).hexdigest())
        self.assertEqual(manifest["opencode_version"], "2.2.5")
        self.assertEqual(manifest["config_format"], "legacy-minimal")
        self.assertEqual(manifest["mcp_entries_exported"], 0)
        for name, sha in manifest["artifacts_sha256"].items():
            self.assertEqual(sha, hashlib.sha256((self.out / name).read_bytes()).hexdigest())

    def test_manifest_refresh_tracks_a_runtime_provider_selection(self) -> None:
        self.apm.write_text(
            "provider:\n  openai: {whitelist: [gpt-6-luna]}\n"
            "  cloudflare-ai-gateway-custom:\n"
            "    npm: '@ai-sdk/openai-compatible'\n"
            "    name: Cloudflare AI Gateway Custom\n"
            "    options:\n"
            "      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat'\n"
            "      apiKey: ''\n      headers:\n"
            "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
            "    models:\n      custom/kimi: {name: Kimi}\n"
            "opencode_v2:\n  default_model: openai/gpt-6-luna\n"
            "  deny_provider_fallback: true\n  deny_guest_auth: true\n"
            "  providers:\n    openai: {enabled: true, auth_method: docker_openai_oauth}\n"
            "    cloudflare-ai-gateway-custom: {enabled: true, auth_method: docker_custom_secret}\n",
            encoding="utf-8",
        )
        self.assertEqual(self.run_export().returncode, 0)
        server_path = self.out / "opencode.jsonc"
        server = json.loads(server_path.read_text())
        server["providers"].pop("cloudflare-ai-gateway-custom")
        server["policies"] = [
            policy for policy in server["policies"]
            if policy.get("resource") != "cloudflare-ai-gateway-custom"
        ]
        server_path.write_text(json.dumps(server, indent=2) + "\n", encoding="utf-8")

        manifest_sha = exporter.refresh_manifest(self.out)

        manifest = json.loads((self.out / "export-manifest.json").read_text())
        self.assertEqual(manifest_sha, hashlib.sha256((self.out / "export-manifest.json").read_bytes()).hexdigest())
        self.assertEqual(manifest["artifacts_sha256"]["opencode.jsonc"], hashlib.sha256(server_path.read_bytes()).hexdigest())

    def test_verification_export_contains_no_provider_or_credential_configuration(self) -> None:
        self.apm.write_text(
            "shell: bash\nsnapshot: true\n"
            "x-oc2-assets: [global-rules/AGENTS.global.md]\n"
            "x-oc2-agents: {}\n"
            "x-oc2-plugins: {enabled: false, allowlist: [superpowers]}\n"
            "x-oc2-mcp: {enabled: false, servers: [oc2-status]}\n",
            encoding="utf-8",
        )

        result = self.run_export("--verification-only")

        self.assertEqual(result.returncode, 0, result.stderr)
        server = json.loads((self.out / "opencode.jsonc").read_text())
        manifest = json.loads((self.out / "export-manifest.json").read_text())
        self.assertEqual(manifest["config_format"], "oc2-verification")
        self.assertEqual(server["plugins"], [])
        self.assertEqual(server["mcp"], {})
        self.assertNotIn("model", server)
        self.assertNotIn("providers", server)
        self.assertNotIn("policies", server)

    def test_v2_provider_config_supports_openai_and_cloudflare_custom(self) -> None:
        self.apm.write_text(
            "shell: bash\nsnapshot: true\n"
            "provider:\n"
            "  openai:\n"
            "    whitelist: [gpt-6-luna, gpt-6.1-sol]\n"
            "  hidden:\n"
            "    apiKey: TOP_SECRET_DO_NOT_EXPORT\n"
            "  cloudflare-ai-gateway-custom:\n"
            "    npm: '@ai-sdk/openai-compatible'\n"
            "    name: Cloudflare AI Gateway Custom\n"
            "    options:\n"
            "      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat'\n"
            "      apiKey: ''\n"
            "      headers:\n"
            "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
            "    models:\n"
            "      custom-ollama-cloud/kimi-k2.6:\n"
            "        name: Kimi K2.6\n"
            "opencode_v2:\n"
            "  default_model: openai/gpt-6-luna\n"
            "  deny_provider_fallback: true\n"
            "  deny_guest_auth: true\n"
            "  providers:\n"
            "    openai:\n"
            "      enabled: true\n"
            "      auth_method: docker_openai_oauth\n"
            "    cloudflare-ai-gateway-custom:\n"
            "      enabled: true\n"
            "      auth_method: docker_custom_secret\n",
            encoding="utf-8",
        )

        result = self.run_export()
        self.assertEqual(result.returncode, 0, result.stderr)
        server = json.loads((self.out / "opencode.jsonc").read_text())
        manifest = json.loads((self.out / "export-manifest.json").read_text())
        self.assertEqual(manifest["config_format"], "opencode-v2")
        self.assertEqual(server["model"], "openai/gpt-6-luna")
        self.assertEqual(set(server["providers"]), {"openai", "cloudflare-ai-gateway-custom"})
        self.assertEqual(
            set(server["providers"]["openai"]["models"]),
            {"gpt-6-luna", "gpt-6.1-sol"},
        )
        self.assertEqual(
            server["policies"][:3],
            [
                {"action": "provider.use", "resource": "*", "effect": "deny"},
                {"action": "provider.use", "resource": "openai", "effect": "allow"},
                {"action": "provider.use", "resource": "cloudflare-ai-gateway-custom", "effect": "allow"},
            ],
        )
        self.assertEqual(
            set(server["providers"]["cloudflare-ai-gateway-custom"]["models"]),
            {"custom-ollama-cloud/kimi-k2.6"},
        )
        self.assertIn(
            {"action": "integration.connect", "resource": "*", "effect": "deny"},
            server["policies"],
        )
        for generated in self.out.iterdir():
            self.assertNotIn("TOP_SECRET_DO_NOT_EXPORT", generated.read_text())
            self.assertNotIn("OC_CF_REST_API_TOKEN", generated.read_text())

    def test_v2_native_agents_use_only_apm_selected_fixed_config(self) -> None:
        self.apm.write_text(
            "provider:\n"
            "  openai:\n"
            "    whitelist: [gpt-6-luna]\n"
            "  cloudflare-ai-gateway-custom:\n"
            "    npm: '@ai-sdk/openai-compatible'\n"
            "    name: Cloudflare AI Gateway Custom\n"
            "    options:\n"
            "      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat'\n"
            "      apiKey: ''\n"
            "      headers:\n"
            "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
            "    models:\n"
            "      custom-ollama-cloud/kimi-k2.6:\n"
            "        name: Kimi K2.6\n"
            "opencode_v2:\n"
            "  default_model: openai/gpt-6-luna\n"
            "  deny_provider_fallback: true\n"
            "  deny_guest_auth: true\n"
            "  providers:\n"
            "    openai:\n"
            "      enabled: true\n"
            "      auth_method: docker_openai_oauth\n"
            "    cloudflare-ai-gateway-custom:\n"
            "      enabled: true\n"
            "      auth_method: docker_custom_secret\n"
            "x-oc2-assets: [global-rules/AGENTS.global.md]\n"
            "x-oc2-agents:\n"
            "  hephaestus: {mode: primary, model: openai/gpt-6-luna}\n"
            "  oracle: {mode: subagent, model: openai/gpt-6-luna}\n"
            "x-oc2-plugins: {enabled: false, allowlist: [superpowers]}\n"
            "x-oc2-mcp: {enabled: false, servers: []}\n",
            encoding="utf-8",
        )

        result = self.run_export()

        self.assertEqual(result.returncode, 0, result.stderr)
        server = json.loads((self.out / "opencode.jsonc").read_text())
        self.assertEqual(set(server["agents"]), {"hephaestus", "oracle"})
        self.assertEqual(server["agents"]["hephaestus"]["mode"], "primary")
        self.assertEqual(server["agents"]["oracle"]["mode"], "subagent")
        self.assertEqual(server["agents"]["oracle"]["model"], "openai/gpt-6-luna")
        self.assertNotIn("default_agent", server)
        self.assertNotIn("fallback_models", server["agents"]["hephaestus"])
        self.assertNotIn("mcp", server)
        self.assertIn(
            {"action": "mcp.use", "resource": "*", "effect": "deny"},
            server["policies"],
        )

    def test_unified_runtime_export_keeps_provider_and_agents_without_inline_plugins(self) -> None:
        source = Path(__file__).resolve().parents[2] / "apm.yml"
        self.apm.write_bytes(source.read_bytes())

        result = self.run_export()

        self.assertEqual(result.returncode, 0, result.stderr)
        server = json.loads((self.out / "opencode.jsonc").read_text())
        manifest = json.loads((self.out / "export-manifest.json").read_text())
        self.assertEqual(manifest["config_format"], "opencode-v2-unified")
        self.assertEqual(server["model"], "openai/gpt-6-luna")
        self.assertEqual(set(server["agents"]), {"hephaestus", "oracle"})
        self.assertNotIn("plugins", server)
        self.assertNotIn("mcp", server)
        for generated in self.out.iterdir():
            self.assertNotIn("TOP_SECRET_DO_NOT_EXPORT", generated.read_text())

    def test_v2_provider_config_rejects_unapproved_provider(self) -> None:
        self.apm.write_text(
            "provider:\n"
            "  cloudflare-ai-gateway-rest:\n"
            "    npm: '@ai-sdk/openai-compatible'\n"
            "    name: Cloudflare AI Gateway REST\n"
            "    options:\n"
            "      baseURL: 'https://api.cloudflare.com/client/v4/accounts/${env:OC_CF_ACCOUNT_ID}/ai/v1'\n"
            "      apiKey: '${env:OC_CF_REST_API_TOKEN}'\n"
            "      headers:\n"
            "        cf-aig-gateway-id: '${env:OC_CF_GATEWAY_ID}'\n"
            "    models:\n"
            "      openai/gpt-6-luna:\n"
            "        name: GPT-6 Luna\n"
            "opencode_v2:\n"
            "  default_model: cloudflare-ai-gateway-rest/openai/gpt-6-luna\n"
            "  deny_provider_fallback: true\n"
            "  deny_guest_auth: true\n"
            "  providers:\n"
            "    cloudflare-ai-gateway-rest:\n"
            "      enabled: true\n"
            "      auth_method: docker_custom_secret\n",
            encoding="utf-8",
        )

        result = self.run_export()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported auth method", result.stderr)
        self.assertFalse(self.out.exists())

    def test_v2_custom_provider_maps_gateway_settings_and_variants(self) -> None:
        self.apm.write_text(
            "provider:\n"
            "  openai:\n"
            "    whitelist: [gpt-6-luna]\n"
            "  cloudflare-ai-gateway-custom:\n"
            "    npm: '@ai-sdk/openai-compatible'\n"
            "    name: Cloudflare AI Gateway Custom\n"
            "    options:\n"
            "      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat'\n"
            "      apiKey: ''\n"
            "      headers:\n"
            "        Authorization: ''\n"
            "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
            "    models:\n"
            "      custom-ollama-cloud/kimi-k2.6:\n"
            "        name: Kimi K2.6\n"
            "        variants:\n"
            "          default:\n"
            "            body:\n"
            "              thinking: {type: enabled}\n"
            "          none:\n"
            "            body:\n"
            "              thinking: {type: disabled}\n"
            "opencode_v2:\n"
            "  default_model: cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.6\n"
            "  deny_provider_fallback: true\n"
            "  deny_guest_auth: true\n"
            "  providers:\n"
            "    openai:\n"
            "      enabled: true\n"
            "      auth_method: docker_openai_oauth\n"
            "    cloudflare-ai-gateway-custom:\n"
            "      enabled: true\n"
            "      auth_method: docker_custom_secret\n",
            encoding="utf-8",
        )

        result = self.run_export()
        self.assertEqual(result.returncode, 0, result.stderr)
        server = json.loads((self.out / "opencode.jsonc").read_text())
        provider = server["providers"]["cloudflare-ai-gateway-custom"]
        self.assertEqual(provider["package"], "aisdk:@ai-sdk/openai-compatible")
        self.assertEqual(
            provider["settings"]["baseURL"],
            "https://gateway.ai.cloudflare.com/v1/{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat",
        )
        self.assertEqual(
            provider["headers"]["cf-aig-authorization"],
            "Bearer {env:OC_CF_API_TOKEN}",
        )
        model = provider["models"]["custom-ollama-cloud/kimi-k2.6"]
        self.assertEqual(model["modelID"], "custom-ollama-cloud/kimi-k2.6")
        self.assertEqual(model["body"]["thinking"]["type"], "enabled")
        self.assertEqual(model["variants"][0]["id"], "none")
        self.assertEqual(model["variants"][0]["body"]["thinking"]["type"], "disabled")
        self.assertNotIn("apiKey", provider["settings"])

    def test_v2_config_rejects_unlisted_default_model(self) -> None:
        self.apm.write_text(
            "provider:\n"
            "  openai:\n"
            "    whitelist: [gpt-6-luna]\n"
            "  cloudflare-ai-gateway-custom:\n"
            "    npm: '@ai-sdk/openai-compatible'\n"
            "    name: Cloudflare AI Gateway Custom\n"
            "    options:\n"
            "      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat'\n"
            "      apiKey: ''\n"
            "      headers:\n"
            "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
            "    models:\n"
            "      custom-ollama-cloud/kimi-k2.7-code:\n"
            "        name: Kimi K2.7 Code\n"
            "opencode_v2:\n"
            "  default_model: openai/not-in-apm\n"
            "  deny_provider_fallback: true\n"
            "  deny_guest_auth: true\n"
            "  providers:\n"
            "    openai:\n"
            "      enabled: true\n"
            "      auth_method: docker_openai_oauth\n"
            "    cloudflare-ai-gateway-custom:\n"
            "      enabled: true\n"
            "      auth_method: docker_custom_secret\n",
            encoding="utf-8",
        )
        result = self.run_export()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.out.exists())

    def test_check_detects_modifications_without_writing(self) -> None:
        self.assertEqual(self.run_export().returncode, 0)
        self.assertEqual(self.run_export("--check").returncode, 0)
        target = self.out / "cli.json"
        target.write_text("{}\n")
        self.assertNotEqual(self.run_export("--check").returncode, 0)
        self.assertEqual(target.read_text(), "{}\n")

    def test_refuses_overwrite(self) -> None:
        self.assertEqual(self.run_export().returncode, 0)
        self.assertNotEqual(self.run_export().returncode, 0)

    def test_rejects_invalid_shell_and_snapshot(self) -> None:
        self.apm.write_text("shell: 'bash; cat /etc/passwd'\n")
        self.assertNotEqual(self.run_export().returncode, 0)
        self.apm.write_text("shell: bash\nsnapshot: 'true'\n")
        self.assertNotEqual(self.run_export().returncode, 0)
        self.assertFalse(self.out.exists())

    def test_refuses_symlinked_apm(self) -> None:
        real = self.root / "real.yml"
        real.write_bytes(self.apm.read_bytes())
        self.apm.unlink()
        self.apm.symlink_to(real)
        self.assertNotEqual(self.run_export().returncode, 0)

    def test_refuses_output_under_repository(self) -> None:
        self.assertNotEqual(
            self.run_export(output=self.root / "sandbox-out").returncode, 0
        )

    def test_refuses_output_outside_temporary_directory(self) -> None:
        output = Path.home() / "unsafe-opencode-export"

        self.assertNotEqual(self.run_export(output=output).returncode, 0)
        self.assertFalse(output.exists())

    def test_refuses_symlinked_output_parent(self) -> None:
        target = Path(self.tmp.name) / "safe"
        target.mkdir()
        link = Path(self.tmp.name) / "link"
        link.symlink_to(target, target_is_directory=True)
        self.assertNotEqual(
            self.run_export(output=link / "export").returncode, 0
        )

    def test_refuses_unexpected_file_in_check(self) -> None:
        self.assertEqual(self.run_export().returncode, 0)
        (self.out / "extra").write_text("unapproved")
        self.assertNotEqual(self.run_export("--check").returncode, 0)


if __name__ == "__main__":
    unittest.main()

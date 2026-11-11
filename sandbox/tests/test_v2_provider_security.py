"""Shared security vectors for the V2 exporter, Stage, and Guest validators."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import oc2_guest as guest  # noqa: E402
import prepare_opencode_v2 as exporter  # noqa: E402
import stage_opencode_v2 as stage  # noqa: E402

CF_PROVIDER = "cloudflare-ai-gateway-custom"
SAFE_APM_BASE_URL = (
    "https://gateway.ai.cloudflare.com/v1/"
    "${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat"
)
SAFE_BASE_URL = (
    "https://gateway.ai.cloudflare.com/v1/"
    "{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat"
)
SAFE_APM_HEADERS = {
    "Authorization": "",
    "cf-aig-authorization": "Bearer ${env:OC_CF_API_TOKEN}",
    "cf-aig-collect-log-payload": "true",
    "cf-aig-max-attempts": "1",
    "cf-aig-skip-cache": "true",
}
SAFE_HEADERS = {
    "Authorization": "",
    "cf-aig-authorization": "Bearer {env:OC_CF_API_TOKEN}",
    "cf-aig-collect-log-payload": "true",
    "cf-aig-max-attempts": "1",
    "cf-aig-skip-cache": "true",
}
BAD_BASE_URLS = (
    "http://gateway.ai.cloudflare.com/v1/{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat",
    "https://user:pass@gateway.ai.cloudflare.com/v1/{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat",
    SAFE_BASE_URL + "?token=NOT_A_REAL_SECRET",
    SAFE_BASE_URL + "#fragment",
    "https://evil.example/v1/{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat",
    "https://GATEWAY.AI.CLOUDFLARE.COM/v1/{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat",
    "https://gateway.ai.cloudflare.com:443/v1/{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat",
    "https://gateway.ai.cloudflare.com/v1/{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/../compat",
    "https://gateway.ai.cloudflare.com/v1/{env:OC_CF_ACCOUNT_ID}\\..\\{env:OC_CF_GATEWAY_ID}/compat",
    "https://gateway.ai.cloudflare.com/v1/%2e%2e/{env:OC_CF_GATEWAY_ID}/compat",
    "https://gateway.ai.cloudflare.com/v1/{env:OC_CF_ACCOUNT_ID}/{env:OTHER_SECRET}/compat",
    "https://gateway.ai.cloudflare.com/v1/{env:OC_CF_ACCOUNT_ID}/{env:OC_CF_GATEWAY_ID}/compat%ZZ",
)
BAD_HEADERS = (
    {"x-auth-token": "NOT_A_REAL_SECRET"},
    {"CF-AIG-AUTHORIZATION": SAFE_HEADERS["cf-aig-authorization"]},
    {
        "cf-aig-authorization": SAFE_HEADERS["cf-aig-authorization"],
        "CF-AIG-AUTHORIZATION": SAFE_HEADERS["cf-aig-authorization"],
    },
    {"cf-aig-authorization": "Bearer NOT_A_REAL_SECRET"},
    {"cf-aig-authorization": "Bearer {env:OPENAI_API_KEY}"},
    {"cf-aig-collect-log-payload": "true\nX-Leak: yes"},
    {"cf-aig-max-attempts": "1\x01"},
    {"cf-aig-max-attempts": "2"},
)


def _cf_provider(
    base_url: str = SAFE_BASE_URL,
    headers: dict[str, str] | None = None,
    settings_extra: dict[str, str] | None = None,
) -> dict[str, exporter.JsonValue]:
    settings: dict[str, object] = {"baseURL": base_url}
    settings.update(settings_extra or {})
    return {
        "package": "aisdk:@ai-sdk/openai-compatible",
        "name": "Cloudflare AI Gateway Custom",
        "settings": settings,
        "headers": dict(SAFE_HEADERS if headers is None else headers),
        "models": {
            "custom-ollama-cloud/kimi-k2.7-code": {
                "modelID": "custom-ollama-cloud/kimi-k2.7-code",
                "name": "Kimi K2.7 Code",
            },
        },
    }


def _server_config(
    base_url: str = SAFE_BASE_URL,
    headers: dict[str, str] | None = None,
    settings_extra: dict[str, str] | None = None,
) -> dict[str, exporter.JsonValue]:
    return {
        "$schema": "https://opencode.ai/config.json",
        "shell": "bash",
        "snapshot": True,
        "model": "openai/gpt-6-luna",
        "providers": {
            "openai": {"models": {"gpt-6-luna": {"modelID": "gpt-6-luna", "name": "GPT-6 Luna"}}},
            CF_PROVIDER: _cf_provider(base_url, headers, settings_extra),
        },
        "policies": [
            {"action": "provider.use", "resource": "*", "effect": "deny"},
            {"action": "provider.use", "resource": "openai", "effect": "allow"},
            {"action": "provider.use", "resource": CF_PROVIDER, "effect": "allow"},
            {"action": "integration.connect", "resource": "*", "effect": "deny"},
            {"action": "plugin.use", "resource": "*", "effect": "deny"},
            {"action": "mcp.use", "resource": "*", "effect": "deny"},
        ],
    }


class ProviderSecurityContractTests(unittest.TestCase):
    def _assert_exporter_rejects(
        self,
        base_url: str,
        headers: dict[str, str],
        settings_extra: dict[str, str] | None = None,
    ) -> None:
        options: dict[str, object] = {
            "baseURL": base_url,
            "apiKey": "",
            "headers": headers,
        }
        options.update(settings_extra or {})
        source = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Cloudflare AI Gateway Custom",
            "options": options,
            "models": {
                "custom-ollama-cloud/kimi-k2.7-code": {"name": "Kimi K2.7 Code"},
            },
        }
        with self.assertRaises(exporter.ExportError):
            exporter._v2_provider(
                CF_PROVIDER, source, ("custom-ollama-cloud/kimi-k2.7-code",),
            )

    def _assert_stage_and_guest_reject(
        self,
        base_url: str,
        headers: dict[str, str],
        settings_extra: dict[str, str] | None = None,
    ) -> None:
        config = _server_config(base_url, headers, settings_extra)
        with self.assertRaises(stage.StageError):
            stage._verify_v2_config(config)
        with self.assertRaises(ValueError):
            guest.verify_v2_config(config)

    def _assert_all_layers_reject(
        self,
        base_url: str,
        headers: dict[str, str],
        settings_extra: dict[str, str] | None = None,
    ) -> None:
        self._assert_exporter_rejects(base_url, headers, settings_extra)
        self._assert_stage_and_guest_reject(base_url, headers, settings_extra)

    def test_current_custom_compat_settings_pass_all_layers(self) -> None:
        source = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Cloudflare AI Gateway Custom",
            "options": {
                "baseURL": SAFE_APM_BASE_URL,
                "apiKey": "",
                "headers": SAFE_APM_HEADERS,
            },
            "models": {
                "custom-ollama-cloud/kimi-k2.7-code": {"name": "Kimi K2.7 Code"},
            },
        }
        exported = exporter._v2_provider(
            CF_PROVIDER, source, ("custom-ollama-cloud/kimi-k2.7-code",),
        )
        self.assertEqual(exported["settings"]["baseURL"], SAFE_BASE_URL)
        config = _server_config()
        config["providers"][CF_PROVIDER] = exported

        stage._verify_v2_config(config)
        guest.verify_v2_config(config)

    def test_exporter_rejects_variant_reasoning_values_outside_allowlist(self) -> None:
        with self.assertRaises(exporter.ExportError):
            exporter._v2_variant({"reasoningEffort": "unbounded"}, "model.variant")

    def test_max_reasoning_effort_passes_all_validation_layers(self) -> None:
        source_model: dict[str, exporter.JsonValue] = {
            "name": "Kimi K3",
            "variants": {
                "default": {"body": {"thinking": {"type": "enabled"}}},
                "max": {"reasoningEffort": "max"},
            },
        }
        model = exporter._v2_model("custom-ollama-cloud/kimi-k3", source_model)
        config = _server_config()
        config["providers"][CF_PROVIDER]["models"]["custom-ollama-cloud/kimi-k3"] = model

        stage._verify_v2_config(config)
        guest.verify_v2_config(config)

        self.assertEqual(model["body"]["thinking"]["type"], "enabled")
        self.assertEqual(model["variants"][0]["settings"]["reasoningEffort"], "max")

    def test_exporter_rejects_credentials_in_variant_settings_headers_and_body(self) -> None:
        for variant in (
            {"settings": {"apiKey": "not-a-real-secret"}},
            {"headers": {"Authorization": "Bearer not-a-real-secret"}},
            {"body": {"options": {"apiKey": "not-a-real-secret"}}},
        ):
            with self.subTest(variant=variant), self.assertRaises(exporter.ExportError):
                exporter._v2_variant(variant, "model.variant")

    def test_all_layers_reject_unapproved_model_headers_and_body_fields(self) -> None:
        for options in (
            {"headers": {"X-Auth": "sk-example"}},
            {"body": {"temperature": 0.5}},
            {"body": {"thinking": {"type": "unapproved"}}},
            {"body": {"thinking": None}},
            {"body": {"thinking": {"type": ["enabled"]}}},
        ):
            with self.subTest(options=options):
                with self.assertRaises(exporter.ExportError):
                    exporter._v2_variant(options, "model.variant")
                with self.assertRaises(exporter.ExportError):
                    exporter._v2_model(
                        "custom-ollama-cloud/test",
                        {"name": "Test", "variants": {"default": options}},
                    )

                config = _server_config()
                config["providers"]["openai"]["models"]["gpt-6-luna"].update(options)
                with self.assertRaises(stage.StageError):
                    stage._verify_v2_config(config)
                with self.assertRaises(ValueError):
                    guest.verify_v2_config(config)

                config = _server_config()
                config["providers"]["openai"]["models"]["gpt-6-luna"]["variants"] = [
                    {"id": "unsafe", **options},
                ]
                with self.assertRaises(stage.StageError):
                    stage._verify_v2_config(config)
                with self.assertRaises(ValueError):
                    guest.verify_v2_config(config)

    def test_stage_and_guest_reject_credentials_in_model_variants(self) -> None:
        config = _server_config()
        config["providers"]["openai"]["models"]["gpt-6-luna"]["variants"] = [
            {"id": "unsafe", "body": {"options": {"apiKey": "not-a-real-secret"}}},
        ]

        with self.assertRaises(stage.StageError):
            stage._verify_v2_config(config)

        with self.assertRaises(ValueError):
            guest.verify_v2_config(config)

    def test_rejects_unsafe_base_urls_in_all_layers(self) -> None:
        for url in BAD_BASE_URLS:
            with self.subTest(url=url):
                self._assert_all_layers_reject(url, SAFE_HEADERS)

    def test_rejects_unsafe_headers_in_all_layers(self) -> None:
        for headers in BAD_HEADERS:
            with self.subTest(headers=headers):
                self._assert_all_layers_reject(SAFE_BASE_URL, headers)

    def test_rejects_guest_api_key_environment_reference_in_all_layers(self) -> None:
        self._assert_all_layers_reject(
            SAFE_BASE_URL,
            SAFE_HEADERS,
            {"apiKey": "${env:OC_CF_API_TOKEN}"},
        )

    def test_rejects_exact_duplicate_yaml_header_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "apm.yml").write_text(
                "provider:\n"
                "  openai:\n    whitelist: [gpt-6-luna]\n"
                "  cloudflare-ai-gateway-custom:\n"
                "    npm: '@ai-sdk/openai-compatible'\n"
                "    name: Cloudflare AI Gateway Custom\n"
                "    options:\n"
                f"      baseURL: '{SAFE_APM_BASE_URL}'\n"
                "      apiKey: ''\n"
                "      headers:\n"
                "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
                "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
                "    models:\n      custom-ollama-cloud/kimi-k2.7-code: {name: Kimi}\n"
                "opencode_v2:\n"
                "  default_model: openai/gpt-6-luna\n"
                "  deny_provider_fallback: true\n"
                "  deny_guest_auth: true\n"
                "  providers:\n"
                "    openai: {enabled: true, auth_method: docker_openai_oauth}\n"
                "    cloudflare-ai-gateway-custom: {enabled: true, auth_method: docker_custom_secret}\n",
                encoding="utf-8",
            )
            with self.assertRaises(exporter.ExportError):
                exporter._read_apm_source(root)

    def test_rejects_exact_duplicate_json_header_keys_in_stage_and_guest(self) -> None:
        server_raw = json.dumps(_server_config(), separators=(",", ":"))
        header = '"cf-aig-authorization":"Bearer {env:OC_CF_API_TOKEN}"'
        duplicate_header = f"{header},{header}"
        self.assertIn(header, server_raw)
        server_raw = server_raw.replace(header, duplicate_header, 1)
        client = json.dumps({"$schema": "https://opencode.ai/v2/cli.json", "plugins": []})
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / "opencode.jsonc").write_text(server_raw, encoding="utf-8")
            (bundle / "cli.json").write_text(client, encoding="utf-8")
            hashes = {
                name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
                for name in ("opencode.jsonc", "cli.json")
            }
            manifest = {
                "schema": "dotfiles-ai/sandbox-export/v0",
                "generator": "v0.2",
                "source": "apm.yml",
                "config_format": "opencode-v2",
                "source_sha256": "0" * 64,
                "opencode_version": "2.2.5",
                "plugins_exported": 0,
                "mcp_entries_exported": 0,
                "artifacts_sha256": hashes,
            }
            (bundle / "export-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises((ValueError, stage.StageError)):
                stage.verify_bundle(bundle, trusted_root=stage.BUNDLE_ROOT)
            with self.assertRaises(ValueError):
                guest.verify(bundle)

    def test_host_export_rejects_credential_material_in_generated_bundle(self) -> None:
        """Reject credentials at Host bundle generation, including after hash regeneration."""
        config = _server_config()
        config["providers"][CF_PROVIDER]["models"][
            "custom-ollama-cloud/kimi-k2.7-code"
        ]["name"] = "apiKey: " + "A" * 32
        v2_config = {
            key: config[key] for key in ("model", "providers", "policies")
        }

        with self.assertRaises(exporter.ExportError):
            exporter._build_files("bash", True, "a" * 64, v2_config)

    def test_stage_rejects_credential_material_in_hash_valid_bundle(self) -> None:
        """Reject credentials at Stage validation even when the bundle hash is updated."""
        config = _server_config()
        v2_config = {
            key: config[key] for key in ("model", "providers", "policies")
        }
        generated = exporter._build_files("bash", True, "a" * 64, v2_config)
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            for name, content in generated.items():
                (bundle / name).write_bytes(content)
            server_path = bundle / "opencode.jsonc"
            server = json.loads(server_path.read_bytes())
            server["providers"][CF_PROVIDER]["models"][
                "custom-ollama-cloud/kimi-k2.7-code"
            ]["name"] = "apiKey: " + "B" * 32
            server_raw = json.dumps(server, sort_keys=True, separators=(",", ":")).encode()
            server_path.write_bytes(server_raw)
            manifest_path = bundle / "export-manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["artifacts_sha256"]["opencode.jsonc"] = hashlib.sha256(
                server_raw,
            ).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaises(stage.StageError):
                stage.verify_bundle(bundle, trusted_root=stage.BUNDLE_ROOT)


if __name__ == "__main__":
    unittest.main()

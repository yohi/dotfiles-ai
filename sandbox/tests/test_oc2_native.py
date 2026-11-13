from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
import oc2_native  # noqa: E402
import oc2_assets  # noqa: E402


def apm_config(
    *,
    agents: str = (
        '  hephaestus:\n'
        '    mode: primary\n'
        '    model: openai/gpt-6-luna\n'
        '  oracle:\n'
        '    mode: subagent\n'
        '    model: openai/gpt-6-luna\n'
    ),
    mcp: str = '  enabled: false\n  servers: []\n',
    assets: str = '  - global-rules/AGENTS.global.md\n',
) -> bytes:
    return (
        'name: dotfiles-ai\n'
        'version: 2.0.0\n'
        'provider:\n'
        '  openai:\n'
        '    whitelist: [gpt-6-luna]\n'
        '  cloudflare-ai-gateway-custom:\n'
        '    models: {custom/test-model: {name: Test}}\n'
        'opencode_v2:\n'
        '  default_model: openai/gpt-6-luna\n'
        '  deny_provider_fallback: true\n'
        '  deny_guest_auth: true\n'
        '  providers:\n'
        '    openai:\n'
        '      enabled: true\n'
        '      auth_method: docker_openai_oauth\n'
        '    cloudflare-ai-gateway-custom:\n'
        '      enabled: true\n'
        '      auth_method: docker_custom_secret\n'
        'x-oc2-assets:\n'
        + assets
        + 'x-oc2-agents:\n'
        + agents
        + 'x-oc2-plugins:\n'
        + '  enabled: false\n'
        + '  allowlist: [superpowers]\n'
        + 'x-oc2-mcp:\n'
        + mcp
    ).encode('utf-8')


class NativeApmConfigTest(unittest.TestCase):
    def test_repository_apm_declares_the_approved_native_selection(self) -> None:
        """Verify the repository APM selects the approved Native configuration."""
        config = oc2_native.parse_apm_native((REPO / 'apm.yml').read_bytes(), require_oc2_assets=True)

        self.assertEqual(set(config.asset_sources), set(oc2_native.ASSET_SOURCES))
        payload = oc2_native.build_native_payload(config)
        self.assertEqual(set(payload['agents']), {'hephaestus', 'oracle'})
        self.assertEqual(payload['plugins'], {
            'enabled': True, 'allowlist': ['superpowers'],
        })
        self.assertEqual(payload['mcp'], {
            'enabled': True, 'servers': ['oc2-status'],
        })
        self.assertEqual(
            tuple(plugin.value for plugin in config.phase4_plugins.allowlist),
            ('akane', 'sibyl'),
        )

    def test_asset_manifest_carries_the_native_config_and_apm_identity(self):
        files = {
            'index.js': b'export default {}\n',
            'package.json': b'{"name":"superpowers","version":"6.4.2"}\n',
            '.opencode/plugins/superpowers.js': b'export default {}\n',
            'skills/demo/SKILL.md': b'---\nname: demo\n---\n',
        }
        artifact = oc2_assets.PluginArtifact(
            source_commit=oc2_native.SUPERPOWERS_COMMIT,
            files=tuple(
                oc2_assets.PluginFile(
                    name, content, hashlib.sha256(content).hexdigest(),
                )
                for name, content in sorted(files.items())
            ),
            tree_files=tuple(
                (name, hashlib.sha256(content).hexdigest())
                for name, content in sorted(files.items())
            ),
        )
        with patch.object(oc2_assets, 'resolve_superpowers_plugin', return_value=artifact):
            raw, asset_sha = oc2_assets.build(REPO, plugin_dir=pathlib.Path('/fixture/superpowers'))
        payload = json.loads(raw)
        native = json.loads(payload['files'][oc2_assets.NATIVE_TARGET])

        self.assertEqual(asset_sha, hashlib.sha256(raw).hexdigest())
        self.assertEqual(native['source_sha256'], hashlib.sha256((REPO / 'apm.yml').read_bytes()).hexdigest())
        self.assertEqual(set(native['agents']), {'hephaestus', 'oracle'})
        self.assertEqual(native['mcp'], {
            'enabled': True, 'servers': ['oc2-status'],
        })
        self.assertEqual(native['plugins'], {
            'enabled': True, 'allowlist': ['superpowers'],
        })

    def test_valid_config_emits_only_two_fixed_native_agents_and_disabled_mcp(self) -> None:
        """Accept the two fixed Agents and emit disabled Plugin/MCP selections."""
        raw = apm_config()

        config = oc2_native.parse_apm_native(raw)
        payload = oc2_native.build_native_payload(config)

        self.assertEqual(config.source_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(set(payload['agents']), {'hephaestus', 'oracle'})
        self.assertEqual(payload['agents']['hephaestus']['mode'], 'primary')
        self.assertEqual(payload['agents']['oracle']['mode'], 'subagent')
        self.assertEqual(payload['agents']['oracle']['model'], 'openai/gpt-6-luna')
        self.assertEqual(payload['mcp'], {'enabled': False, 'servers': []})

    def test_skill_frontmatter_is_validated_against_native_discovery_name(self) -> None:
        """Accept matching Skill metadata and reject missing or mismatched fields."""
        valid = (
            '---\nname: config-modernizer\n'
            'description: Modernizes approved OpenCode configuration.\n---\nBody\n'
        )
        invalid_name = valid.replace('name: config-modernizer', 'name: other-skill')
        missing_description = (
            '---\nname: config-modernizer\n---\nBody\n'
        )

        self.assertEqual(
            oc2_native.validate_skill_frontmatter('config-modernizer', valid),
            {'name': 'config-modernizer', 'description': 'Modernizes approved OpenCode configuration.'},
        )
        with self.assertRaisesRegex(ValueError, 'name mismatch'):
            oc2_native.validate_skill_frontmatter('config-modernizer', invalid_name)
        with self.assertRaisesRegex(ValueError, 'description'):
            oc2_native.validate_skill_frontmatter('config-modernizer', missing_description)

    def test_existing_apm_skills_have_native_discovery_frontmatter(self) -> None:
        """Verify selected repository Skills expose native discovery metadata."""
        for name in ('agent-skill-architect', 'config-modernizer'):
            path = REPO / 'agent-skills' / 'custom' / name / 'SKILL.md'
            frontmatter = oc2_native.validate_skill_frontmatter(
                name, path.read_text(encoding='utf-8'),
            )
            with self.subTest(name=name):
                self.assertEqual(frontmatter['name'], name)
                self.assertTrue(frontmatter['description'])

    def test_agent_permissions_keep_oracle_read_only_and_delegation_manual(self) -> None:
        """Allow manual shell/subagent actions and keep Oracle read-only."""
        payload = oc2_native.build_native_payload(oc2_native.parse_apm_native(apm_config()))
        hephaestus = payload['agents']['hephaestus']
        oracle = payload['agents']['oracle']
        hephaestus_permissions = {
            (rule['action'], rule['resource']): rule['effect']
            for rule in hephaestus['permissions']
        }
        oracle_permissions = {
            (rule['action'], rule['resource']): rule['effect']
            for rule in oracle['permissions']
        }

        self.assertEqual(hephaestus_permissions[('edit', '*')], 'ask')
        self.assertEqual(hephaestus_permissions[('shell', '*')], 'ask')
        self.assertEqual(hephaestus_permissions[('subagent', '*')], 'ask')
        self.assertEqual(hephaestus_permissions[('grep', '*')], 'allow')
        self.assertEqual(oracle_permissions[('*', '*')], 'deny')
        self.assertEqual(oracle_permissions[('read', '*')], 'allow')
        self.assertEqual(oracle_permissions[('edit', '*')], 'deny')
        self.assertEqual(oracle_permissions[('shell', '*')], 'deny')
        self.assertEqual(oracle_permissions[('subagent', '*')], 'deny')
        self.assertEqual(oracle_permissions[('webfetch', '*')], 'deny')
        self.assertEqual(oracle_permissions[('websearch', '*')], 'deny')
        self.assertEqual(oracle_permissions[('mcp.use', '*')], 'deny')
        self.assertEqual(oracle_permissions[('grep', '*')], 'allow')
        self.assertNotIn('fallback_models', oracle)
        self.assertNotIn('fallback_models', hephaestus)

    def test_unknown_agent_is_rejected(self) -> None:
        """Reject Agent names outside the fixed allowlist."""
        raw = apm_config(agents=(
            '  sisyphus:\n'
            '    mode: primary\n'
            '    model: openai/gpt-6-luna\n'
        ))

        with self.assertRaisesRegex(ValueError, 'unapproved agent'):
            oc2_native.parse_apm_native(raw)

    def test_agent_model_must_be_in_the_v2_apm_allowlist(self) -> None:
        """Reject Native Agent models absent from the OpenAI APM whitelist."""
        raw = apm_config(agents=(
            '  hephaestus:\n'
            '    mode: primary\n'
            '    model: openai/not-allowed\n'
            '  oracle:\n'
            '    mode: subagent\n'
            '    model: openai/gpt-6-luna\n'
        ))

        with self.assertRaisesRegex(ValueError, 'unapproved agent model'):
            oc2_native.parse_apm_native(raw)

    def test_agent_model_is_independent_of_the_approved_v2_default(self) -> None:
        """Keep each approved Agent model fixed when the provider default changes."""
        raw = apm_config().replace(
            b'whitelist: [gpt-6-luna]',
            b'whitelist: [gpt-6-luna, gpt-6.1-sol]',
        ).replace(
            b'default_model: openai/gpt-6-luna',
            b'default_model: openai/gpt-6.1-sol',
        )

        config = oc2_native.parse_apm_native(raw)
        payload = oc2_native.build_native_payload(config)

        self.assertEqual(payload['agents']['hephaestus']['model'], 'openai/gpt-6-luna')
        self.assertEqual(payload['agents']['oracle']['model'], 'openai/gpt-6-luna')

    def test_agent_model_change_is_taken_from_the_apm_provider_catalog(self):
        raw = apm_config().replace(
            b'whitelist: [gpt-6-luna]',
            b'whitelist: [gpt-6-luna, gpt-6.1-sol]',
        ).replace(
            b'default_model: openai/gpt-6-luna',
            b'default_model: openai/gpt-6.1-sol',
        ).replace(
            b'model: openai/gpt-6-luna',
            b'model: openai/gpt-6.1-sol',
        )

        payload = oc2_native.build_native_payload(oc2_native.parse_apm_native(raw))

        self.assertEqual(payload['agents']['hephaestus']['model'], 'openai/gpt-6.1-sol')
        self.assertEqual(payload['agents']['oracle']['model'], 'openai/gpt-6.1-sol')

    def test_runtime_options_are_parsed_from_apm_and_preserve_ping_safety(self):
        raw = (REPO / 'apm.yml').read_bytes().replace(
            b'stage1Ms: 180000', b'stage1Ms: 240000',
        )

        config = oc2_native.parse_apm_native(raw, require_oc2_assets=True)

        self.assertEqual(config.runtime.watchdog.stage1_ms, 240000)
        self.assertGreaterEqual(config.runtime.watchdog.stage2_ms, 86400000)
        self.assertLessEqual(config.runtime.watchdog.max_pings, 1)
        self.assertTrue(config.runtime.sibyl_observer.enabled)
        self.assertEqual(config.runtime.theme, 'tokyonight')

    def test_runtime_rejects_ping_safety_regression_and_unknown_theme(self):
        source = (REPO / 'apm.yml').read_bytes()
        for changed in (
            source.replace(b'stage2Ms: 86400000', b'stage2Ms: 180000'),
            source.replace(b'theme: tokyonight', b'theme: unapproved-theme'),
        ):
            with self.subTest(changed=changed), self.assertRaises(oc2_native.NativeConfigError):
                oc2_native.parse_apm_native(changed, require_oc2_assets=True)

    def test_mcp_execution_timeout_is_read_from_apm_runtime_source(self):
        source = (REPO / 'apm.yml').read_bytes().replace(
            b'mcp_timeout: 120000', b'mcp_timeout: 45000',
        )

        config = oc2_native.parse_apm_native(source, require_oc2_assets=True)

        self.assertEqual(config.runtime.mcp_execution_timeout_ms, 45000)

    def test_mcp_execution_timeout_rejects_out_of_bounds_values(self):
        source = (REPO / 'apm.yml').read_bytes()
        for bad_timeout in (b'0', b'600001'):
            changed = source.replace(b'mcp_timeout: 120000', b'mcp_timeout: ' + bad_timeout)
            with self.subTest(bad_timeout=bad_timeout), self.assertRaises(
                oc2_native.NativeConfigError,
            ):
                oc2_native.parse_apm_native(changed, require_oc2_assets=True)

    def test_yaml_integer_spellings_match_safe_loader_values(self) -> None:
        """Parse octal and hexadecimal YAML integers using YAML semantics."""
        source = (REPO / 'apm.yml').read_bytes()

        for raw_value, expected in ((b'0100000', 32768), (b'0x1d4c0', 120000)):
            changed = source.replace(b'mcp_timeout: 120000', b'mcp_timeout: ' + raw_value)
            with self.subTest(raw_value=raw_value):
                config = oc2_native.parse_apm_native(changed, require_oc2_assets=True)
                self.assertEqual(config.runtime.mcp_execution_timeout_ms, expected)

    def test_watchdog_stage2_accepts_timer_maximum_and_rejects_larger_values(self) -> None:
        """Enforce the maximum timer duration while retaining the existing lower bound."""
        source = (REPO / 'apm.yml').read_bytes()
        at_maximum = source.replace(
            b'stage2Ms: 86400000', b'stage2Ms: 2147483647',
        )
        above_maximum = source.replace(
            b'stage2Ms: 86400000', b'stage2Ms: 2147483648',
        )

        config = oc2_native.parse_apm_native(at_maximum, require_oc2_assets=True)
        self.assertEqual(config.runtime.watchdog.stage2_ms, 2147483647)
        with self.assertRaises(oc2_native.NativeConfigError):
            oc2_native.parse_apm_native(above_maximum, require_oc2_assets=True)

    def test_agent_fallback_fields_are_rejected(self) -> None:
        """Reject unsupported fallback model fields in Agent definitions."""
        raw = apm_config(agents=(
            '  hephaestus:\n'
            '    mode: primary\n'
            '    model: openai/gpt-6-luna\n'
            '    fallback_models: [cloudflare-ai-gateway-custom/custom-ollama-cloud/kimi-k2.7-code]\n'
            '  oracle:\n'
            '    mode: subagent\n'
            '    model: openai/gpt-6-luna\n'
        ))

        with self.assertRaisesRegex(ValueError, 'unsupported agent fields'):
            oc2_native.parse_apm_native(raw)

    def test_mcp_must_remain_disabled_and_empty(self) -> None:
        """Reject enabled MCP and non-allowlisted MCP server selections."""
        for mcp in (
            '  enabled: true\n  servers: []\n',
            '  enabled: false\n  servers: [codegraph]\n',
        ):
            with self.subTest(mcp=mcp), self.assertRaises(ValueError):
                oc2_native.parse_apm_native(apm_config(mcp=mcp))

    def test_asset_paths_must_be_unique_and_allowlisted(self) -> None:
        """Reject duplicate and path-traversing asset selections."""
        for assets in (
            '  - global-rules/AGENTS.global.md\n  - global-rules/AGENTS.global.md\n',
            '  - ../outside.md\n',
        ):
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                oc2_native.parse_apm_native(apm_config(assets=assets))

    def test_unknown_asset_path_is_rejected(self) -> None:
        """Reject asset sources absent from the fixed source allowlist."""
        raw = apm_config(assets='  - docs/unreviewed.md\n')

        with self.assertRaisesRegex(ValueError, 'unapproved asset'):
            oc2_native.parse_apm_native(raw)

    def test_missing_oc2_extensions_remain_compatible_with_config_only_exports(self) -> None:
        """Allow extension-free APM in ordinary config-only exports."""
        config = oc2_native.parse_apm_native(b'name: fixture\nversion: 1\n')

        self.assertEqual(config.asset_sources, ())
        self.assertEqual(config.agents, ())
        self.assertEqual(oc2_native.build_native_payload(config)['mcp'],
                         {'enabled': False, 'servers': []})

    def test_missing_oc2_extensions_are_rejected_in_verification_mode(self) -> None:
        """Reject extension-free APM when verification-only selection is requested."""
        with self.assertRaisesRegex(ValueError, 'extensions are required'):
            oc2_native.parse_apm_native(
                b'name: fixture\nversion: 1\n', verification_only=True,
            )

    def test_missing_oc2_extensions_are_rejected_when_assets_are_required(self) -> None:
        """Reject extension-free APM when OC2 assets are required."""
        with self.assertRaisesRegex(ValueError, 'extensions are required'):
            oc2_native.parse_apm_native(
                b'name: fixture\nversion: 1\n', require_oc2_assets=True,
            )

    def test_partial_oc2_extensions_are_rejected(self) -> None:
        """Reject APM documents that declare only part of the OC2 extension set."""
        raw = b'name: fixture\nversion: 1\nx-oc2-agents: {}\n'

        with self.assertRaisesRegex(ValueError, 'extensions must be declared together'):
            oc2_native.parse_apm_native(raw)

    def test_runtime_selection_without_complete_oc2_extensions_is_rejected(self):
        raw = b'name: fixture\nx-oc2-runtime: {enabled: true}\n'

        with self.assertRaisesRegex(ValueError, 'Runtime requires'):
            oc2_native.parse_apm_native(raw)

    def test_duplicate_mapping_keys_are_rejected(self) -> None:
        """Reject duplicate keys in Native APM mappings."""
        raw = apm_config().replace(
            b'    mode: primary\n',
            b'    mode: primary\n    mode: subagent\n',
            1,
        )

        with self.assertRaisesRegex(ValueError, 'duplicate'):
            oc2_native.parse_apm_native(raw)


if __name__ == '__main__':
    unittest.main()

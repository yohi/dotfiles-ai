from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import unittest

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
        'opencode_v2:\n'
        '  default_model: openai/gpt-6-luna\n'
        '  deny_provider_fallback: true\n'
        '  deny_guest_auth: true\n'
        '  providers:\n'
        '    openai:\n'
        '      enabled: true\n'
        '    cloudflare-ai-gateway-custom:\n'
        '      enabled: true\n'
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
    def test_repository_apm_declares_the_approved_native_selection(self):
        config = oc2_native.parse_apm_native((REPO / 'apm.yml').read_bytes(), require_oc2_assets=True)

        self.assertEqual(set(config.asset_sources), set(oc2_native.ASSET_SOURCES))
        payload = oc2_native.build_native_payload(config)
        self.assertEqual(set(payload['agents']), {'hephaestus', 'oracle'})
        self.assertEqual(payload['plugins'], {'enabled': False, 'allowlist': []})
        self.assertEqual(payload['mcp'], {'enabled': False, 'servers': []})

    def test_asset_manifest_carries_the_native_config_and_apm_identity(self):
        raw, asset_sha = oc2_assets.build(REPO)
        payload = json.loads(raw)
        native = json.loads(payload['files'][oc2_assets.NATIVE_TARGET])

        self.assertEqual(asset_sha, hashlib.sha256(raw).hexdigest())
        self.assertEqual(native['source_sha256'], hashlib.sha256((REPO / 'apm.yml').read_bytes()).hexdigest())
        self.assertEqual(set(native['agents']), {'hephaestus', 'oracle'})
        self.assertEqual(native['mcp'], {'enabled': False, 'servers': []})

    def test_valid_config_emits_only_two_fixed_native_agents_and_disabled_mcp(self):
        raw = apm_config()

        config = oc2_native.parse_apm_native(raw)
        payload = oc2_native.build_native_payload(config)

        self.assertEqual(config.source_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(set(payload['agents']), {'hephaestus', 'oracle'})
        self.assertEqual(payload['agents']['hephaestus']['mode'], 'primary')
        self.assertEqual(payload['agents']['oracle']['mode'], 'subagent')
        self.assertEqual(payload['agents']['oracle']['model'], 'openai/gpt-6-luna')
        self.assertEqual(payload['mcp'], {'enabled': False, 'servers': []})

    def test_skill_frontmatter_is_validated_against_native_discovery_name(self):
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

    def test_existing_apm_skills_have_native_discovery_frontmatter(self):
        for name in ('agent-skill-architect', 'config-modernizer'):
            path = REPO / 'agent-skills' / 'custom' / name / 'SKILL.md'
            frontmatter = oc2_native.validate_skill_frontmatter(
                name, path.read_text(encoding='utf-8'),
            )
            with self.subTest(name=name):
                self.assertEqual(frontmatter['name'], name)
                self.assertTrue(frontmatter['description'])

    def test_agent_permissions_keep_oracle_read_only_and_delegation_manual(self):
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
        self.assertEqual(hephaestus_permissions[('bash', '*')], 'ask')
        self.assertEqual(hephaestus_permissions[('task', '*')], 'ask')
        self.assertEqual(oracle_permissions[('*', '*')], 'deny')
        self.assertEqual(oracle_permissions[('read', '*')], 'allow')
        self.assertEqual(oracle_permissions[('edit', '*')], 'deny')
        self.assertEqual(oracle_permissions[('bash', '*')], 'deny')
        self.assertEqual(oracle_permissions[('task', '*')], 'deny')
        self.assertEqual(oracle_permissions[('webfetch', '*')], 'deny')
        self.assertEqual(oracle_permissions[('websearch', '*')], 'deny')
        self.assertEqual(oracle_permissions[('mcp.use', '*')], 'deny')
        self.assertNotIn('fallback_models', oracle)
        self.assertNotIn('fallback_models', hephaestus)

    def test_unknown_agent_is_rejected(self):
        raw = apm_config(agents=(
            '  sisyphus:\n'
            '    mode: primary\n'
            '    model: openai/gpt-6-luna\n'
        ))

        with self.assertRaisesRegex(ValueError, 'unapproved agent'):
            oc2_native.parse_apm_native(raw)

    def test_agent_model_must_be_in_the_v2_apm_allowlist(self):
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

    def test_agent_model_is_independent_of_the_approved_v2_default(self):
        raw = apm_config().replace(
            b'default_model: openai/gpt-6-luna',
            b'default_model: openai/gpt-6.1-sol',
        )

        config = oc2_native.parse_apm_native(raw)
        payload = oc2_native.build_native_payload(config)

        self.assertEqual(payload['agents']['hephaestus']['model'], 'openai/gpt-6-luna')
        self.assertEqual(payload['agents']['oracle']['model'], 'openai/gpt-6-luna')

    def test_agent_fallback_fields_are_rejected(self):
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

    def test_mcp_must_remain_disabled_and_empty(self):
        for mcp in (
            '  enabled: true\n  servers: []\n',
            '  enabled: false\n  servers: [codegraph]\n',
        ):
            with self.subTest(mcp=mcp), self.assertRaises(ValueError):
                oc2_native.parse_apm_native(apm_config(mcp=mcp))

    def test_asset_paths_must_be_unique_and_allowlisted(self):
        for assets in (
            '  - global-rules/AGENTS.global.md\n  - global-rules/AGENTS.global.md\n',
            '  - ../outside.md\n',
        ):
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                oc2_native.parse_apm_native(apm_config(assets=assets))

    def test_unknown_asset_path_is_rejected(self):
        raw = apm_config(assets='  - docs/unreviewed.md\n')

        with self.assertRaisesRegex(ValueError, 'unapproved asset'):
            oc2_native.parse_apm_native(raw)

    def test_missing_oc2_extensions_remain_compatible_with_config_only_exports(self):
        config = oc2_native.parse_apm_native(b'name: fixture\nversion: 1\n')

        self.assertEqual(config.asset_sources, ())
        self.assertEqual(config.agents, ())
        self.assertEqual(oc2_native.build_native_payload(config)['mcp'],
                         {'enabled': False, 'servers': []})

    def test_partial_oc2_extensions_are_rejected(self):
        raw = b'name: fixture\nversion: 1\nx-oc2-agents: {}\n'

        with self.assertRaisesRegex(ValueError, 'extensions must be declared together'):
            oc2_native.parse_apm_native(raw)

    def test_duplicate_mapping_keys_are_rejected(self):
        raw = apm_config().replace(
            b'    mode: primary\n',
            b'    mode: primary\n    mode: subagent\n',
            1,
        )

        with self.assertRaisesRegex(ValueError, 'duplicate'):
            oc2_native.parse_apm_native(raw)


if __name__ == '__main__':
    unittest.main()

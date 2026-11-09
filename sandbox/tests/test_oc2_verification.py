from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest.mock import ANY, patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import oc2  # noqa: E402
import oc2_assets  # noqa: E402
import oc2_guest  # noqa: E402
import oc2_identity  # noqa: E402
import oc2_native  # noqa: E402


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def destination_status(self, _name: str, _destination: str) -> int:
        return 0

    def sbx(self, *args: str, **_kwargs: bool) -> str:
        self.calls.append(args)
        return ''


class VerificationRuntimePreparationTest(unittest.TestCase):
    def test_unified_launch_stages_one_config_assets_and_plugin_bundle(self):
        runner = FakeRunner()
        request = oc2.SandboxLaunch(
            'oc2-unified-test', 'a' * 64, oc2.PINNED[0], '/workspace',
            pathlib.Path('/tmp/config.json'),
            assets_file=pathlib.Path('/tmp/assets.json'), assets_sha='b' * 64,
            bundle=pathlib.Path('/tmp/bundle'), manifest_sha='c' * 64,
            phase4_plugin_file=pathlib.Path('/tmp/phase4.json'),
            phase4_plugins_sha='d' * 64,
        )

        with (
            patch.object(oc2, 'stage') as stage,
            patch.object(oc2, 'oauth_helper_source', return_value='helper'),
        ):
            oc2.launch(runner, request)

        stage.assert_called_once_with(
            runner, request.name, request.bundle, request.manifest_sha,
            oc2.HERE / 'oc2_guest.py', request.assets_file, request.assets_sha,
            phase4_plugin_file=request.phase4_plugin_file,
            phase4_plugins_sha=request.phase4_plugins_sha,
        )

    def test_verification_refuses_to_create_or_reuse_an_incompatible_sandbox(self):
        runner = FakeRunner()
        with (patch.object(oc2, 'Runner', return_value=runner),
              patch.object(oc2, 'is_compatible_sandbox', return_value=False),
              self.assertRaisesRegex(oc2.Stop, 'existing compatible')):
            oc2.prepare_verification_runtime(
                pathlib.Path('/repo'), 'oc2-test', pathlib.Path('/fixture/superpowers'),
            )

        self.assertEqual(runner.calls, [])

    def test_phase4_refuses_an_incompatible_sandbox_without_staging(self):
        runner = FakeRunner()
        with (
            patch.object(oc2, 'Runner', return_value=runner),
            patch.object(oc2, 'is_compatible_sandbox', return_value=False),
            self.assertRaisesRegex(oc2.Stop, 'existing compatible'),
        ):
            oc2.prepare_phase4_runtime(
                pathlib.Path('/repo'),
                oc2.Phase4RuntimeRequest(
                    'oc2-phase4-test',
                    pathlib.Path('/fixture/superpowers'),
                    oc2.Phase4ArtifactPaths(
                        pathlib.Path('/fixture/akane.tgz'),
                        pathlib.Path('/fixture/sibyl.tgz'),
                    ),
                ),
            )

        self.assertEqual(runner.calls, [])

    def test_phase4_cli_rejects_non_dedicated_sandbox_name_before_runner(self):
        with patch.object(oc2, 'Runner', side_effect=AssertionError('no Sandbox CLI')):
            result = oc2.main([
                '--phase4-plugins',
                '--prepare-only',
                '--sandbox',
                'oc2-v2',
                '--plugin-dir',
                '/fixture/superpowers',
                '--akane-artifact',
                '/fixture/akane.tgz',
                '--sibyl-artifact',
                '/fixture/sibyl.tgz',
            ])

        self.assertEqual(result, 1)

    def test_phase4_dry_run_accepts_base_superpowers_and_artifact_inputs(self):
        with patch.object(oc2, 'Runner', side_effect=AssertionError('no Sandbox commands')):
            result = oc2.main([
                '--phase4-plugins',
                '--prepare-only',
                '--dry-run',
                '--sandbox',
                'oc2-phase4-test',
                '--plugin-dir',
                '/fixture/superpowers',
                '--akane-artifact',
                '/fixture/akane.tgz',
                '--sibyl-artifact',
                '/fixture/sibyl.tgz',
            ])

        self.assertEqual(result, 0)

    def test_phase4_stages_two_pinned_assets_with_phase4_runtime_identity(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / 'bundle'
            with (
                patch.object(oc2, 'Runner', return_value=runner),
                patch.object(oc2, 'is_compatible_sandbox', return_value=True),
                patch.object(runner, 'destination_status', return_value=0),
                patch.object(oc2, 'cli_path', return_value=oc2.PINNED[0]),
                patch.object(oc2, 'export_v2_config', return_value=output / 'opencode.jsonc'),
                patch('sandbox.scripts.stage_opencode_v2.verify_bundle', return_value='a' * 64),
                patch.object(oc2_assets, 'build', return_value=(b'base-assets', 'b' * 64)),
                patch.object(oc2_assets, 'build_phase4_plugins', return_value=(b'phase4-assets', 'c' * 64)),
                patch.object(oc2, 'stage') as stage,
                patch.object(oc2, 'provision_cli', side_effect=AssertionError('no CLI install')),
                patch.object(oc2, 'launch', side_effect=AssertionError('no OpenCode start')),
                patch.object(oc2, 'ensure_cloudflare_credential', side_effect=AssertionError('no credentials')),
            ):
                actual = oc2.prepare_phase4_runtime(
                    pathlib.Path('/repo'),
                    oc2.Phase4RuntimeRequest(
                        'oc2-phase4-test',
                        pathlib.Path('/fixture/superpowers'),
                        oc2.Phase4ArtifactPaths(
                            pathlib.Path('/fixture/akane.tgz'),
                            pathlib.Path('/fixture/sibyl.tgz'),
                        ),
                    ),
                )

        stage.assert_called_once()
        self.assertEqual(stage.call_args.kwargs['phase4_plugins_sha'], 'c' * 64)
        fingerprint = oc2_identity.phase4_generator_fingerprint((
            oc2.HERE / 'oc2_guest.py',
            oc2.HERE / 'oc2_agent_native.py',
            oc2.HERE / 'oc2_identity.py',
            oc2.HERE / 'oc2_phase4_policy.py',
        ))
        self.assertEqual(actual, oc2_identity.phase4_runtime_identity_sha256(
            oc2_identity.Phase4RuntimeIdentity('a' * 64, 'b' * 64, 'c' * 64, fingerprint),
        ))

    def test_verification_stages_without_credentials_cli_install_or_launch(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / 'bundle'
            with (
                patch.object(oc2, 'Runner', return_value=runner),
                patch.object(oc2, 'is_compatible_sandbox', return_value=True),
                patch.object(oc2, 'cli_path', return_value=oc2.PINNED[0]),
                patch.object(oc2, 'export_v2_config', return_value=output / 'opencode.jsonc') as export,
                patch('sandbox.scripts.stage_opencode_v2.verify_bundle', return_value='a' * 64),
                patch.object(oc2_assets, 'build', return_value=(b'asset', 'b' * 64)),
                patch.object(oc2, 'stage') as stage,
                patch.object(oc2, 'provision_cli', side_effect=AssertionError('no install')),
                patch.object(oc2, 'launch', side_effect=AssertionError('no OpenCode start')),
                patch.object(
                    oc2, 'ensure_cloudflare_credential',
                    side_effect=AssertionError('no credentials'),
                ),
            ):
                oc2.prepare_verification_runtime(
                    pathlib.Path('/repo'), 'oc2-test', pathlib.Path('/fixture/superpowers'),
                )

        export.assert_called_once_with(
            pathlib.Path('/repo'), ANY, verification_only=True,
        )
        stage.assert_called_once()
        self.assertEqual(runner.calls, [])

    def test_verification_identity_includes_generator_fingerprint(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / 'bundle'
            fingerprint = oc2_identity.verification_generator_fingerprint(
                oc2.HERE / 'oc2_guest.py',
                oc2.HERE / 'oc2_agent_native.py',
                oc2.HERE / 'oc2_identity.py',
            )
            expected = oc2_identity.runtime_identity_sha256(
                'a' * 64, 'b' * 64, fingerprint,
            )
            with (
                patch.object(oc2, 'Runner', return_value=runner),
                patch.object(oc2, 'is_compatible_sandbox', return_value=True),
                patch.object(oc2, 'cli_path', return_value=oc2.PINNED[0]),
                patch.object(oc2, 'export_v2_config', return_value=output / 'opencode.jsonc'),
                patch('sandbox.scripts.stage_opencode_v2.verify_bundle', return_value='a' * 64),
                patch.object(oc2_assets, 'build', return_value=(b'asset', 'b' * 64)),
                patch.object(oc2, 'stage'),
            ):
                actual = oc2.prepare_verification_runtime(
                    pathlib.Path('/repo'), 'oc2-test', pathlib.Path('/fixture/superpowers'),
                )

        self.assertEqual(actual, expected)
        self.assertEqual(
            actual[:16],
            oc2_guest.runtime_path(
                'a' * 64, 'b' * 64, generator_fingerprint=fingerprint,
            ).name,
        )

    def test_verification_refuses_existing_runtime_identity_before_staging(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / 'bundle'
            with (
                patch.object(oc2, 'Runner', return_value=runner),
                patch.object(oc2, 'is_compatible_sandbox', return_value=True),
                patch.object(oc2, 'cli_path', return_value=oc2.PINNED[0]),
                patch.object(oc2, 'export_v2_config', return_value=output / 'opencode.jsonc'),
                patch('sandbox.scripts.stage_opencode_v2.verify_bundle', return_value='a' * 64),
                patch.object(oc2_assets, 'build', return_value=(b'asset', 'b' * 64)),
                patch.object(oc2, 'stage') as stage,
                patch.object(runner, 'destination_status', return_value=10),
                self.assertRaisesRegex(oc2.Stop, 'identity already exists'),
            ):
                oc2.prepare_verification_runtime(
                    pathlib.Path('/repo'), 'oc2-test', pathlib.Path('/fixture/superpowers'),
                )

        stage.assert_not_called()


if __name__ == '__main__':
    unittest.main()

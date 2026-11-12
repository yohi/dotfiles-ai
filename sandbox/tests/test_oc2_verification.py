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


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def destination_status(self, _name: str, _destination: str) -> int:
        return 0

    def sbx(self, *args: str, **_kwargs: bool) -> str:
        self.calls.append(args)
        return ''


class VerificationRuntimePreparationTest(unittest.TestCase):
    def test_verification_refuses_to_create_or_reuse_an_incompatible_sandbox(self):
        runner = FakeRunner()
        with (patch.object(oc2, 'Runner', return_value=runner),
              patch.object(oc2, 'is_compatible_sandbox', return_value=False),
              self.assertRaisesRegex(oc2.Stop, 'existing compatible')):
            oc2.prepare_verification_runtime(
                pathlib.Path('/repo'), 'oc2-test', pathlib.Path('/fixture/superpowers'),
            )

        self.assertEqual(runner.calls, [])

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
                patch.object(
                    oc2_assets, 'export_superpowers_tree',
                    side_effect=lambda _repo, _plugin, destination: destination.mkdir(),
                    create=True,
                ) as export_tree,
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
        export_tree.assert_called_once()
        tree_source = export_tree.call_args.args[2]
        self.assertEqual(tree_source.name, 'verification-superpowers')
        self.assertEqual(stage.call_args.kwargs, {'superpowers_source': tree_source})
        self.assertEqual(stage.call_args.args[0:2], (runner, 'oc2-test'))
        self.assertEqual(stage.call_args.args[3:7], (
            'a' * 64, oc2.HERE / 'oc2_guest.py', tree_source.parent / 'assets.json', 'b' * 64,
        ))
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
                patch.object(oc2_assets, 'export_superpowers_tree'),
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
                patch.object(oc2_assets, 'export_superpowers_tree'),
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

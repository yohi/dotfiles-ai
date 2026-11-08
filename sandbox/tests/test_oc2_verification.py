from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest.mock import ANY, patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import oc2
import oc2_assets


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

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
                pathlib.Path('/repo'), 'oc2-test', pathlib.Path('/plugin'),
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
                patch.object(oc2, 'stage') as stage,
                patch.object(oc2, 'provision_cli', side_effect=AssertionError('no install')),
                patch.object(oc2, 'launch', side_effect=AssertionError('no OpenCode start')),
                patch.object(
                    oc2, 'ensure_cloudflare_credential',
                    side_effect=AssertionError('no credentials'),
                ),
            ):
                oc2.prepare_verification_runtime(
                    pathlib.Path('/repo'), 'oc2-test', pathlib.Path('/plugin'),
                )

        export.assert_called_once_with(
            pathlib.Path('/repo'), ANY, verification_only=True,
        )
        stage.assert_called_once()
        self.assertEqual(runner.calls, [])


if __name__ == '__main__':
    unittest.main()

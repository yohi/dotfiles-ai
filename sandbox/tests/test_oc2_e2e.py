from __future__ import annotations

import contextlib
import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import oc2  # noqa: E402


class FakeSbx:
    def __init__(self) -> None:
        self.created = False
        self.installed = False
        self.clone_source: pathlib.Path | None = None
        self.clone_source_content: str | None = None
        self.clone_source_remotes: str | None = None
        self.clone_source_log_subject: str | None = None
        self.clone_source_has_http_header = False
        self.calls: list[tuple[str, ...]] = []
        self.timeouts: list[int | None] = []

    def sbx(self, *args: str, capture: bool = False, tty: bool = False,
            timeout: int | None = 180) -> str:
        self.calls.append(args)
        self.timeouts.append(None if tty else timeout)
        if args == ('version',):
            return 'sbx version v0.49.2 test\n'
        if args == ('create', '--help'):
            return '  --clone  private in-container clone\n'
        if args == ('ls', '-q'):
            return 'oc2-test\n' if self.created else ''
        if args[:1] == ('create',):
            self.created = True
            self.clone_source = pathlib.Path(args[-1])
            self.clone_source_content = (self.clone_source / 'main.py').read_text()
            self.clone_source_remotes = subprocess.run(
                ['git', '-C', str(self.clone_source), 'remote'],
                capture_output=True, text=True, check=True,
            ).stdout
            self.clone_source_log_subject = subprocess.run(
                ['git', '-C', str(self.clone_source), 'log', '-1', '--format=%s'],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            header = subprocess.run(
                ['git', 'config', '--file', str(self.clone_source / '.git' / 'config'),
                 '--get-regexp', r'^http\..*\.extraheader$'],
                capture_output=True, text=True, check=False,
            )
            self.clone_source_has_http_header = header.returncode == 0
            return ''
        if args[:2] == ('exec', 'oc2-test'):
            command = args[2:]
            if (command[:2] == ('sh', '-c')
                    and command[4] == oc2.PINNED[0]):
                return 'opencode v2.2.5\n' if self.installed else ''
            if command == ('pwd',):
                return '/home/agent/workspace/synthetic\n'
            if (command[:2] == ('git', '-C')
                    and command[3:] == ('rev-parse', '--show-toplevel')):
                return command[2] + '\n'
            if command[:2] == ('npm', 'install'):
                self.installed = True
                return ''
            return ''
        if args[:2] == ('exec', '-it'):
            return ''
        return ''


class LauncherFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.repo = self.root / 'dotfiles-ai'
        self.repo.mkdir()
        (self.repo / 'apm.yml').write_text('targets: [opencode]\n')
        self.project = self.root / 'synthetic'
        self.project.mkdir()
        clone_root_patch = patch.object(
            oc2, 'CLONE_SOURCE_ROOT', self.root / 'oc2-state' / 'clone-sources',
        )
        clone_root_patch.start()
        self.addCleanup(clone_root_patch.stop)
        (self.project / 'main.py').write_text('print("safe")\n')
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        subprocess.run(
            ['git', '-C', str(self.project), 'config', 'user.email', 'test@example.invalid'],
            check=True,
        )
        subprocess.run(
            ['git', '-C', str(self.project), 'config', 'user.name', 'Test Fixture'],
            check=True,
        )
        subprocess.run(
            ['git', '-C', str(self.project), 'remote', 'add', 'origin',
             'https://example.invalid/source.git'],
            check=True,
        )
        subprocess.run(
            ['git', '-C', str(self.project), 'config',
             'http.https://example.invalid/.extraheader',
             'AUTHORIZATION: Basic c2VjcmV0LXBsYWNlaG9sZGVy'],
            check=True,
        )
        subprocess.run(['git', '-C', str(self.project), 'add', 'main.py'], check=True)
        subprocess.run(
            ['git', '-C', str(self.project), 'commit', '-qm', 'fixture'], check=True,
        )
        self.fake = FakeSbx()

    def _run(self) -> tuple[int, str]:
        output = io.StringIO()
        args = [
            '--repo-root', str(self.repo), '--workspace', str(self.project),
            '--sandbox', 'oc2-test',
        ]
        with patch.object(oc2, 'Runner', return_value=self.fake), \
                patch.object(oc2.shutil, 'which', return_value='/fake/sbx'), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = oc2.main(args)
        return status, output.getvalue()

    def test_clone_mode_installs_and_launches_only_pinned_v2(self) -> None:
        status, output = self._run()
        self.assertEqual(status, 0, output)
        create = next(call for call in self.fake.calls if call[0] == 'create' and '--clone' in call)
        self.assertEqual(create[:-1], ('create', '--clone', '--name', 'oc2-test', 'shell'))
        self.assertNotEqual(pathlib.Path(create[-1]), self.project)
        self.assertEqual(self.fake.clone_source_content, 'print("safe")\n')
        self.assertEqual(self.fake.clone_source_remotes, 'origin\n')
        self.assertEqual(self.fake.clone_source_log_subject, 'OC2 sanitized workspace snapshot')
        self.assertFalse(self.fake.clone_source_has_http_header)
        self.assertTrue(pathlib.Path(create[-1]).exists())
        install = next(call for call in self.fake.calls if call[:3] == (
            'exec', 'oc2-test', 'npm',
        ))
        self.assertEqual(install[-1], '@opencode/cli@2.2.5')
        self.assertIn(900, self.fake.timeouts)
        launch = next(call for call in self.fake.calls if call[:2] == ('exec', '-it'))
        self.assertEqual(launch[3], '/home/agent/workspace/synthetic')
        self.assertIn('env', launch)
        self.assertIn('-i', launch)
        self.assertEqual(launch[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertIn('opencode=v2.2.5', output)
        self.assertFalse(any('--collect' in call or '--apply' in call for call in self.fake.calls))

    def test_clone_mode_refuses_env_file_before_creating_sandbox(self) -> None:
        (self.project / '.env').write_text('TOKEN=fixture-only')
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('clone mode would expose', output)
        self.assertFalse(self.fake.created)
        self.assertFalse(any(call[0] == 'create' and '--clone' in call for call in self.fake.calls))

    def test_clone_mode_refuses_project_opencode_configuration(self) -> None:
        (self.project / 'opencode.json').write_text('{"mcp":{}}\n')
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('OpenCode project configuration', output)
        self.assertFalse(self.fake.created)

    def test_existing_sandbox_is_not_reused_or_rebuilt(self) -> None:
        self.fake.created = True
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('refusing to reuse or rebuild', output)
        self.assertFalse(any(call[0] == 'create' and '--clone' in call for call in self.fake.calls))

    def test_clone_mode_refuses_credentials_in_git_metadata_before_creation(self) -> None:
        config = self.project / '.git' / 'config'
        config.write_text(
            '[remote "origin"]\nurl = https://user:password@example.invalid/repo.git\n',
        )
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('Git metadata contains credential', output)
        self.assertFalse(self.fake.created)

    def test_clone_mode_refuses_credentials_in_remote_query_before_creation(self) -> None:
        subprocess.run(
            ['git', '-C', str(self.project), 'remote', 'set-url', 'origin',
             'https://example.invalid/source.git?access_token=fixture-token-material-123456'],
            check=True,
        )

        status, output = self._run()

        self.assertEqual(status, 1)
        self.assertIn('Git remote contains credential', output)
        self.assertFalse(self.fake.created)

    def test_clone_source_survives_ambiguous_sandbox_creation_failure(self) -> None:
        original_sbx = self.fake.sbx

        def fail_after_create(*args: str, capture: bool = False, tty: bool = False,
                              timeout: int | None = 180) -> str:
            result = original_sbx(*args, capture=capture, tty=tty, timeout=timeout)
            if args[0] == 'create' and '--clone' in args:
                raise oc2.Stop('simulated ambiguous create failure')
            return result

        with patch.object(self.fake, 'sbx', side_effect=fail_after_create):
            status, output = self._run()

        self.assertEqual(status, 1)
        self.assertIn('simulated ambiguous create failure', output)
        self.assertTrue(self.fake.created, (output, self.fake.calls))
        self.assertIsNotNone(self.fake.clone_source)
        self.assertTrue(self.fake.clone_source.exists())

    def test_clone_mode_uses_validated_snapshot_after_host_changes(self) -> None:
        validate = oc2.validate_clone_workspace

        def validate_then_mutate(snapshot: pathlib.Path) -> None:
            validate(snapshot)
            if snapshot != self.project:
                (self.project / 'main.py').write_text('print("changed after inspection")\n')

        with patch.object(oc2, 'validate_clone_workspace', side_effect=validate_then_mutate):
            status, output = self._run()

        self.assertEqual(status, 0, output)
        create = next(
            call for call in self.fake.calls if call[0] == 'create' and '--clone' in call
        )
        clone_source = pathlib.Path(create[-1])
        self.assertNotEqual(clone_source, self.project)
        self.assertTrue(clone_source.exists())
        self.assertEqual(self.fake.clone_source_content, 'print("safe")\n')
        self.assertEqual(self.fake.clone_source_remotes, 'origin\n')
        self.assertEqual(self.fake.clone_source_log_subject, 'OC2 sanitized workspace snapshot')
        self.assertFalse(self.fake.clone_source_has_http_header)
        self.assertEqual((self.project / 'main.py').read_text(),
                         'print("changed after inspection")\n')


if __name__ == '__main__':
    unittest.main()

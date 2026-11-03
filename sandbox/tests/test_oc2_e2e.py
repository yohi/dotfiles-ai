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
    def __init__(self):
        self.created = False
        self.installed = False
        self.calls: list[tuple[str, ...]] = []

    def sbx(self, *args: str, capture: bool = False, tty: bool = False) -> str:
        self.calls.append(args)
        if args == ('version',):
            return 'sbx version v0.49.2 test\n'
        if args == ('create', '--help'):
            return '  --clone  private in-container clone\n'
        if args == ('ls', '-q'):
            return 'oc2-test\n' if self.created else ''
        if args[:1] == ('create',):
            self.created = True
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
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.repo = self.root / 'dotfiles-ai'
        self.repo.mkdir()
        (self.repo / 'apm.yml').write_text('targets: [opencode]\n')
        self.project = self.root / 'synthetic'
        self.project.mkdir()
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

    def test_clone_mode_installs_and_launches_only_pinned_v2(self):
        status, output = self._run()
        self.assertEqual(status, 0, output)
        create = next(call for call in self.fake.calls if call[0] == 'create' and '--clone' in call)
        self.assertEqual(
            create,
            ('create', '--clone', '--name', 'oc2-test', 'shell', str(self.project)),
        )
        install = next(call for call in self.fake.calls if call[:3] == (
            'exec', 'oc2-test', 'npm',
        ))
        self.assertEqual(install[-1], '@opencode/cli@2.2.5')
        launch = next(call for call in self.fake.calls if call[:2] == ('exec', '-it'))
        self.assertEqual(launch[3], '/home/agent/workspace/synthetic')
        self.assertIn('env', launch)
        self.assertIn('-i', launch)
        self.assertEqual(launch[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertIn('opencode=v2.2.5', output)
        self.assertFalse(any('--collect' in call or '--apply' in call for call in self.fake.calls))

    def test_clone_mode_refuses_env_file_before_creating_sandbox(self):
        (self.project / '.env').write_text('TOKEN=fixture-only')
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('clone mode would expose', output)
        self.assertFalse(self.fake.created)
        self.assertFalse(any(call[0] == 'create' and '--clone' in call for call in self.fake.calls))

    def test_clone_mode_refuses_project_opencode_configuration(self):
        (self.project / 'opencode.json').write_text('{"mcp":{}}\n')
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('OpenCode project configuration', output)
        self.assertFalse(self.fake.created)

    def test_existing_sandbox_is_not_reused_or_rebuilt(self):
        self.fake.created = True
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('refusing to reuse or rebuild', output)
        self.assertFalse(any(call[0] == 'create' and '--clone' in call for call in self.fake.calls))


if __name__ == '__main__':
    unittest.main()

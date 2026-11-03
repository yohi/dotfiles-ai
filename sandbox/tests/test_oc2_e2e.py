"""Offline end-to-end tests of the host flow through a Fake sbx adapter."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import oc2  # noqa: E402
import oc2_assets  # noqa: E402


class FakeSbx:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.created = False
        self.fail_project_copy = False
        self.calls: list[tuple[str, ...]] = []

    def _path(self, sandbox: str, remote: str) -> pathlib.Path:
        return self.root / sandbox / remote.lstrip('/')

    def sbx(self, *args: str, capture: bool = False, tty: bool = False) -> str:
        self.calls.append(args)
        if args == ('ls', '-q'):
            return 'oc2-test\n' if self.created else ''
        if args == ('ls', '--format', 'json'):
            return json.dumps([{'name': 'oc2-test', 'agent': 'shell'}] if self.created else [])
        if args[:2] == ('inspect', 'oc2-test'):
            return json.dumps({'name': 'oc2-test', 'runtime_mounts': []})
        if args[:1] == ('create',):
            self.created = True
            return ''
        if args[0] == 'cp':
            source, destination = args[1:]
            if self.fail_project_copy and pathlib.Path(source).name == 'project':
                raise oc2.Stop('fake sbx transfer failure')
            if source.startswith('oc2-test:'):
                remote = source.split(':', 1)[1]
                origin = self._path('oc2-test', remote)
                if origin.is_dir():
                    shutil.copytree(origin, pathlib.Path(destination))
                else:
                    shutil.copy2(origin, pathlib.Path(destination))
            else:
                sandbox, remote = destination.split(':', 1)
                origin = pathlib.Path(source)
                target = self._path(sandbox, remote)
                if origin.is_dir():
                    shutil.copytree(origin, target)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(origin, target)
            return ''
        if args[:2] == ('exec', 'oc2-test'):
            command = args[2:]
            if command[:3] == ('chmod', '-R', 'u+rwX'):
                location = self._path('oc2-test', command[3])
                for current, directories, filenames in os.walk(location):
                    for name in directories:
                        item = pathlib.Path(current) / name
                        item.chmod(item.stat().st_mode | 0o700)
                    for name in filenames:
                        item = pathlib.Path(current) / name
                        item.chmod(item.stat().st_mode | 0o600)
                location.chmod(location.stat().st_mode | 0o700)
                return ''
            if command[:2] in (('mkdir', '-p'), ('chmod', '700')):
                for value in command[2:]:
                    location = self._path('oc2-test', value)
                    if command[0] == 'mkdir':
                        location.mkdir(parents=True, exist_ok=True)
                return ''
            if command[:2] == ('bash', '-c'):
                script = command[2]
                if 'echo exists' in script:
                    paths = re.findall(r'test -e ([^ ;]+)', script)
                    return 'exists\n' if paths and self._path('oc2-test', paths[0]).exists() else 'missing\n'
                candidates = re.findall(r'test -x ([^ ;]+)', script)
                if candidates and self._path('oc2-test', candidates[0]).is_file():
                    return 'opencode v2.1.4\n'
                if 'npm install' in script:
                    binary = self._path('oc2-test', oc2.PINNED[1])
                    binary.parent.mkdir(parents=True, exist_ok=True)
                    binary.write_text('fake executable')
                    return ''
                return ''
            if command[:1] == ('sha256sum',):
                file = self._path('oc2-test', command[1])
                return hashlib.sha256(file.read_bytes()).hexdigest() + '  ' + file.name + '\n'
            if command[:1] == ('python3',):
                return ''
        if args[:4] == ('exec', '-it', '-w', args[3]):
            remote = args[3]
            project = self._path(args[4], remote)
            (project / 'main.py').write_text('print("sandbox")\n')
            (project / 'created.py').write_text('created = True\n')
            (project / 'remove.py').unlink(missing_ok=True)
            return ''
        return ''


class LauncherFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.repo = self.root / 'dotfiles-ai'
        self.repo.mkdir()
        (self.repo / 'apm.yml').write_text(
            'shell: bash\nsnapshot: true\n'
            'provider:\n  api_key: OMITTED\n'
            'plugin:\n  - unreviewed-plugin\n'
            'dependencies:\n  mcp:\n    - name: host-tool\n      command: secret-tool\n'
        )
        for source in [*oc2_assets.SOURCE_TO_TARGET, oc2_assets.THEME_SOURCE]:
            target = self.repo / source
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.startswith('agent-commands/'):
                target.write_text('---\ndescription: test\n---\nbody\n')
            elif source == oc2_assets.THEME_SOURCE:
                target.write_text('{"theme":"tokyonight"}')
            else:
                target.write_text('# test fixture\n')
        v1 = self.repo / 'opencode'
        v1.mkdir(exist_ok=True)
        (v1 / 'omo.jsonc').write_text('{"model":"v1-model"}\n')
        (v1 / 'opencode.jsonc').write_text('{"plugin":["v1-plugin"]}\n')
        self.project = self.root / 'project'
        self.project.mkdir()
        (self.project / 'main.py').write_text('print("host")\n')
        (self.project / 'remove.py').write_text('remove = True\n')
        (self.project / '.env').write_text('SECRET=fixture\n')
        self.state = self.root / 'state'
        self.fake = FakeSbx(self.root / 'fake-sbx')
        self.acl_grants: list[tuple[pathlib.Path, str]] = []

    def _run(self, *flags: str) -> tuple[int, str]:
        output = io.StringIO()
        args = [
            '--repo-root', str(self.repo), '--workspace', str(self.project),
            '--state-dir', str(self.state), '--sandbox', 'oc2-test',
            '--sbx-user', 'sbx-poc', '--seed-sandbox', '', *flags,
        ]
        with patch.object(oc2, 'Runner', return_value=self.fake), \
             patch.object(oc2.shutil, 'which', return_value='/fake/sbx'), \
             patch.object(oc2, 'grant_snapshot_access', side_effect=self._grant_snapshot_access), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = oc2.main(args)
        return status, output.getvalue()

    def _grant_snapshot_access(self, path: pathlib.Path, operator: str) -> None:
        self.acl_grants.append((path, operator))

    def test_workspace_launch_collect_and_apply(self):
        v1_before = (self.repo / 'apm.yml').read_bytes()
        v1_config_before = {
            name: (self.repo / 'opencode' / name).read_bytes()
            for name in ('omo.jsonc', 'opencode.jsonc')
        }
        status, output = self._run()
        self.assertEqual(status, 0, output + repr(self.fake.calls))
        self.assertEqual(len(self.acl_grants), 1)
        self.assertEqual(self.acl_grants[0][1], 'sbx-poc')
        self.assertEqual((self.project / 'main.py').read_text(), 'print("host")\n')
        self.assertTrue((self.project / '.env').is_file())
        self.assertTrue(any(call[0] == 'cp' for call in self.fake.calls))
        launch = next(call for call in self.fake.calls if call[:2] == ('exec', '-it'))
        self.assertIn('/projects/', launch[3])
        remote_project = self.fake._path('oc2-test', launch[3])
        self.assertFalse((remote_project / '.env').exists())
        self.assertNotIn('SECRET=fixture', repr(self.fake.calls))
        bundle_remote = next(
            call[2].split(':', 1)[1] for call in self.fake.calls
            if call[0] == 'cp' and '/bundles/' in call[2]
        )
        server = json.loads(
            (self.fake._path('oc2-test', bundle_remote) / 'opencode.jsonc').read_text()
        )
        self.assertEqual(server['shell'], 'bash')
        self.assertIs(server['snapshot'], True)
        self.assertEqual(server['plugins'], [])
        self.assertEqual(server['mcp'], {})
        self.assertNotIn('OMITTED', json.dumps(server))
        self.assertNotIn('unreviewed-plugin', json.dumps(server))
        status, output = self._run('--collect')
        self.assertEqual(status, 0, output)
        self.assertIn('MODIFIED: main.py', output)
        self.assertIn('ADDED: created.py', output)
        self.assertIn('DELETED: remove.py', output)
        self.assertEqual((self.project / 'main.py').read_text(), 'print("host")\n')
        self.assertTrue((self.project / 'remove.py').exists())
        status, output = self._run('--apply')
        self.assertEqual(status, 1)
        self.assertIn('deletion approval', output)
        status, output = self._run('--apply', '--allow-deletions')
        self.assertEqual(status, 0, output)
        self.assertEqual((self.project / 'main.py').read_text(), 'print("sandbox")\n')
        self.assertEqual((self.project / 'created.py').read_text(), 'created = True\n')
        self.assertFalse((self.project / 'remove.py').exists())
        self.assertEqual((self.repo / 'apm.yml').read_bytes(), v1_before)
        self.assertEqual(
            {name: (self.repo / 'opencode' / name).read_bytes() for name in v1_config_before},
            v1_config_before,
        )

    def test_workspace_apply_refuses_host_conflict(self):
        status, output = self._run()
        self.assertEqual(status, 0, output + repr(self.fake.calls))
        status, output = self._run('--collect')
        self.assertEqual(status, 0, output)
        (self.project / 'remove.py').write_text('remove = True\n')
        (self.project / 'main.py').write_text('print("concurrent host")\n')
        status, output = self._run('--apply')
        self.assertEqual(status, 1)
        self.assertIn('conflict', output)
        self.assertEqual((self.project / 'main.py').read_text(), 'print("concurrent host")\n')

    def test_sandbox_transfer_failure_fails_closed_without_host_changes(self):
        self.fake.fail_project_copy = True
        before = (self.project / 'main.py').read_bytes()
        status, output = self._run()
        self.assertEqual(status, 1)
        self.assertIn('fake sbx transfer failure', output)
        self.assertEqual((self.project / 'main.py').read_bytes(), before)
        self.assertFalse(any(self.state.rglob('receipt.json')))


if __name__ == '__main__':
    unittest.main()

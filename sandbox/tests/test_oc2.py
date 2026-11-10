"""Offline tests for the host launcher and guest config materializer.

No sbx, sudo, network, package installation, or OpenCode binary is invoked.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


oc2 = load('oc2')
guest = load('oc2_guest')
assets = load('oc2_assets')


class FakeRunner:
    def __init__(self, rows=None, inspection=None):
        self.rows = rows or []
        self.inspection = (
            {'name': 'oc2-dev', 'runtime_mounts': []}
            if inspection is None else inspection
        )
        self.calls = []
        self.workspace_copies = []
        self.remote_files = {}

    def sbx(self, *args, **kwargs):
        self.calls.append(args)
        if args == ('ls', '-q'):
            return '\n'.join(row['name'] for row in self.rows)
        if args == ('ls', '--format', 'json'):
            return json.dumps(self.rows)
        if args == ('inspect', 'oc2-dev', '--json'):
            return json.dumps(self.inspection)
        if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
            remote_file = args[3]
            for source, destination in self.workspace_copies:
                prefix = destination.split(':', 1)[1] + '/'
                if remote_file.startswith(prefix):
                    relative = remote_file[len(prefix):]
                    data = (source / relative).read_bytes()
                    return hashlib.sha256(data).hexdigest() + '  ' + relative + '\n'
            return '0' * 64 + ' /tmp/file\n'
        if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
            return 'missing\n'
        if args[0] == 'cp' and len(args) == 3:
            self.workspace_copies.append((pathlib.Path(args[1]), args[2]))
        return ''


class HostTest(unittest.TestCase):
    def test_clone_mode_command_requires_a_workspace_path(self):
        workspace = pathlib.Path('/tmp/oc2-safe-repository')
        self.assertEqual(
            oc2.clone_create_args('oc2-safe', workspace),
            ['create', '--clone', '--name', 'oc2-safe', 'shell', str(workspace)],
        )

    def test_clone_mode_refuses_excluded_files_that_docker_would_expose(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'main.py').write_text('print("safe")\n')
            (root / '.env').write_text('TOKEN=fixture-value')
            with self.assertRaisesRegex(oc2.Stop, 'clone mode would expose'):
                oc2.validate_clone_workspace(root)

    def test_opencode_cli_install_is_pinned_to_v225(self):
        self.assertEqual(oc2.VERSION, '2.2.5')
        self.assertEqual(
            oc2.install_cli_args('oc2-safe'),
            ['exec', 'oc2-safe', 'npm', 'install', '--prefix',
             '/home/agent/.local/oc2-runtime', '--no-audit', '--no-fund',
             '--no-save', '@opencode/cli@2.2.5'],
        )

    def test_workspace_snapshot_excludes_secrets_and_symlinks(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'src').mkdir()
            (root / 'src' / 'main.py').write_text('print(1)\n')
            (root / '.env').write_text('TOKEN=not-for-sandbox')
            manifest = workspace.snapshot(root)
            self.assertEqual([entry.path for entry in manifest.files], ['src/main.py'])
            self.assertNotIn('not-for-sandbox', repr(manifest))
            (root / 'linked').symlink_to(root / 'src' / 'main.py')
            with self.assertRaises(workspace.WorkspaceError):
                workspace.snapshot(root)

    def test_workspace_snapshot_rejects_embedded_credential_material(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'settings.py').write_text(
                'api_key = "' + '0123456789abcdef' * 2 + '"\n'
            )
            with self.assertRaisesRegex(workspace.WorkspaceError, 'credential material') as error:
                workspace.snapshot(root)
            self.assertEqual(
                str(error.exception),
                'workspace file appears to contain credential material',
            )
            (root / 'settings.py').write_text('api_key = "TOP_SECRET_DO_NOT_EXPORT"\n')
            manifest = workspace.snapshot(root)
            self.assertEqual([entry.path for entry in manifest.files], ['settings.py'])

    def test_workspace_snapshot_rejects_special_files(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            os.mkfifo(root / 'pipe')
            with self.assertRaisesRegex(workspace.WorkspaceError, 'special'):
                workspace.snapshot(root)

    def test_workspace_collect_rejects_host_conflicts_and_unapproved_apply(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            source = root / 'note.txt'
            source.write_text('original')
            baseline = workspace.snapshot(root)
            sandbox = pathlib.Path(tmp) / 'guest'
            sandbox.mkdir()
            (sandbox / 'note.txt').write_text('sandbox change')
            with self.assertRaises(workspace.WorkspaceError):
                workspace.apply_changes(root, sandbox, baseline, approved=False)
            source.write_text('host concurrent change')
            with self.assertRaisesRegex(workspace.WorkspaceError, 'conflict'):
                workspace.apply_changes(root, sandbox, baseline, approved=True)

    def test_workspace_snapshot_materializes_only_manifest_files(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'source'
            root.mkdir()
            (root / 'app.py').write_text('print("safe")\n')
            (root / '.env.production').write_text('SECRET=value')
            manifest = workspace.snapshot(root)
            stage = pathlib.Path(tmp) / 'stage'
            workspace.materialize(root, stage, manifest)
            self.assertEqual(sorted(item.name for item in stage.iterdir()), ['app.py'])
            self.assertEqual((stage / 'app.py').read_text(), 'print("safe")\n')

    def test_guest_snapshot_keeps_files_private_before_operator_acl(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'source'
            root.mkdir()
            source = root / 'app.py'
            source.write_text('print("safe")\n')
            manifest = workspace.snapshot(root)
            stage = pathlib.Path(tmp) / 'stage'
            workspace.materialize(root, stage, manifest, for_guest=True)
            self.assertEqual(stat.S_IMODE((stage / 'app.py').stat().st_mode), 0o600)

    def test_workspace_transfer_grants_only_operator_read_access(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'main.py').write_text('print("safe")\n')
            manifest = workspace.snapshot(root)
            staged = pathlib.Path(tmp) / 'snapshot'
            runner = FakeRunner()
            calls = []
            with patch.object(
                oc2, 'grant_snapshot_access',
                side_effect=lambda path, user: calls.append((path, user)),
                create=True,
            ):
                oc2.transfer_workspace(runner, 'oc2-dev', staged, manifest, 'sbx-poc')
            self.assertEqual(calls, [(staged, 'sbx-poc')])

    def test_snapshot_acl_is_limited_to_named_operator(self):
        result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
            args=[], returncode=0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = pathlib.Path(tmp) / 'project'
            (snapshot / 'src').mkdir(parents=True)
            (snapshot / 'src' / 'main.py').write_text('print(1)\n')
            with patch.object(oc2.shutil, 'which', return_value='/usr/bin/setfacl'), \
                 patch.object(oc2.subprocess, 'run', return_value=result) as run:
                oc2.grant_snapshot_access(snapshot, 'sbx-poc')
            self.assertEqual(
                run.call_args_list[0].args[0],
                ['/usr/bin/setfacl', '-R', '-m', 'u:sbx-poc:r--', '--', str(snapshot)],
            )
            self.assertEqual(
                run.call_args_list[1].args[0],
                ['/usr/bin/setfacl', '-m', 'u:sbx-poc:r-x', '--',
                 str(snapshot), str(snapshot / 'src')],
            )

    def test_collection_acl_is_limited_to_private_temporary_directory(self):
        result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
            args=[], returncode=0,
        )
        with patch.object(oc2.shutil, 'which', return_value='/usr/bin/setfacl'), \
             patch.object(oc2.subprocess, 'run', return_value=result) as run:
            oc2.grant_collection_directory_access(
                pathlib.Path('/tmp/oc2-collect-x'), 'sbx-poc',
            )
        self.assertEqual(
            run.call_args.args[0],
            ['/usr/bin/setfacl', '-m', 'u:sbx-poc:rwx', '--',
             '/tmp/oc2-collect-x'],
        )

    def test_collection_staging_is_created_in_private_session_directory(self):
        workspace_ops = load('oc2_workspace')
        sessions = load('oc2_session')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            workspace = root / 'workspace'
            workspace.mkdir()
            (workspace / 'main.py').write_text('print("safe")\n')
            state_root = root / 'state'
            manifest = workspace_ops.snapshot(workspace)
            session = sessions.create(
                state_root, 'oc2-dev', oc2.ROOT + '/projects/' + 'a' * 32, manifest,
            )

            class CollectionRunner:
                def sbx(self, *args, **kwargs):
                    if args[0] == 'cp':
                        incoming = pathlib.Path(args[2])
                        incoming.mkdir()
                        (incoming / 'main.py').write_text('print("safe")\n')
                    return ''

            runner = CollectionRunner()
            temporary_directory = tempfile.TemporaryDirectory
            with patch.object(tempfile, 'TemporaryDirectory', wraps=temporary_directory) as temp_dir, \
                    patch.object(oc2, 'Runner', return_value=runner), \
                    patch.object(oc2, 'is_compatible_sandbox', return_value=True), \
                    patch.object(oc2, 'grant_collection_directory_access'), \
                    patch.object(oc2, 'grant_collected_workspace_access'), \
                    patch.object(oc2, 'run_operator'):
                result = oc2._session_action(
                    argparse.Namespace(sandbox='oc2-dev', sbx_user='sbx-poc'),
                    workspace, state_root, collect=True,
                )

        self.assertEqual(result, 0)
        self.assertEqual(temp_dir.call_args.kwargs['dir'], session.directory)

    def test_collection_read_acl_grants_host_user_access_only_to_returned_tree(self):
        with patch.object(oc2.shutil, 'which', side_effect=['/usr/bin/setfacl', '/usr/bin/find']), \
             patch.object(oc2, 'run_operator', return_value='') as run:
            oc2.grant_collected_workspace_access(
                pathlib.Path('/tmp/oc2-collect-x/incoming'),
                'sbx-poc',
                'y_ohi',
            )
        self.assertEqual(
            run.call_args_list[0].args,
            ('sbx-poc', '/usr/bin/setfacl', '-m', 'u:y_ohi:r-x', '--',
             '/tmp/oc2-collect-x/incoming'),
        )
        self.assertEqual(
            run.call_args_list[1].args,
            ('sbx-poc', '/usr/bin/find', '/tmp/oc2-collect-x/incoming',
             '-type', 'd', '-exec', '/usr/bin/setfacl', '-m', 'u:y_ohi:r-x',
             '--', '{}', '+'),
        )
        self.assertEqual(
            run.call_args_list[2].args,
            ('sbx-poc', '/usr/bin/find', '/tmp/oc2-collect-x/incoming',
             '-type', 'f', '-exec', '/usr/bin/setfacl', '-m', 'u:y_ohi:r--',
             '--', '{}', '+'),
        )

    def test_snapshot_acl_fails_closed_when_setfacl_is_missing(self):
        with patch.object(oc2.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(oc2.Stop, 'setfacl is required'):
                oc2.grant_snapshot_access(pathlib.Path('/tmp/oc2-stage/project'), 'sbx-poc')

    def test_workspace_transfer_stops_before_copy_if_private_acl_fails(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'main.py').write_text('print("safe")\n')
            manifest = workspace.snapshot(root)
            staged = pathlib.Path(tmp) / 'snapshot'
            runner = FakeRunner()
            with patch.object(oc2, 'grant_snapshot_access', side_effect=oc2.Stop('ACL denied')):
                with self.assertRaisesRegex(oc2.Stop, 'ACL denied'):
                    oc2.transfer_workspace(runner, 'oc2-dev', staged, manifest, 'sbx-poc')
            self.assertFalse(any(call[0] == 'cp' for call in runner.calls))

    def test_collection_acl_failure_stops_before_sandbox_copy(self):
        with patch.object(oc2.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(oc2.Stop, 'setfacl is required'):
                oc2.grant_collection_directory_access(
                    pathlib.Path('/tmp/oc2-collect-x'), 'sbx-poc',
                )

    def test_workspace_changes_apply_add_modify_and_require_delete_approval(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'keep.txt').write_text('old')
            (root / 'remove.txt').write_text('remove')
            baseline = workspace.snapshot(root)
            guest = pathlib.Path(tmp) / 'guest'
            workspace.materialize(root, guest, baseline)
            (guest / 'keep.txt').write_text('new')
            (guest / 'added.txt').write_text('added')
            (guest / 'remove.txt').unlink()
            with self.assertRaisesRegex(workspace.WorkspaceError, 'deletion approval'):
                workspace.apply_changes(root, guest, baseline, approved=True)
            result = workspace.apply_changes(
                root, guest, baseline, approved=True, allow_deletions=True,
            )
            self.assertEqual(result, ('added.txt', 'keep.txt', 'remove.txt'))
            self.assertEqual((root / 'keep.txt').read_text(), 'new')
            self.assertEqual((root / 'added.txt').read_text(), 'added')
            self.assertFalse((root / 'remove.txt').exists())

    def test_workspace_manifest_rejects_path_traversal(self):
        workspace = load('oc2_workspace')
        with self.assertRaisesRegex(workspace.WorkspaceError, 'manifest path'):
            workspace.decode_manifest(
                b'{"schema":"dotfiles-ai/oc2-workspace/v1","files":'
                b'[{"path":"../outside","size":0,"sha256":"' + b'0' * 64 + b'"}]}',
                pathlib.Path('/tmp/workspace'),
            )

    def test_workspace_launcher_transfers_and_launches_in_project_directory(self):
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'main.py').write_text('print("original")\n')
            manifest = workspace.snapshot(root)
            staged = pathlib.Path(tmp) / 'snapshot'
            workspace.materialize(root, staged, manifest)
            runner = FakeRunner()
            with patch.object(oc2, 'grant_snapshot_access'):
                remote = oc2.transfer_workspace(
                    runner, 'oc2-dev', staged, manifest, 'sbx-poc',
                )
            self.assertEqual(remote, oc2.ROOT + '/projects/' + remote.rsplit('/', 1)[-1])
            self.assertEqual(runner.workspace_copies[0], (staged, 'oc2-dev:' + remote))
            oc2.launch(runner, 'oc2-dev', 'a' * 64, oc2.PINNED[0], remote)
            self.assertEqual(runner.calls[-1][3], remote)

    def test_oc2_help_and_version_are_local(self):
        help_result = subprocess.run(
            [sys.executable, str(SCRIPTS / 'oc2.py'), '--help'],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(help_result.returncode, 0)
        version_result = subprocess.run(
            [sys.executable, str(SCRIPTS / 'oc2.py'), '--version'],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(version_result.returncode, 0)
        self.assertIn(oc2.VERSION, version_result.stdout)
        self.assertEqual(oc2.VERSION, '2.2.5')
        self.assertNotIn('--collect', help_result.stdout)

    def test_missing_sandbox(self):
        runner = FakeRunner()
        self.assertFalse(oc2.is_compatible_sandbox(runner, 'oc2-dev'))

    def test_mountless_sandbox_reused(self):
        # sbx v0.49.2 omits mount-related fields from ls --format json.
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}])
        self.assertTrue(oc2.is_compatible_sandbox(runner, 'oc2-dev'))
        self.assertIn(('inspect', 'oc2-dev', '--json'), runner.calls)

    def test_mounted_workspace_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell', 'workspace': '/home/user/repo'}])
        with self.assertRaisesRegex(oc2.Stop, 'workspace mount'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_missing_runtime_mounts_evidence_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev'})
        with self.assertRaisesRegex(oc2.Stop, 'mount information missing'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_runtime_mounts_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev',
                                        'runtime_mounts': [{'source': '/home/user'}]})
        with self.assertRaisesRegex(oc2.Stop, 'runtime mounts'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_inspect_name_mismatch_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'other-sandbox', 'runtime_mounts': []})
        with self.assertRaisesRegex(oc2.Stop, 'identity mismatch'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_invalid_runtime_mounts_type_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev', 'runtime_mounts': {}})
        with self.assertRaisesRegex(oc2.Stop, 'mount information missing'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_list_workspace_mount_rejected_even_if_inspect_empty(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell',
                              'workspace': '/home/user/source'}])
        with self.assertRaisesRegex(oc2.Stop, 'workspace mount'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')
        self.assertNotIn(('inspect', 'oc2-dev', '--json'), runner.calls)

    def test_wrong_agent_rejected(self):
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'opencode', 'workspace': '-'}])
        with self.assertRaisesRegex(oc2.Stop, 'not shell'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_dry_run_no_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'apm.yml').write_text('shell: bash\n')
            with patch.object(oc2, 'Runner', side_effect=AssertionError('must not call sbx')):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(oc2.main(['--repo-root', tmp, '--workspace', tmp,
                                               '--dry-run']), 0)
                self.assertIn('no Sandbox commands executed', out.getvalue())

    def test_invalid_sandbox_name_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'apm.yml').write_text('shell: bash\n')
            self.assertEqual(oc2.main(['--repo-root', tmp, '--sandbox', '../bad', '--dry-run']), 1)

    def test_launch_uses_standalone_no_host_env(self):
        runner = FakeRunner()
        oc2.launch(runner, 'oc2-dev', 'a' * 64, oc2.PINNED[0])
        command = runner.calls[-1]
        self.assertEqual(command[:3], ('exec', '-it', '-w'))
        self.assertEqual(command[3], oc2.ROOT + '/runtime/' + 'a' * 16 + '/project')
        self.assertEqual(command[4:7], ('oc2-dev', 'env', '-i'))
        self.assertEqual(command[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertIn('OPENCODE_WATCHDOG_ENABLED=false', command)
        self.assertNotIn('bash', command)
        self.assertNotIn('--mount', command)

    def test_launch_prepares_isolated_runtime_for_clone_workspace(self):
        runner = FakeRunner()
        digest = 'b' * 64
        project = '/clone/workspaces/synthetic'
        runtime = f'{oc2.ROOT}/runtime/{digest[:16]}'
        oc2.launch(runner, 'oc2-dev', digest, oc2.PINNED[0], project)
        self.assertEqual(
            runner.calls[0],
            ('exec', 'oc2-dev', 'mkdir', '-p', '-m', '700',
             runtime, *(f'{runtime}/{name}' for name in
                        ('home', 'config', 'data', 'state', 'cache', 'tmp'))),
        )
        self.assertEqual(
            runner.calls[1],
            ('exec', 'oc2-dev', 'chmod', '700', runtime,
             *(f'{runtime}/{name}' for name in
               ('home', 'config', 'data', 'state', 'cache', 'tmp'))),
        )
        self.assertEqual(runner.calls[2][3], project)

    def test_seed_cli_uses_operator_home_for_private_staging(self):
        runner = oc2.Runner('operator')
        created = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='/home/' + 'operator/.oc2-seed-12345678\n', stderr='',
        )
        with patch.object(oc2, 'is_compatible_sandbox', return_value=True), \
                patch.object(oc2, 'cli_path', return_value=oc2.PINNED[0]), \
                patch.object(oc2.subprocess, 'run', return_value=created) as run, \
                patch.object(runner, 'sbx', return_value='opencode v2.2.5\n'):
            self.assertEqual(oc2.seed_cli(runner, 'oc2-dev', 'oc2-source', pathlib.Path('/tmp')),
                             oc2.PINNED[0])

        self.assertEqual(
            run.call_args_list[0].args[0],
            ['sudo', '-i', '-u', 'operator', '--', 'sh', '-c',
             'umask 077; mktemp -d "$HOME/.oc2-seed-XXXXXXXX"'],
        )

    def test_stage_does_not_depend_on_bash_positional_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = pathlib.Path(tmp) / 'bundle'
            bundle.mkdir()
            script = pathlib.Path(tmp) / 'oc2_guest.py'
            script.write_text('# harmless guest fixture\n')
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()

            class StagingRunner:
                def __init__(self):
                    self.calls = []

                def sbx(self, *args, **kwargs):
                    self.calls.append(args)
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        # No synthetic $0/$1/$2 follows the bash code.
                        assert len(args) == 5, args
                        assert '$1' not in args[4] and '$2' not in args[4]
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        return script_sha + '  oc2_guest.py\n'
                    return ''

            runner = StagingRunner()
            oc2.stage(runner, 'oc2-dev', bundle, 'a' * 64, script)
            self.assertIn(
                ('exec', 'oc2-dev', 'mkdir', '-p', oc2.ROOT,
                 oc2.ROOT + '/bundles', oc2.ROOT + '/scripts'),
                runner.calls,
            )
            self.assertIn(
                ('exec', 'oc2-dev', 'chmod', '700', oc2.ROOT,
                 oc2.ROOT + '/bundles', oc2.ROOT + '/scripts'),
                runner.calls,
            )
            self.assertEqual(len([c for c in runner.calls if c[0] == 'cp']), 2)

    def test_stage_selected_assets_with_bounded_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bundle = root / 'bundle'
            bundle.mkdir()
            script = root / 'oc2_guest.py'
            script.write_text('# fixture\n')
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()
            asset = root / 'oc2-assets.json'
            asset.write_text('{"fixture":true}')
            asset_sha = hashlib.sha256(asset.read_bytes()).hexdigest()

            class Runner:
                def __init__(self):
                    self.calls = []

                def sbx(self, *args, **kwargs):
                    self.calls.append(args)
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        return ((asset_sha if '/assets/' in args[3] else script_sha)
                                + '  verified\n')
                    return ''

            runner = Runner()
            oc2.stage(runner, 'oc2-dev', bundle, 'a' * 64, script, asset, asset_sha)
            self.assertEqual(len([c for c in runner.calls if c[0] == 'cp']), 3)
            start = [c for c in runner.calls if c[:3] ==
                     ('exec', 'oc2-dev', 'python3')]
            self.assertEqual(len(start), 1)
            self.assertIn('--expected-assets-sha', start[0])
            self.assertIn(asset_sha, start[0])
            self.assertIn('--assets', start[0])

    def test_stage_selected_assets_sha_mismatch_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bundle = root / 'bundle'
            bundle.mkdir()
            script = root / 'oc2_guest.py'
            script.write_text('# fixture\n')
            asset = root / 'oc2-assets.json'
            asset.write_text('{}')
            expected = hashlib.sha256(asset.read_bytes()).hexdigest()
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()

            class Runner:
                def sbx(self, *args, **kwargs):
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        return (('f' * 64 if '/assets/' in args[3] else script_sha)
                                + ' verified\n')
                    return ''

            with self.assertRaisesRegex(oc2.Stop, 'asset bundle SHA mismatch'):
                oc2.stage(Runner(), 'oc2-dev', bundle, 'a' * 64, script, asset, expected)

    def test_cli_version_probe_uses_shell_parameter_for_binary_path(self):
        class VersionRunner:
            def __init__(self):
                self.calls = []

            def sbx(self, *args, **kwargs):
                self.calls.append(args)
                assert args == (
                    'exec', 'oc2-dev', 'sh', '-c',
                    'if test -x "$1"; then "$1" --version; fi',
                    'oc2-version-probe', oc2.PINNED[0],
                )
                return 'opencode v2.2.5\n'

        runner = VersionRunner()
        self.assertEqual(oc2.cli_path(runner, 'oc2-dev'), oc2.PINNED[0])
        self.assertEqual(len(runner.calls), 1)

    def test_cli_path_returns_none_when_pinned_binary_is_missing(self):
        class MissingBinaryRunner:
            def __init__(self):
                self.calls = []

            def sbx(self, *args, **kwargs):
                self.calls.append(args)
                if args[:4] == ('exec', 'oc2-dev', 'sh', '-c'):
                    return ''
                raise oc2.Stop('sbx command failed (exit 127)')

        runner = MissingBinaryRunner()
        self.assertIsNone(oc2.cli_path(runner, 'oc2-dev'))
        self.assertEqual(len(runner.calls), 1)

    def test_launch_rejects_unapproved_binary(self):
        with self.assertRaisesRegex(oc2.Stop, 'unapproved'):
            oc2.launch(FakeRunner(), 'oc2-dev', 'a' * 64, '/tmp/untrusted')

    def test_launch_rejects_invalid_digest(self):
        with self.assertRaisesRegex(oc2.Stop, 'invalid runtime digest'):
            oc2.launch(FakeRunner(), 'oc2-dev', 'not-a-digest', oc2.PINNED[0])


class GuestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name) / 'oc2'
        self.base.mkdir()
        self.orig = guest.BASE
        guest.BASE = self.base
        self.bundle = self.base / 'bundles' / 'bundle1'
        self.bundle.mkdir(parents=True)
        self.config = {'$schema': 'https://opencode.ai/config.json', 'shell': 'bash',
                       'snapshot': True, 'plugins': [], 'mcp': {}}
        self.client = {'$schema': 'https://opencode.ai/v2/cli.json', 'plugins': []}
        for name, value in [('opencode.jsonc', self.config), ('cli.json', self.client)]:
            (self.bundle / name).write_text(json.dumps(value))
        hashes = {n: hashlib.sha256((self.bundle / n).read_bytes()).hexdigest()
                  for n in ('opencode.jsonc', 'cli.json')}
        self.manifest = {'schema': 'dotfiles-ai/sandbox-export/v0', 'generator': 'v0.1',
                         'opencode_version': '2.1.4', 'plugins_exported': 0,
                         'mcp_entries_exported': 0, 'artifacts_sha256': hashes}
        (self.bundle / 'export-manifest.json').write_text(json.dumps(self.manifest))

    def tearDown(self):
        guest.BASE = self.orig
        self.tmp.cleanup()

    def test_materialize_idempotently(self):
        digest = guest.verify(self.bundle)
        d1 = guest.prepare(self.bundle, digest)
        d2 = guest.prepare(self.bundle, digest)
        self.assertEqual(d1, d2)
        self.assertTrue((d1 / 'config/opencode/cli.json').exists())
        self.assertTrue((d1 / 'project').is_dir())

    def test_manifest_tampering_stops(self):
        (self.bundle / 'opencode.jsonc').write_text('{"shell":"zsh"}')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            guest.verify(self.bundle)

    def test_extra_secret_file_stops(self):
        (self.bundle / '.env').write_text('SECRET=present')
        with self.assertRaisesRegex(ValueError, 'bundle'):
            guest.verify(self.bundle)

    def test_symlink_rejected(self):
        p = self.bundle / 'cli.json'
        p.unlink()
        p.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'non-regular'):
            guest.verify(self.bundle)

    def _assets(self):
        names = sorted(guest.ASSET_TARGETS)
        contents = {name: ('# selected text\n' if name != 'theme.json'
                           else '{"name":"tokyonight"}')
                    for name in names}
        hashes = {name: hashlib.sha256(data.encode('utf-8')).hexdigest()
                  for name, data in contents.items()}
        payload = {'schema': guest.ASSET_SCHEMA, 'files': contents, 'sha256': hashes}
        directory = self.base / 'assets'
        directory.mkdir(exist_ok=True)
        path = directory / 'assets.json'
        raw = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(raw)
        return path, hashlib.sha256(raw).hexdigest()

    def test_assets_materialize_and_reuse(self):
        path, sha = self._assets()
        data = guest.verify_assets(path, sha)
        cfg_sha = guest.verify(self.bundle)
        target = guest.prepare(self.bundle, cfg_sha, data, sha)
        self.assertNotEqual(target, guest.runtime_path(cfg_sha))
        self.assertEqual(target, guest.prepare(self.bundle, cfg_sha, data, sha))
        self.assertTrue((target / 'config/opencode/AGENTS.md').is_file())
        self.assertTrue((target / 'config/opencode/skills/config-modernizer/SKILL.md').is_file())
        server = json.loads((target / 'config/opencode/opencode.jsonc').read_text())
        self.assertEqual(len(server['instructions']), 6)
        self.assertTrue(all(s.startswith(str(target)) for s in server['instructions']))
        self.assertNotIn('default_agent', server)
        self.assertNotIn('agents', server)
        self.assertNotIn('model', server)
        self.assertFalse((target / 'metadata/agent-routes.json').exists())
        tui = json.loads((target / 'config/opencode/cli.json').read_text())
        self.assertEqual(tui['theme'], {'name': 'tokyonight'})

    def _assert_unapproved_asset_rejected(self, name):
        path, _ = self._assets()
        payload = json.loads(path.read_bytes())
        payload['files'][name] = '{"source":"third-party"}'
        payload['sha256'][name] = hashlib.sha256(
            payload['files'][name].encode('utf-8')).hexdigest()
        rewritten = (json.dumps(payload, sort_keys=True) + '\n').encode()
        path.write_bytes(rewritten)
        with self.assertRaisesRegex(ValueError, 'allowlist mismatch'):
            guest.verify_assets(path, hashlib.sha256(rewritten).hexdigest())

    def test_guest_rejects_legacy_routing_asset_even_with_valid_hashes(self):
        self._assert_unapproved_asset_rejected('metadata/agent-routes.json')

    def test_guest_rejects_imported_agent_asset_even_with_valid_hashes(self):
        self._assert_unapproved_asset_rejected('config/opencode/agents/legacy.md')

    def test_assets_tampering_rejected(self):
        path, sha = self._assets()
        path.write_bytes(path.read_bytes().replace(b'tokyonight', b'othername'))
        with self.assertRaisesRegex(ValueError, 'asset SHA mismatch'):
            guest.verify_assets(path, sha)

    def test_assets_extra_path_rejected(self):
        path, sha = self._assets()
        data = json.loads(path.read_bytes())
        data['files']['../../secret'] = 'forbidden'
        raw = json.dumps(data).encode()
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'allowlist mismatch'):
            guest.verify_assets(path, hashlib.sha256(raw).hexdigest())

    def test_assets_symlink_rejected(self):
        path, sha = self._assets()
        real = path.parent / 'real.json'
        path.rename(real)
        path.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            guest.verify_assets(path, sha)

    def test_existing_runtime_asset_tampering_rejected(self):
        path, sha = self._assets()
        data = guest.verify_assets(path, sha)
        cfg_sha = guest.verify(self.bundle)
        target = guest.prepare(self.bundle, cfg_sha, data, sha)
        (target / 'config/opencode/AGENTS.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'runtime asset mismatch'):
            guest.prepare(self.bundle, cfg_sha, data, sha)

    def test_receipt_tampering_stops(self):
        digest = guest.verify(self.bundle)
        out = guest.prepare(self.bundle, digest)
        (out / 'receipt.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            guest.prepare(self.bundle, digest)



class AssetExporterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        for source in [*assets.SOURCE_TO_TARGET, assets.THEME_SOURCE]:
            file = self.root / source
            file.parent.mkdir(parents=True, exist_ok=True)
            if source == assets.THEME_SOURCE:
                file.write_text('{"theme":"tokyonight","plugin":["DO_NOT_IMPORT"]}')
            elif source.startswith('agent-commands/'):
                file.write_text('---\ndescription: Safe skill command\nagent: old-agent\n'
                                'model: unavailable/v1-model\n---\nBody of command\n')
            else:
                file.write_text('# Reviewed content\n', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def test_export_selected_assets_with_v1_command_fields_removed(self):
        raw, digest = assets.build(self.root)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
        payload = json.loads(raw)
        self.assertEqual(set(payload['files']),
                         set(assets.SOURCE_TO_TARGET.values()) |
                         {assets.THEME_TARGET})
        self.assertNotIn('metadata/agent-routes.json', payload['files'])
        command = payload['files']['config/opencode/commands/build-skill.md']
        self.assertNotIn('agent: old-agent', command)
        self.assertNotIn('model: unavailable/', command)
        self.assertIn('description: Safe skill command', command)
        self.assertNotIn('DO_NOT_IMPORT', raw.decode('utf-8'))
        self.assertEqual(json.loads(payload['files']['theme.json']), {'name':'tokyonight'})

    def test_symlinked_source_rejected(self):
        target = self.root / 'global-rules/AGENTS.global.md'
        target.unlink()
        target.symlink_to(self.root / 'opencode/tui.jsonc')
        with self.assertRaisesRegex(assets.AssetError, 'linked'):
            assets.build(self.root)

    def test_unapproved_theme_rejected(self):
        (self.root / assets.THEME_SOURCE).write_text('{"theme":"../../bad"}')
        with self.assertRaisesRegex(assets.AssetError, 'unapproved TUI theme'):
            assets.build(self.root)



class NativeV2IndependenceTest(unittest.TestCase):
    def setUp(self):
        self.fixture = AssetExporterTest()
        self.fixture.setUp()
        self.root = self.fixture.root

    def tearDown(self):
        self.fixture.tearDown()

    def test_no_legacy_routing_source_required(self):
        self.assertFalse((self.root / 'opencode/omo.jsonc').exists())
        raw, digest = assets.build(self.root)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_legacy_source_ignored_even_if_malformed(self):
        before = assets.build(self.root)
        legacy = self.root / 'opencode/omo.jsonc'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('this is not valid json')
        self.assertEqual(before, assets.build(self.root))

    def test_legacy_source_symlink_ignored(self):
        before = assets.build(self.root)
        legacy = self.root / 'opencode/omo.jsonc'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to('/etc/passwd')
        self.assertEqual(before, assets.build(self.root))

    def test_unapproved_agent_directory_ignored(self):
        before = assets.build(self.root)
        agent = self.root / 'opencode/agents/old.md'
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text('model: unknown/unapproved\n')
        self.assertEqual(before, assets.build(self.root))

    def test_exported_manifest_has_no_agent_routes(self):
        raw, _ = assets.build(self.root)
        payload = json.loads(raw)
        self.assertFalse(any(p.startswith('metadata/') or
                             '/agents/' in p for p in payload['files']))


if __name__ == '__main__':
    unittest.main()

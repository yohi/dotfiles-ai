"""Offline tests for the host launcher and guest config materializer.

No sbx, sudo, network, package installation, or OpenCode binary is invoked.
"""
from __future__ import annotations

import argparse
import ast
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
import types
import unittest
from unittest.mock import patch

import yaml

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


oc2 = load('oc2')
oauth_bundle = load('oc2_oauth_bundle')
guest = load('oc2_guest')
assets = load('oc2_assets')
bootstrap = load('oc2_oauth_bootstrap')
oauth = load('oc2_oauth')


class FakeRunner:
    def __init__(self, rows: list[dict[str, object]] | None = None,
                 inspection: dict[str, object] | None = None) -> None:
        self.rows = rows or []
        self.inspection = (
            {'name': 'oc2-dev', 'runtime_mounts': []}
            if inspection is None else inspection
        )
        self.calls: list[tuple[str, ...]] = []
        self.workspace_copies: list[tuple[pathlib.Path, str]] = []
        self.remote_files: dict[str, bytes] = {}

    def sbx(self, *args: str, capture: bool = False, tty: bool = False,
            timeout: int | None = 180) -> str:
        self.calls.append(args)
        if args == ('ls', '-q'):
            return '\n'.join(str(row['name']) for row in self.rows)
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

class RunnerTimeoutTest(unittest.TestCase):
    def test_cli_install_uses_extended_timeout(self) -> None:
        runner = oc2.Runner('operator')
        completed = subprocess.CompletedProcess([], 0, '')
        with patch.object(oc2.subprocess, 'run', return_value=completed) as run:
            runner.sbx(*oc2.install_cli_args('oc2-dev'), timeout=900)
        self.assertEqual(run.call_args.kwargs['timeout'], 900)

    def test_tty_remains_unbounded_and_default_timeout_remains_180_seconds(self) -> None:
        runner = oc2.Runner('operator')
        results = [subprocess.CompletedProcess([], 0, ''), subprocess.CompletedProcess([], 0, '')]
        with patch.object(oc2.subprocess, 'run', side_effect=results) as run:
            runner.sbx('exec', '-it', tty=True)
            runner.sbx('version')
        self.assertIsNone(run.call_args_list[0].kwargs['timeout'])
        self.assertEqual(run.call_args_list[1].kwargs['timeout'], 180)


class CloudflareCredentialProvisioningTest(unittest.TestCase):
    class Runner:
        def __init__(self, *, sandbox_scope=None, global_scope=None, store=True):
            self.sandbox_scope = sandbox_scope
            self.global_scope = global_scope
            self.store = store
            self.calls = []

        def sbx(self, *args, capture=False, tty=False, timeout=180):
            self.calls.append((args, tty))
            if args[:2] == ('secret', 'ls'):
                scope = self.global_scope if '--global' in args else self.sandbox_scope
                entries = [] if scope is None else [{
                    'name': 'cloudflare-ai-gateway',
                    'scope': scope,
                    'secret': '(stored)',
                    'type': 'service',
                }]
                return json.dumps({'secrets': entries})
            if args[:2] == ('secret', 'set'):
                if self.store:
                    self.sandbox_scope = 'oc2-dev'
                return ''
            raise AssertionError(f'unexpected command: {args!r}')

    def test_existing_sandbox_secret_is_reused_without_mutation(self):
        runner = self.Runner(sandbox_scope='oc2-dev')

        scope = oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=False)

        self.assertEqual(scope, 'sandbox')
        self.assertEqual(len(runner.calls), 1)

    def test_missing_secret_requires_interactive_terminal(self):
        runner = self.Runner()

        with self.assertRaisesRegex(oc2.Stop, 'interactive terminal'):
            oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=False)

        self.assertEqual(len(runner.calls), 2)

    def test_interactive_secret_creation_is_verified_before_return(self):
        runner = self.Runner()

        scope = oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=True)

        self.assertEqual(scope, 'sandbox')
        self.assertEqual(runner.calls[2][0][:2], ('secret', 'set'))
        self.assertTrue(runner.calls[2][1])
        self.assertEqual(runner.calls[3][0][:2], ('secret', 'ls'))

    def test_malformed_secret_listing_fails_closed(self):
        class MalformedRunner(self.Runner):
            def sbx(self, *args, **kwargs):
                self.calls.append((args, kwargs.get('tty', False)))
                return '{"secrets":[{"name":"cloudflare-ai-gateway","scope":"oc2-dev"}]}'

        runner = MalformedRunner()
        with self.assertRaisesRegex(oc2.Stop, 'schema'):
            oc2.ensure_cloudflare_credential(runner, 'oc2-dev', interactive=True)


class HostTest(unittest.TestCase):
    def test_guest_exec_wrapper_has_one_module_assignment(self):
        source = (SCRIPTS / 'oc2.py').read_text(encoding='utf-8')
        module = ast.parse(source)
        assignments = [
            node for node in ast.walk(module)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'GUEST_EXEC_WRAPPER'
                    for target in node.targets)
        ]

        self.assertEqual(len(assignments), 1)

    def test_inline_module_source_loads_embedded_python_module(self):
        loader = oauth_bundle.inline_python_module('oc2_embedded_fixture', 'value = 42\n')
        program = loader + '\nimport oc2_embedded_fixture\nprint(oc2_embedded_fixture.value)\n'
        result = subprocess.run([sys.executable, '-c', program], capture_output=True,
                                text=True, check=False)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '42')

    def test_oauth_helper_bundle_compiles(self):
        source = oauth_bundle.oauth_helper_source(SCRIPTS)

        compile(source, '<oc2-oauth-helper>', 'exec')

    def test_launch_stops_before_tui_when_auth_identity_check_fails(self):
        class AuthFailureRunner(FakeRunner):
            def sbx(self, *args, **kwargs):
                self.calls.append(args)
                if 'oc2_oauth.py' in ' '.join(args):
                    raise oc2.Stop('authentication failed')
                return ''

        runner = AuthFailureRunner()
        request = oc2.SandboxLaunch('oc2-dev', 'a' * 64, oc2.PINNED[0],
                                    '/workspace/project', pathlib.Path('/tmp/config'))
        with self.assertRaises(oc2.Stop):
            oc2.launch(runner, request)
        self.assertFalse(any('-it' in call for call in runner.calls))

    def test_clone_mode_rejects_credentials_in_git_metadata_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            metadata = root / '.git'
            metadata.mkdir()
            (metadata / 'config').write_text(
                '[remote "origin"]\nurl = https://user:password@example.invalid/repo.git\n',
            )
            with self.assertRaisesRegex(oc2.Stop, 'Git metadata contains credential'):
                oc2.validate_clone_workspace(root)

    def test_clone_mode_command_requires_a_workspace_path(self) -> None:
        workspace = pathlib.Path('/tmp/oc2-safe-repository')
        self.assertEqual(
            oc2.clone_create_args(
                'oc2-safe', workspace, pathlib.Path('/tmp/oc2-credential-mixin'),
            ),
            ['create', '--clone', '--name', 'oc2-safe', '--kit',
             '/tmp/oc2-credential-mixin', 'shell', str(workspace)],
        )

    def test_clone_mode_refuses_excluded_files_that_docker_would_expose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'main.py').write_text('print("safe")\n')
            (root / '.env').write_text('TOKEN=fixture-value')
            with self.assertRaisesRegex(oc2.Stop, 'clone mode would expose'):
                oc2.validate_clone_workspace(root)

    def test_clone_mode_fails_closed_when_excluded_directory_cannot_be_walked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / '.git').mkdir()
            original_walk = oc2.os.walk
            calls = 0

            def fail_second_walk(path: str | os.PathLike[str], *args: object,
                                 **kwargs: object) -> object:
                nonlocal calls
                calls += 1
                if calls == 1:
                    return original_walk(path, *args, **kwargs)
                onerror = kwargs['onerror']
                assert callable(onerror)

                def walk_with_error() -> object:
                    yield str(root), ['.ssh'], []
                    onerror(PermissionError('simulated excluded-directory failure'))

                return walk_with_error()

            with patch.object(oc2.os, 'walk', side_effect=fail_second_walk):
                with self.assertRaisesRegex(oc2.Stop, 'workspace cannot be safely inspected'):
                    oc2.validate_clone_workspace(root)

    def test_clone_mode_rejects_nested_git_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / '.git').mkdir()
            nested_git = root / 'vendor' / '.git'
            nested_git.mkdir(parents=True)
            (nested_git / 'HEAD').write_text('ref: refs/heads/main\n')

            with self.assertRaisesRegex(oc2.Stop, 'nested Git metadata'):
                oc2.validate_clone_workspace(root)

    def test_clone_mode_rejects_symlinked_directory_inside_excluded_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / '.git').mkdir()
            hidden = root / '.ssh'
            hidden.mkdir()
            target = root / 'outside'
            target.mkdir()
            (hidden / 'linked').symlink_to(target, target_is_directory=True)

            with self.assertRaisesRegex(oc2.Stop, 'symlink'):
                oc2.validate_clone_workspace(root)

    def test_clone_mode_checks_compressed_git_object_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            object_content = b'https://user:password@example.invalid/repo.git'
            subprocess.run(
                ['git', '-C', str(root), 'hash-object', '-w', '--stdin'],
                input=object_content, check=True, capture_output=True,
            )

            with self.assertRaisesRegex(oc2.Stop, 'Git metadata contains credential'):
                oc2.validate_clone_workspace(root)

    def test_clone_mode_accepts_clean_repository_with_packed_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'main.py').write_text('print("safe")\n')
            subprocess.run(['git', '-C', str(root), 'add', 'main.py'], check=True)
            subprocess.run(
                ['git', '-C', str(root), '-c', 'user.name=OC2 Test',
                 '-c', 'user.email=oc2-test@example.invalid', 'commit', '-qm', 'fixture'],
                check=True,
            )
            subprocess.run(['git', '-C', str(root), 'repack', '-adq'], check=True)

            oc2.validate_clone_workspace(root)

    def test_opencode_cli_install_is_pinned_to_v225(self) -> None:
        self.assertEqual(oc2.VERSION, '2.2.5')
        self.assertEqual(
            oc2.install_cli_args('oc2-safe'),
            ['exec', 'oc2-safe', 'npm', 'install', '--prefix',
             '/home/agent/.local/oc2-runtime', '--no-audit', '--no-fund',
             '--no-save', '@opencode/cli@2.2.5'],
        )

    def test_workspace_snapshot_excludes_secrets_and_symlinks(self) -> None:
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

    def test_workspace_snapshot_rejects_embedded_credential_material(self) -> None:
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

    def test_workspace_snapshot_rejects_special_files(self) -> None:
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            os.mkfifo(root / 'pipe')
            with self.assertRaisesRegex(workspace.WorkspaceError, 'special'):
                workspace.snapshot(root)

    def test_workspace_collect_rejects_host_conflicts_and_unapproved_apply(self) -> None:
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

    def test_workspace_apply_restores_file_mode_after_replace_failure(self) -> None:
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            first = root / 'a.py'
            second = root / 'b.py'
            first.write_text('original a')
            second.write_text('original b')
            first.chmod(0o6751)
            second.chmod(0o640)
            baseline = workspace.snapshot(root)
            guest = pathlib.Path(tmp) / 'guest'
            guest.mkdir()
            (guest / 'a.py').write_text('changed a')
            (guest / 'b.py').write_text('changed b')
            real_replace = os.replace
            calls = 0

            def fail_second_replace(source: pathlib.Path, target: pathlib.Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('injected replace failure')
                real_replace(source, target)

            with patch.object(workspace.os, 'replace', side_effect=fail_second_replace):
                with self.assertRaisesRegex(OSError, 'injected replace failure'):
                    workspace.apply_changes(root, guest, baseline, approved=True)

            self.assertEqual(first.read_text(), 'original a')
            self.assertEqual(second.read_text(), 'original b')
            self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o6751)
            self.assertEqual(stat.S_IMODE(second.stat().st_mode), 0o640)

    def test_workspace_apply_restores_file_mode_after_delete_failure(self) -> None:
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            first = root / 'a.py'
            deleted = root / 'b.py'
            first.write_text('original a')
            deleted.write_text('original b')
            first.chmod(0o6751)
            deleted.chmod(0o640)
            baseline = workspace.snapshot(root)
            guest = pathlib.Path(tmp) / 'guest'
            guest.mkdir()
            (guest / 'a.py').write_text('changed a')
            real_unlink = pathlib.Path.unlink

            def fail_delete(path: pathlib.Path, *, missing_ok: bool = False) -> None:
                if path == deleted:
                    raise OSError('injected delete failure')
                real_unlink(path, missing_ok=missing_ok)

            with patch.object(pathlib.Path, 'unlink', fail_delete):
                with self.assertRaisesRegex(OSError, 'injected delete failure'):
                    workspace.apply_changes(
                        root, guest, baseline, approved=True, allow_deletions=True,
                    )

            self.assertEqual(first.read_text(), 'original a')
            self.assertEqual(deleted.read_text(), 'original b')
            self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o6751)
            self.assertEqual(stat.S_IMODE(deleted.stat().st_mode), 0o640)

    def test_workspace_snapshot_materializes_only_manifest_files(self) -> None:
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

    def test_guest_snapshot_keeps_files_private_before_operator_acl(self) -> None:
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

    def test_workspace_transfer_grants_only_operator_read_access(self) -> None:
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

    def test_snapshot_acl_is_limited_to_named_operator(self) -> None:
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

    def test_collection_acl_grants_operator_traversal_and_staging_access(self) -> None:
        result: subprocess.CompletedProcess[str] = subprocess.CompletedProcess(
            args=[], returncode=0,
        )
        with patch.object(oc2.shutil, 'which', return_value='/usr/bin/setfacl'), \
             patch.object(oc2.subprocess, 'run', return_value=result) as run:
            oc2.grant_collection_directory_access(
                pathlib.Path('/tmp/oc2-state/session/collecting'), 'sbx-poc',
            )
        self.assertEqual(
            run.call_args_list[0].args[0],
            ['/usr/bin/setfacl', '-m', 'u:sbx-poc:--x', '--',
             '/tmp/oc2-state/session', '/tmp/oc2-state'],
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            ['/usr/bin/setfacl', '-m', 'u:sbx-poc:rwx', '--',
             '/tmp/oc2-state/session/collecting'],
        )

    def test_collection_staging_is_created_in_private_session_directory(self) -> None:
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
                def sbx(self, *args: str, capture: bool = False, tty: bool = False,
                        timeout: int | None = 180) -> str:
                    if args[0] == 'cp':
                        incoming = pathlib.Path(args[2])
                        incoming.mkdir()
                        (incoming / 'main.py').write_text('print("safe")\n')
                    return ''

            runner = CollectionRunner()
            with patch.object(oc2, 'Runner', return_value=runner), \
                    patch.object(oc2, 'is_compatible_sandbox', return_value=True), \
                    patch.object(oc2, 'grant_collection_directory_access') as grant_directory, \
                    patch.object(oc2, 'grant_collected_workspace_access'), \
                    patch.object(oc2, 'run_operator'):
                result = oc2._session_action(
                    argparse.Namespace(sandbox='oc2-dev', sbx_user='sbx-poc'),
                    workspace, state_root, collect=True,
                )

        self.assertEqual(result, 0)
        staging = grant_directory.call_args.args[0]
        self.assertEqual(staging.parent, session.directory)

    def test_collection_read_acl_grants_host_user_access_only_to_returned_tree(self) -> None:
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

    def test_snapshot_acl_fails_closed_when_setfacl_is_missing(self) -> None:
        with patch.object(oc2.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(oc2.Stop, 'setfacl is required'):
                oc2.grant_snapshot_access(pathlib.Path('/tmp/oc2-stage/project'), 'sbx-poc')

    def test_workspace_transfer_stops_before_copy_if_private_acl_fails(self) -> None:
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

    def test_collection_acl_failure_stops_before_sandbox_copy(self) -> None:
        with patch.object(oc2.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(oc2.Stop, 'setfacl is required'):
                oc2.grant_collection_directory_access(
                    pathlib.Path('/tmp/oc2-collect-x'), 'sbx-poc',
                )

    def test_workspace_changes_apply_add_modify_and_require_delete_approval(self) -> None:
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

    def test_workspace_apply_rolls_back_when_a_replacement_fails(self) -> None:
        workspace = load('oc2_workspace')
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'host'
            root.mkdir()
            (root / 'a.txt').write_text('host-a')
            (root / 'b.txt').write_text('host-b')
            baseline = workspace.snapshot(root)
            guest = pathlib.Path(tmp) / 'guest'
            workspace.materialize(root, guest, baseline)
            (guest / 'a.txt').write_text('guest-a')
            (guest / 'b.txt').write_text('guest-b')
            real_replace = os.replace
            calls = 0

            def fail_second_replace(source, target):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('injected replace failure')
                real_replace(source, target)

            ops = sys.modules['oc2_workspace_ops']
            with patch.object(ops.os, 'replace', side_effect=fail_second_replace):
                with self.assertRaisesRegex(OSError, 'injected replace failure'):
                    workspace.apply_changes(root, guest, baseline, approved=True)
            self.assertEqual((root / 'a.txt').read_text(), 'host-a')
            self.assertEqual((root / 'b.txt').read_text(), 'host-b')

    def test_workspace_manifest_rejects_path_traversal(self) -> None:
        workspace = load('oc2_workspace')
        with self.assertRaisesRegex(workspace.WorkspaceError, 'manifest path'):
            workspace.decode_manifest(
                b'{"schema":"dotfiles-ai/oc2-workspace/v1","files":'
                b'[{"path":"../outside","size":0,"sha256":"' + b'0' * 64 + b'"}]}',
                pathlib.Path('/tmp/workspace'),
            )

    def test_workspace_launcher_transfers_and_launches_in_project_directory(self) -> None:
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
            oc2.launch(
                runner,
                oc2.SandboxLaunch(
                    'oc2-dev', 'a' * 64, oc2.PINNED[0], remote,
                    pathlib.Path('/tmp/opencode-v2-config.jsonc'),
                ),
            )
            self.assertEqual(runner.calls[-1][3], remote)

    def test_oc2_help_and_version_are_local(self) -> None:
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

    def test_missing_sandbox(self) -> None:
        runner = FakeRunner()
        self.assertFalse(oc2.is_compatible_sandbox(runner, 'oc2-dev'))

    def test_mountless_sandbox_reused(self) -> None:
        # sbx v0.49.2 omits mount-related fields from ls --format json.
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}])
        self.assertTrue(oc2.is_compatible_sandbox(runner, 'oc2-dev'))
        self.assertIn(('inspect', 'oc2-dev', '--json'), runner.calls)

    def test_mounted_workspace_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell', 'workspace': '/home/user/repo'}])
        with self.assertRaisesRegex(oc2.Stop, 'workspace mount'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_missing_runtime_mounts_evidence_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev'})
        with self.assertRaisesRegex(oc2.Stop, 'mount information missing'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_runtime_mounts_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev',
                                        'runtime_mounts': [{'source': '/home/user'}]})
        with self.assertRaisesRegex(oc2.Stop, 'runtime mounts'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_inspect_name_mismatch_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'other-sandbox', 'runtime_mounts': []})
        with self.assertRaisesRegex(oc2.Stop, 'identity mismatch'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_invalid_runtime_mounts_type_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell'}],
                            inspection={'name': 'oc2-dev', 'runtime_mounts': {}})
        with self.assertRaisesRegex(oc2.Stop, 'mount information missing'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_list_workspace_mount_rejected_even_if_inspect_empty(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'shell',
                              'workspace': '/home/user/source'}])
        with self.assertRaisesRegex(oc2.Stop, 'workspace mount'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')
        self.assertNotIn(('inspect', 'oc2-dev', '--json'), runner.calls)

    def test_wrong_agent_rejected(self) -> None:
        runner = FakeRunner([{'name': 'oc2-dev', 'agent': 'opencode', 'workspace': '-'}])
        with self.assertRaisesRegex(oc2.Stop, 'not shell'):
            oc2.is_compatible_sandbox(runner, 'oc2-dev')

    def test_dry_run_no_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'apm.yml').write_text('shell: bash\n')
            with patch.object(oc2, 'Runner', side_effect=AssertionError('must not call sbx')):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(oc2.main(['--repo-root', tmp, '--workspace', tmp,
                                               '--dry-run']), 0)
                self.assertIn('no Sandbox commands executed', out.getvalue())

    def test_invalid_sandbox_name_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'apm.yml').write_text('shell: bash\n')
            self.assertEqual(oc2.main(['--repo-root', tmp, '--sandbox', '../bad', '--dry-run']), 1)

    def test_launch_uses_standalone_no_host_env(self) -> None:
        runner = FakeRunner()
        runtime = f'{oc2.ROOT}/runtime/' + 'a' * 16
        oc2.launch(
            runner,
            oc2.SandboxLaunch(
                'oc2-dev', 'a' * 64, oc2.PINNED[0],
                runtime + '/project', pathlib.Path('/tmp/opencode-v2-config.jsonc'),
            ),
        )
        command = runner.calls[-1]
        self.assertEqual(command[:3], ('exec', '-it', '-w'))
        self.assertEqual(command[3], runtime + '/project')
        self.assertEqual(command[4:7], ('oc2-dev', 'python3', '-c'))
        self.assertIn(oc2.GUEST_EXEC_WRAPPER, command)
        self.assertNotIn('-i', command)
        self.assertEqual(command[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertIn('OPENCODE_WATCHDOG_ENABLED=false', command)
        self.assertIn(f'TMPDIR={runtime}/tmp', command)
        self.assertNotIn('bash', command)
        self.assertNotIn('--mount', command)
        self.assertFalse(any(argument.startswith('OPENCODE_CONFIG_DIR=') for argument in command))
        self.assertIn('OPENCODE_CONFIG_PROJECT_DISABLE=1', command)

    def test_launch_passes_gateway_token_placeholder_not_host_token(self):
        runner = FakeRunner()
        runtime = f'{oc2.ROOT}/runtime/' + 'a' * 16
        cloudflare = oc2.CloudflareGatewayRuntime('a' * 32, 'gateway-1')
        with patch.dict(oc2.os.environ, {'OC_CF_API_TOKEN': 'sensitive-poison-value'}):
            oc2.launch(
                runner,
                oc2.SandboxLaunch(
                    'oc2-dev', 'a' * 64, oc2.PINNED[0], runtime + '/project',
                    pathlib.Path('/tmp/opencode-v2-config.jsonc'), cloudflare,
                ),
            )

        command = runner.calls[-1]
        self.assertIn('OC_CF_ACCOUNT_ID=' + 'a' * 32, command)
        self.assertIn('OC_CF_GATEWAY_ID=gateway-1', command)
        self.assertIn('OC_CF_API_TOKEN=proxy-managed', command)
        self.assertNotIn('sensitive-poison-value', repr(runner.calls))

    def test_launch_without_cloudflare_selection_passes_no_cloudflare_environment(self):
        runner = FakeRunner()
        runtime = f'{oc2.ROOT}/runtime/' + 'a' * 16
        oc2.launch(
            runner,
            oc2.SandboxLaunch(
                'oc2-dev', 'a' * 64, oc2.PINNED[0], runtime + '/project',
                pathlib.Path('/tmp/opencode-v2-config.jsonc'),
            ),
        )

        command = runner.calls[-1]
        self.assertFalse(any(argument.startswith('OC_CF_') for argument in command))

    def test_launch_prepares_isolated_runtime_for_clone_workspace(self) -> None:
        runner = FakeRunner()
        digest = 'b' * 64
        project = '/clone/workspaces/synthetic'
        runtime = f'{oc2.ROOT}/runtime/{digest[:16]}'
        config_file = pathlib.Path('/tmp/opencode-v2-config.jsonc')
        oc2.launch(runner, oc2.SandboxLaunch('oc2-dev', digest, oc2.PINNED[0], project, config_file))
        self.assertEqual(
            runner.calls[0],
            ('exec', 'oc2-dev',
             *oc2._runtime_directory_setup_command(oc2.ROOT, runtime)),
        )
        self.assertEqual(
            runner.calls[1],
            ('cp', str(config_file), f'oc2-dev:{runtime}/config/opencode/opencode.jsonc'),
        )
        auth, tui = runner.calls[2:4]
        self.assertEqual(tui[3], project)
        compile(auth[auth.index('-c') + 1], '<oc2-inline-helper>', 'exec')
        for variable in ('HOME=', 'XDG_DATA_HOME=', 'OPENCODE_DB=', 'XDG_CONFIG_HOME=',
                         'XDG_STATE_HOME=', 'XDG_CACHE_HOME=', 'TMPDIR='):
            self.assertEqual([arg for arg in auth if arg.startswith(variable)],
                             [arg for arg in tui if arg.startswith(variable)])
        self.assertIn(f'OPENCODE_DB={runtime}/home/.local/share/opencode/oc2.db', tui)
        self.assertFalse(any(arg.startswith('OPENCODE_CONFIG_DIR=') for arg in tui))

    def test_runtime_directory_setup_rejects_symlinked_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = pathlib.Path(tmp)
            root = parent / 'oc2'
            root.mkdir(mode=0o700)
            outside = parent / 'outside'
            outside.mkdir(mode=0o700)
            (root / 'runtime').symlink_to(outside, target_is_directory=True)
            runtime = root / 'runtime' / ('a' * 16)

            result = subprocess.run(
                oc2._runtime_directory_setup_command(str(root), str(runtime)),
                capture_output=True, text=True, check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((outside / ('a' * 16)).exists())

    def test_runtime_directory_setup_creates_private_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / 'oc2'
            runtime = root / 'runtime' / ('b' * 16)

            result = subprocess.run(
                oc2._runtime_directory_setup_command(str(root), str(runtime)),
                capture_output=True, text=True, check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            directories = (
                root, root / 'runtime', runtime, runtime / 'home',
                runtime / 'home/.local/share', runtime / 'home/.local/share/opencode',
                runtime / 'config', runtime / 'config/opencode', runtime / 'state',
                runtime / 'cache', runtime / 'tmp',
            )
            for directory in directories:
                info = directory.stat()
                self.assertEqual(info.st_uid, os.geteuid())
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o700)

    def test_runtime_directory_setup_rejects_dotdot_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = pathlib.Path(tmp)
            root = parent / 'oc2' / '..' / 'escaped'
            runtime = root / 'runtime' / ('c' * 16)

            result = subprocess.run(
                [sys.executable, '-c', oc2.RUNTIME_DIRECTORY_SETUP_SCRIPT,
                 str(root), str(root), str(root / 'runtime'), str(runtime)],
                capture_output=True, text=True, check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((parent / 'escaped').exists())

    def test_runtime_directory_setup_does_not_execute_replaceable_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = pathlib.Path(tmp)
            source = parent / 'source'
            source.mkdir(mode=0o700)
            marker = parent / 'modified-helper-ran'
            (source / 'oc2_runtime_dirs.py').write_text(
                f'from pathlib import Path; Path({str(marker)!r}).touch()\n',
            )
            root = parent / 'oc2'
            runtime = root / 'runtime' / ('d' * 16)
            with patch.object(oc2, 'HERE', source):
                command = oc2._runtime_directory_setup_command(str(root), str(runtime))
                result = subprocess.run(
                    command,
                    capture_output=True, text=True, check=False,
                )
                self.assertFalse(marker.exists())

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_seed_cli_uses_operator_home_for_private_staging(self) -> None:
        runner = oc2.Runner('operator')
        created = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout='/home/' + 'operator/.oc2-seed-12345678\n', stderr='',
        )
        with patch.object(oc2, 'is_compatible_sandbox', return_value=True), \
                patch.object(oc2, 'cli_path', return_value=oc2.PINNED[0]), \
                patch.object(oc2.subprocess, 'run', return_value=created) as run, \
                patch.object(runner, 'sbx', return_value='opencode v2.2.5\n') as sbx:
            self.assertEqual(
                oc2.seed_cli(runner, 'oc2-dev', 'oc2-source'), oc2.PINNED[0],
            )

        self.assertEqual(
            run.call_args_list[0].args[0],
            ['sudo', '-i', '-u', 'operator', '--', 'sh', '-c',
             'umask 077; mktemp -d "$HOME/.oc2-seed-XXXXXXXX"'],
        )
        copy_calls = [call.args for call in sbx.call_args_list if call.args[0] == 'cp']
        self.assertIn(
            ('exec', 'oc2-source', 'bash', '-c',
             'if test -x /home/agent/.local/opencode-v2/node_modules/.bin/opencode; '
             'then /home/agent/.local/opencode-v2/node_modules/.bin/opencode --version; fi'),
            [call.args for call in sbx.call_args_list],
        )
        self.assertEqual(
            copy_calls,
            [
                ('cp', 'oc2-source:/home/agent/.local/opencode-v2/node_modules',
                 '/home/' + 'operator/.oc2-seed-12345678/node_modules'),
                ('cp', '/home/' + 'operator/.oc2-seed-12345678/node_modules',
                 'oc2-dev:/home/agent/.local/oc2-runtime/node_modules'),
            ],
        )

    def test_stage_does_not_depend_on_bash_positional_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = pathlib.Path(tmp) / 'bundle'
            bundle.mkdir()
            script = pathlib.Path(tmp) / 'oc2_guest.py'
            script.write_text('# harmless guest fixture\n')
            script_sha = hashlib.sha256(script.read_bytes()).hexdigest()

            class StagingRunner:
                def __init__(self) -> None:
                    self.calls: list[tuple[str, ...]] = []

                def sbx(self, *args: str, capture: bool = False, tty: bool = False,
                        timeout: int | None = 180) -> str:
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

    def test_stage_selected_assets_with_bounded_paths(self) -> None:
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
                def __init__(self) -> None:
                    self.calls: list[tuple[str, ...]] = []

                def sbx(self, *args: str, capture: bool = False, tty: bool = False,
                        timeout: int | None = 180) -> str:
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

    def test_stage_selected_assets_sha_mismatch_stops(self) -> None:
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
                def sbx(self, *args: str, capture: bool = False, tty: bool = False,
                        timeout: int | None = 180) -> str:
                    if args[:4] == ('exec', 'oc2-dev', 'bash', '-c'):
                        return 'missing\n'
                    if args[:3] == ('exec', 'oc2-dev', 'sha256sum'):
                        return (('f' * 64 if '/assets/' in args[3] else script_sha)
                                + ' verified\n')
                    return ''

            with self.assertRaisesRegex(oc2.Stop, 'asset bundle SHA mismatch'):
                oc2.stage(Runner(), 'oc2-dev', bundle, 'a' * 64, script, asset, expected)

    def test_cli_version_probe_uses_shell_parameter_for_binary_path(self) -> None:
        class VersionRunner:
            def __init__(self) -> None:
                self.calls: list[tuple[str, ...]] = []

            def sbx(self, *args: str, capture: bool = False, tty: bool = False,
                    timeout: int | None = 180) -> str:
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

    def test_cli_path_returns_none_when_pinned_binary_is_missing(self) -> None:
        class MissingBinaryRunner:
            def __init__(self) -> None:
                self.calls: list[tuple[str, ...]] = []

            def sbx(self, *args: str, capture: bool = False, tty: bool = False,
                    timeout: int | None = 180) -> str:
                self.calls.append(args)
                if args[:4] == ('exec', 'oc2-dev', 'sh', '-c'):
                    return ''
                raise oc2.Stop('sbx command failed (exit 127)')

        runner = MissingBinaryRunner()
        self.assertIsNone(oc2.cli_path(runner, 'oc2-dev'))
        self.assertEqual(len(runner.calls), 1)

    def test_launch_rejects_unapproved_binary(self) -> None:
        with self.assertRaisesRegex(oc2.Stop, 'unapproved'):
            oc2.launch(
                FakeRunner(),
                oc2.SandboxLaunch(
                    'oc2-dev', 'a' * 64, '/tmp/untrusted', '/workspace/project',
                    pathlib.Path('/tmp/opencode-v2-config.jsonc'),
                ),
            )

    def test_launch_rejects_invalid_digest(self) -> None:
        with self.assertRaisesRegex(oc2.Stop, 'invalid runtime digest'):
            oc2.launch(
                FakeRunner(),
                oc2.SandboxLaunch(
                    'oc2-dev', 'not-a-digest', oc2.PINNED[0], '/workspace/project',
                    pathlib.Path('/tmp/opencode-v2-config.jsonc'),
                ),
            )

    def test_cloudflare_gateway_runtime_is_absent_when_provider_is_not_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna', 'providers': {'openai': {}},
            }))
            self.assertIsNone(oc2.cloudflare_gateway_runtime(config, None, None))

    def test_cloudflare_gateway_runtime_accepts_legacy_config_without_providers(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({'shell': 'bash', 'snapshot': True}))
            self.assertIsNone(oc2.cloudflare_gateway_runtime(config, None, None))

    def test_cloudflare_gateway_runtime_requires_valid_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna',
                'providers': {'openai': {}, 'cloudflare-ai-gateway-custom': {}},
            }))
            for account_id, gateway_id in (
                (None, 'default'),
                ('a' * 31, 'default'),
                ('g' * 32, 'default'),
                ('a' * 32, None),
                ('a' * 32, 'invalid gateway'),
            ):
                with self.subTest(account_id=account_id, gateway_id=gateway_id):
                    with self.assertRaisesRegex(oc2.Stop, 'Cloudflare runtime identifiers') as error:
                        oc2.cloudflare_gateway_runtime(config, account_id, gateway_id)
                    self.assertNotIn(str(account_id), str(error.exception))
                    self.assertNotIn(str(gateway_id), str(error.exception))

    def test_cloudflare_gateway_runtime_is_selected_with_openai_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna',
                'providers': {'openai': {}, 'cloudflare-ai-gateway-custom': {}},
            }))
            self.assertEqual(
                oc2.cloudflare_gateway_runtime(config, 'a' * 32, 'gateway-1'),
                oc2.CloudflareGatewayRuntime('a' * 32, 'gateway-1'),
            )

    def test_credential_mixin_spec_declares_proxy_bindings(self):
        spec = yaml.safe_load(oc2.credential_mixin_spec('oc2-credentials-a1b2c3'))

        self.assertTrue(oc2.credential_mixin_spec('oc2-credentials-a1b2c3').startswith(b'# syntax=docker/sandbox-kit:3\n'))
        self.assertEqual(spec['schemaVersion'], '3')
        self.assertEqual(spec['kind'], 'mixin')
        self.assertNotIn('name', spec)
        capabilities = spec['capabilities']
        credentials = [item for item in capabilities if item['type'] == 'com.docker.sandbox/credential@1']
        openai = next(item for item in credentials if item['config']['service'] == 'openai')
        self.assertEqual(openai['config']['phase'], 'runtime')
        self.assertNotIn('passthrough', openai['config'])
        self.assertEqual(
            openai['config']['oauth'],
            {
                'tokenEndpoint': {'host': 'auth.openai.com', 'path': '/oauth/token'},
                'resourceHosts': ['chatgpt.com'],
                'sentinels': {
                    'accessToken': 'oai-oat01-proxy-managed',
                    'refreshToken': 'oai-ort01-proxy-managed',
                },
                'credentialFile': {
                    'path': '~/.local/share/opencode/auth.json',
                    'structure': {
                        'openai': {
                            'type': 'oauth',
                            'access': '{{.AccessToken}}',
                            'refresh': '{{.RefreshToken}}',
                            'expires': '{{.ExpiresAt}}',
                        },
                    },
                },
            },
        )
        cloudflare = next(item for item in credentials
                          if item['config']['service'] == 'cloudflare-ai-gateway')
        self.assertTrue(cloudflare['optional'])
        self.assertEqual(cloudflare['config']['phase'], 'runtime')
        self.assertEqual(
            cloudflare['config']['apiKey'],
            {
                'name': 'OC_CF_API_TOKEN',
                'proxyManaged': True,
                'inject': [{
                    'domain': 'gateway.ai.cloudflare.com',
                    'header': 'cf-aig-authorization',
                    'format': 'Bearer %s',
                }],
            },
        )
        self.assertEqual(
            next(item for item in capabilities if item['type'] ==
                 'com.docker.sandbox/network-policy@1')['config']['runtime']['allow'],
            ['auth.openai.com', 'chatgpt.com', 'gateway.ai.cloudflare.com'],
        )
        self.assertNotIn('secret-value', str(spec))

    def test_clone_create_args_attaches_mixin(self):
        args = oc2.clone_create_args(
            'oc2-v2', pathlib.Path('/tmp/workspace'), pathlib.Path('/tmp/mixin'),
        )

        self.assertEqual(
            args,
            ['create', '--clone', '--name', 'oc2-v2', '--kit', '/tmp/mixin',
             'shell', '/tmp/workspace'],
        )

    def test_requires_external_inference_when_v2_provider_is_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({
                'model': 'openai/gpt-6-luna', 'providers': {'openai': {}},
            }))
            self.assertTrue(oc2.requires_external_inference(config))

    def test_requires_external_inference_is_false_for_legacy_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = pathlib.Path(tmp) / 'opencode.jsonc'
            config.write_text(json.dumps({'shell': 'bash', 'snapshot': True}))
            self.assertFalse(oc2.requires_external_inference(config))


class OAuthBootstrapConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = pathlib.Path(self.temp.name) / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.runtime.chmod(0o700)
        config_dir = self.runtime / 'config' / 'opencode'
        config_dir.mkdir(parents=True, mode=0o700)
        self.base_file = config_dir / 'opencode.jsonc'
        self.policies: list[dict[str, str]] = [
            {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'provider.use', 'resource': 'openai', 'effect': 'allow'},
            {'action': 'integration.connect', 'resource': '*', 'effect': 'deny'},
            {'action': 'plugin.use', 'resource': '*', 'effect': 'deny'},
            {'action': 'mcp.use', 'resource': '*', 'effect': 'deny'},
        ]
        self.config = {
            '$schema': 'https://opencode.ai/config.json',
            'model': 'openai/gpt-6-luna',
            'providers': {'openai': {'models': {'gpt-6-luna': {}}}},
            'policies': self.policies,
        }
        self.base_bytes = json.dumps(self.config, indent=2).encode() + b'\n'
        self.base_file.write_bytes(self.base_bytes)

    def test_bootstrap_adds_only_openai_connect_exception(self):
        directory = bootstrap.create(self.base_file, self.runtime)
        generated = json.loads((directory / 'opencode.jsonc').read_bytes())
        expected = [
            *self.policies[:2],
            self.policies[2],
            {'action': 'integration.connect', 'resource': 'openai', 'effect': 'allow'},
            *self.policies[3:],
        ]
        expected_config = {**self.config, 'policies': expected}

        self.assertEqual(generated, expected_config)
        self.assertEqual(self.base_file.read_bytes(), self.base_bytes)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((directory / 'opencode.jsonc').stat().st_mode), 0o600)
        self.assertTrue((directory / 'node_modules').is_dir())
        bootstrap.cleanup(directory, self.runtime)
        self.assertFalse(directory.exists())
        self.assertEqual(self.base_file.read_bytes(), self.base_bytes)

    def test_bootstrap_refuses_base_without_blanket_connect_deny(self):
        self.config['policies'] = [self.policies[0], self.policies[1]]
        self.base_file.write_text(json.dumps(self.config))

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.create(self.base_file, self.runtime)

        self.assertFalse((self.runtime / 'oauth-bootstrap').exists())

    def test_bootstrap_refuses_preexisting_allow_policy(self):
        self.policies.append(
            {'action': 'integration.connect', 'resource': 'openai', 'effect': 'allow'},
        )
        self.base_file.write_text(json.dumps(self.config))

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.create(self.base_file, self.runtime)

        self.assertFalse((self.runtime / 'oauth-bootstrap').exists())

    def test_bootstrap_refuses_existing_destination(self):
        destination = self.runtime / 'oauth-bootstrap'
        destination.mkdir(mode=0o700)
        existing = destination / 'preserve.txt'
        existing.write_text('preserve')

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.create(self.base_file, self.runtime)

        self.assertEqual(existing.read_text(), 'preserve')

    def test_bootstrap_cleanup_refuses_unexpected_symlink(self):
        directory = bootstrap.create(self.base_file, self.runtime)
        target = self.runtime / 'preserve'
        target.write_text('preserve')
        (directory / 'unexpected').symlink_to(target)

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.cleanup(directory, self.runtime)

        self.assertEqual(target.read_text(), 'preserve')
        self.assertTrue(directory.is_dir())

    def test_cleanup_refuses_unexpected_files_without_deleting_them(self):
        directory = bootstrap.create(self.base_file, self.runtime)
        unexpected = directory / 'unexpected'
        unexpected.write_text('preserve')

        with self.assertRaises(bootstrap.BootstrapConfigError):
            bootstrap.cleanup(directory, self.runtime)

        self.assertEqual(unexpected.read_text(), 'preserve')


class OAuthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / 'auth.json'
        self.runtime = self.root / 'runtime'
        self.runtime_tmp = self.runtime / 'tmp'
        self.runtime_tmp.mkdir(parents=True, mode=0o700)
        self.runtime.chmod(0o700)
        self.runtime_tmp.chmod(0o700)
        config_dir = self.runtime / 'config' / 'opencode'
        config_dir.mkdir(parents=True, mode=0o700)
        self.base_config = config_dir / 'opencode.jsonc'
        self.base_config.write_text(json.dumps({
            '$schema': 'https://opencode.ai/config.json',
            'model': 'openai/gpt-6-luna',
            'providers': {'openai': {'models': {'gpt-6-luna': {}}}},
            'policies': [
                {'action': 'provider.use', 'resource': '*', 'effect': 'deny'},
                {'action': 'provider.use', 'resource': 'openai', 'effect': 'allow'},
                {'action': 'integration.connect', 'resource': '*', 'effect': 'deny'},
                {'action': 'plugin.use', 'resource': '*', 'effect': 'deny'},
                {'action': 'mcp.use', 'resource': '*', 'effect': 'deny'},
            ],
        }))
        self.base_config_bytes = self.base_config.read_bytes()
        self.environment = patch.dict(os.environ, {
            'TMPDIR': str(self.runtime_tmp),
            'XDG_CONFIG_HOME': str(self.runtime / 'config'),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.last_envs = []
        self.db = self.runtime / 'home/.local/share/opencode/oc2.db'
        self.db.parent.mkdir(parents=True)
        self.db.touch()
        self.source.write_text(json.dumps({'openai': {
            'type': 'oauth', 'access': 'oai-oat01-proxy-managed',
            'refresh': 'oai-ort01-proxy-managed', 'expires': 123,
        }}))
        self.record = {'id': 'sbx-openai', 'integrationID': 'openai',
                       'label': 'Sandbox OpenAI', 'active': True,
                       'value': {'type': 'oauth', 'methodID': 'chatgpt-browser',
                                 'access': 'oai-oat01-proxy-managed',
                                 'refresh': 'oai-ort01-proxy-managed', 'expires': 123}}
        self.other = {'id': 'other', 'integrationID': 'other', 'active': True}
        self.last_calls = []

    def capture_stderr(self, stderr):
        return bootstrap.capture_import_stderr(self.runtime, self.db, stderr)

    def run_sync(self, before, after, fail=None):
        calls: list[tuple[str, str | bytes | None]] = []
        self.last_calls = calls
        self.last_envs = []
        exports = iter([before, after])
        export_count = 0

        def run(args, **kwargs):
            nonlocal export_count
            calls.append((args, kwargs.get('input')))
            action = tuple(args[1:3])
            self.last_envs.append((action, kwargs.get('env')))
            if action == fail:
                return subprocess.CompletedProcess(args, 1, b'', b'secret-value')
            if action == ('debug', 'paths'):
                output = str(self.db)
            elif action == ('auth', 'export'):
                export_count += 1
                if export_count == 2:
                    self.assertFalse((self.runtime / 'oauth-bootstrap').exists())
                output = json.dumps(next(exports))
            else:
                output = ''
            return subprocess.CompletedProcess(args, 0, output.encode(), b'')

        with patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                patch.object(oauth.subprocess, 'run', side_effect=run):
            oauth.synchronize('opencode', self.source, self.db)
        return calls

    def test_captures_import_stderr_only_under_runtime_tmp(self):
        legacy = self.runtime_tmp / 'oc2-oauth-import.stderr'
        legacy.write_bytes(b'previous attempt')
        with patch.object(bootstrap.secrets, 'token_hex', return_value='a' * 16):
            captured = self.capture_stderr(b'sensitive CLI error')

        self.assertEqual(captured, self.runtime_tmp / f'oc2-oauth-import-{"a" * 16}.stderr')
        self.assertEqual(captured.read_bytes(), b'sensitive CLI error')
        self.assertEqual(stat.S_IMODE(captured.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.runtime_tmp.stat().st_mode), 0o700)
        self.assertEqual(captured.stat().st_nlink, 1)
        self.assertEqual(legacy.read_bytes(), b'previous attempt')

    def test_each_import_failure_gets_a_distinct_capture_path(self):
        with patch.object(bootstrap.secrets, 'token_hex', side_effect=('a' * 16, 'b' * 16)):
            first = self.capture_stderr(b'first')
            second = self.capture_stderr(b'second')

        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), b'first')
        self.assertEqual(second.read_bytes(), b'second')

    def test_captures_empty_import_stderr_as_empty_file(self):
        captured = self.capture_stderr(b'')

        self.assertIsNotNone(captured)
        self.assertEqual(captured.stat().st_size, 0)

    def test_refuses_existing_import_stderr_without_overwrite(self):
        path = self.runtime_tmp / f'oc2-oauth-import-{"c" * 16}.stderr'
        path.write_bytes(b'previous evidence')

        with patch.object(bootstrap.secrets, 'token_hex', return_value='c' * 16):
            captured = self.capture_stderr(b'new secret')

        self.assertIsNone(captured)
        self.assertEqual(path.read_bytes(), b'previous evidence')

    def test_refuses_import_stderr_symlink_without_following_it(self):
        target = self.root / 'protected'
        target.write_bytes(b'protected')
        destination = self.runtime_tmp / f'oc2-oauth-import-{"d" * 16}.stderr'
        destination.symlink_to(target)

        with patch.object(bootstrap.secrets, 'token_hex', return_value='d' * 16):
            captured = self.capture_stderr(b'new secret')

        self.assertIsNone(captured)
        self.assertEqual(target.read_bytes(), b'protected')

    def test_capture_uses_runtime_tmp_instead_of_external_tmpdir(self):
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir(mode=0o700)
        with patch.dict(os.environ, {'TMPDIR': str(elsewhere)}):
            captured = bootstrap.capture_import_stderr(self.runtime, self.db, b'secret')

        self.assertEqual(captured.parent, self.runtime_tmp)
        self.assertEqual(captured.read_bytes(), b'secret')
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_refuses_runtime_tmp_with_broad_permissions(self):
        self.runtime_tmp.chmod(0o755)

        captured = self.capture_stderr(b'secret')

        self.assertIsNone(captured)
        self.assertFalse(list(self.runtime_tmp.glob('oc2-oauth-import-*.stderr')))

    def test_imports_sentinel_without_changing_other_records(self):
        calls = self.run_sync([self.other], [self.other, self.record])
        imports = [payload for args, payload in calls if args[1:3] == ['auth', 'import']]
        self.assertEqual(json.loads(imports[0]), [self.record])
        self.assertFalse(list(self.runtime_tmp.glob('oc2-oauth-import-*.stderr')))

    def test_reuses_matching_record_without_import(self):
        calls = self.run_sync([self.other, self.record], [])
        self.assertFalse(any(args[1:3] == ['auth', 'import'] for args, _ in calls))

    def test_only_import_uses_bootstrap_config_and_readback_reverts(self):
        self.run_sync([self.other], [self.other, self.record])

        import_envs = [env for action, env in self.last_envs if action == ('auth', 'import')]
        export_envs = [env for action, env in self.last_envs if action == ('auth', 'export')]
        self.assertEqual(len(import_envs), 1)
        self.assertEqual(len(export_envs), 2)
        self.assertEqual(
            import_envs[0]['OPENCODE_CONFIG_DIR'],
            str(self.runtime / 'oauth-bootstrap'),
        )
        self.assertNotIn('OPENCODE_CONFIG_PROJECT_DISABLE', import_envs[0])
        self.assertEqual(export_envs, [None, None])
        self.assertEqual(self.base_config.read_bytes(), self.base_config_bytes)

    def test_bootstrap_policy_error_stops_before_import(self):
        self.base_config.write_text(json.dumps({
            'policies': [{'action': 'provider.use', 'resource': '*', 'effect': 'deny'}],
        }))
        self.last_calls = []

        def run(args, **kwargs):
            self.last_calls.append(tuple(args[1:3]))
            action = tuple(args[1:3])
            if action == ('debug', 'paths'):
                return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
            if action == ('auth', 'export'):
                return subprocess.CompletedProcess(args, 0, b'[]', b'')
            return subprocess.CompletedProcess(args, 0, b'', b'')

        with patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                patch.object(oauth.subprocess, 'run', side_effect=run):
            with self.assertRaises(bootstrap.BootstrapConfigError):
                oauth.synchronize('opencode', self.source, self.db)

        self.assertNotIn(('auth', 'import'), self.last_calls)

    def test_import_failure_cleans_bootstrap_and_exports_failure_state_once(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(ValueError):
            self.run_sync([], [self.record], fail=('auth', 'import'))

        self.assertFalse((self.runtime / 'oauth-bootstrap').exists())
        exports = [call for call in self.last_calls if call[0][1:3] == ['auth', 'export']]
        imports = [call for call in self.last_calls if call[0][1:3] == ['auth', 'import']]
        self.assertEqual(len(exports), 2)
        self.assertEqual(len(imports), 1)
        self.assertIn('OC2_OAUTH IMPORT FAIL', output.getvalue())
        self.assertIn('PRE_IMPORT_OPENAI_COUNT=0', output.getvalue())
        self.assertIn('AFTER_FAILURE_OPENAI_COUNT=1', output.getvalue())
        self.assertIn('AFTER_FAILURE_ACTIVE=true', output.getvalue())
        self.assertIn('AFTER_FAILURE_SENTINELS_MATCH=true', output.getvalue())
        self.assertIn('POST_FAILURE_DB_IDENTITY_MATCH=true', output.getvalue())
        self.assertIn('OTHER_CREDENTIALS_UNCHANGED=true', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())

    def test_bootstrap_cleanup_failure_blocks_readback(self):
        calls = []
        export_count = 0

        def run(args, **kwargs):
            nonlocal export_count
            calls.append(tuple(args[1:3]))
            action = tuple(args[1:3])
            if action == ('debug', 'paths'):
                return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
            if action == ('auth', 'export'):
                export_count += 1
                return subprocess.CompletedProcess(args, 0, b'[]', b'')
            if action == ('auth', 'import'):
                config_dir = pathlib.Path(kwargs['env']['OPENCODE_CONFIG_DIR'])
                (config_dir / 'unexpected').write_text('block cleanup')
                return subprocess.CompletedProcess(args, 0, b'', b'')
            return subprocess.CompletedProcess(args, 0, b'', b'')

        output = io.StringIO()
        with contextlib.redirect_stderr(output), \
                patch.dict(os.environ, {
                    'TMPDIR': str(self.runtime_tmp),
                    'XDG_CONFIG_HOME': str(self.runtime / 'config'),
                }), \
                patch.object(oauth.subprocess, 'run', side_effect=run):
            with self.assertRaises(bootstrap.BootstrapConfigError):
                oauth.synchronize('opencode', self.source, self.db)

        self.assertEqual(export_count, 1)
        self.assertEqual(calls.count(('auth', 'import')), 1)
        self.assertIn('OC2_OAUTH BOOTSTRAP_CLEANUP FAIL', output.getvalue())
        self.assertTrue((self.runtime / 'oauth-bootstrap' / 'unexpected').is_file())

    def test_rejects_invalid_sentinel_or_expiry(self):
        for key, value in [('expires', -1), ('expires', True), ('access', 'real-token')]:
            with self.subTest(key=key, value=value):
                auth = json.loads(self.source.read_text())
                auth['openai'][key] = value
                with self.assertRaises(ValueError) as error:
                    bootstrap.record_from_auth(auth)
                self.assertNotIn('real-token', str(error.exception))

    def test_conflicting_openai_record_stops(self):
        with self.assertRaises(ValueError):
            self.run_sync([{'id': 'another', 'integrationID': 'openai'}], [])

    def test_inactive_managed_record_stops_without_import(self):
        record = dict(self.record, active=False)
        with self.assertRaises(ValueError):
            self.run_sync([record], [])

    def test_rejects_database_symlink_before_commands(self):
        self.db.unlink()
        self.db.symlink_to(self.source)
        with patch.object(oauth.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                oauth.synchronize('opencode', self.source, self.db)
            run.assert_not_called()

    def test_metadata_is_mapped_from_source(self):
        auth = json.loads(self.source.read_text())
        auth['openai'].update(accountId='account', enterpriseUrl='https://example.invalid')
        record = bootstrap.record_from_auth(auth)
        self.assertEqual(record['value']['metadata'],
                         {'accountID': 'account', 'enterpriseUrl': 'https://example.invalid'})

    def test_database_path_mismatch_stops(self):
        result = subprocess.CompletedProcess([], 0, b'/different/path\n', b'')
        with patch.object(oauth.subprocess, 'run', return_value=result):
            with self.assertRaises(ValueError):
                oauth.synchronize('opencode', self.source, self.db)

    def test_readback_mismatch_stops(self):
        with self.assertRaises(ValueError):
            self.run_sync([self.other], [self.record])

    def test_export_and_import_failure_stop(self):
        for action in [('auth', 'export'), ('auth', 'import')]:
            with self.subTest(action=action), self.assertRaises(ValueError) as error:
                self.run_sync([], [], fail=action)
            self.assertNotIn('secret-value', str(error.exception))

    def test_export_failure_reports_stage_without_secret(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(ValueError):
            self.run_sync([], [], fail=('auth', 'export'))
        self.assertIn('OC2_OAUTH EXPORT_BEFORE FAIL', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())

    def test_import_nonzero_reports_fixed_code_without_stderr(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(ValueError):
            self.run_sync([], [], fail=('auth', 'import'))
        self.assertIn('OC2_OAUTH IMPORT_NONZERO', output.getvalue())
        self.assertIn('IMPORT_EXIT_CODE=1', output.getvalue())
        self.assertIn('IMPORT_STDERR_CAPTURED=true', output.getvalue())
        self.assertIn('IMPORT_STDERR_BYTES=12', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())
        import_calls = [call for call in self.last_calls if call[0][1:3] == ['auth', 'import']]
        self.assertEqual(len(import_calls), 1)
        capture_path = next(
            line.removeprefix('IMPORT_STDERR_PATH=')
            for line in output.getvalue().splitlines()
            if line.startswith('IMPORT_STDERR_PATH=')
        )
        capture = pathlib.Path(capture_path)
        self.assertEqual(capture.parent, self.runtime_tmp)
        self.assertEqual(capture.read_bytes(), b'secret-value')

    def test_import_stderr_capture_failure_still_fails_closed(self):
        self.runtime_tmp.chmod(0o755)
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(ValueError):
            self.run_sync([], [], fail=('auth', 'import'))

        self.assertIn('OC2_OAUTH IMPORT_NONZERO', output.getvalue())
        self.assertIn('IMPORT_STDERR_CAPTURED=false', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())
        self.assertFalse(list(self.runtime_tmp.glob('oc2-oauth-import-*.stderr')))

    def test_import_classifies_exact_cli_input_error_only(self):
        message = 'Pipe auth export output into stdin or pass a file to import'
        for stderr, expected in [(message + '\n', 'IMPORT_INPUT_INVALID'),
                                 (message + ' secret-value', 'IMPORT_NONZERO')]:
            with self.subTest(expected=expected):
                output = io.StringIO()
                def run(args, **kwargs):
                    if args[1:3] == ['debug', 'paths']:
                        return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
                    if args[1:3] == ['auth', 'export']:
                        return subprocess.CompletedProcess(args, 0, b'[]', b'')
                    return subprocess.CompletedProcess(args, 1, b'', stderr.encode())
                with contextlib.redirect_stderr(output), \
                        patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                        patch.object(oauth.subprocess, 'run', side_effect=run):
                    with self.assertRaises(ValueError):
                        oauth.synchronize('opencode', self.source, self.db)
                self.assertIn('OC2_OAUTH ' + expected, output.getvalue())
                self.assertNotIn('secret-value', output.getvalue())

    def test_unrecognized_schema_and_other_errors_remain_nonzero(self):
        for stderr in ('SchemaError: secret-value', 'connection failed: secret-value'):
            with self.subTest(kind=stderr.split(':')[0]):
                output = io.StringIO()
                def run(args, **kwargs):
                    if args[1:3] == ['debug', 'paths']:
                        return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
                    if args[1:3] == ['auth', 'export']:
                        return subprocess.CompletedProcess(args, 0, b'[]', b'')
                    return subprocess.CompletedProcess(args, 1, b'', stderr.encode())
                with contextlib.redirect_stderr(output), \
                        patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                        patch.object(oauth.subprocess, 'run', side_effect=run):
                    with self.assertRaises(ValueError):
                        oauth.synchronize('opencode', self.source, self.db)
                self.assertIn('OC2_OAUTH IMPORT_NONZERO', output.getvalue())
                self.assertNotIn('secret-value', output.getvalue())

    def test_import_timeout_reports_fixed_code_without_exception_text(self):
        output = io.StringIO()
        def run(args, **kwargs):
            if args[1:3] == ['debug', 'paths']:
                return subprocess.CompletedProcess(args, 0, str(self.db).encode(), b'')
            if args[1:3] == ['auth', 'export']:
                return subprocess.CompletedProcess(args, 0, b'[]', b'')
            raise subprocess.TimeoutExpired('secret-value', 30, stderr=b'secret-value')
        with contextlib.redirect_stderr(output), \
                patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                patch.object(oauth.subprocess, 'run', side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                oauth.synchronize('opencode', self.source, self.db)
        self.assertIn('OC2_OAUTH IMPORT_TIMEOUT', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())

    def test_failure_stages_are_distinct_and_sanitized(self):
        cases = [
            ('SENTINEL_VALIDATE', 'sentinel'),
            ('DB_PATH_VERIFY', 'path'),
            ('EXPORT_BEFORE', 'before'),
            ('STATE_CLASSIFY', 'conflict'),
            ('IMPORT', 'import'),
            ('EXPORT_AFTER', 'after'),
            ('READBACK_VERIFY', 'readback'),
        ]
        for expected, failure in cases:
            with self.subTest(stage=expected):
                output = io.StringIO()
                export_count = 0
                def run(args, **kwargs):
                    nonlocal export_count
                    action = tuple(args[1:3])
                    if action == ('debug', 'paths'):
                        return subprocess.CompletedProcess(args, 0,
                            ('/wrong' if failure == 'path' else str(self.db)).encode(), b'')
                    if action == ('auth', 'export'):
                        export_count += 1
                        if (failure == 'before' and export_count == 1 or
                                failure == 'after' and export_count == 2):
                            return subprocess.CompletedProcess(args, 1, b'', b'secret-value')
                        records = ([{'id': 'other-openai', 'integrationID': 'openai'}]
                                   if failure == 'conflict' else [])
                        return subprocess.CompletedProcess(args, 0, json.dumps(records).encode(), b'')
                    if failure == 'import':
                        return subprocess.CompletedProcess(args, 1, b'', b'secret-value')
                    return subprocess.CompletedProcess(args, 0, b'', b'')
                with contextlib.redirect_stderr(output), \
                        patch.dict(os.environ, {'TMPDIR': str(self.runtime_tmp)}), \
                        patch.object(oauth.subprocess, 'run', side_effect=run):
                    if failure == 'sentinel':
                        self.source.write_text('{"openai":{"access":"secret-value"}}')
                    with self.assertRaises(ValueError):
                        oauth.synchronize('opencode', self.source, self.db)
                if failure == 'sentinel':
                    self.source.write_text(json.dumps({'openai': {
                        'type': 'oauth', 'access': 'oai-oat01-proxy-managed',
                        'refresh': 'oai-ort01-proxy-managed', 'expires': 123}}))
                self.assertIn(f'OC2_OAUTH {expected} START', output.getvalue())
                self.assertIn(f'OC2_OAUTH {expected} FAIL', output.getvalue())
                self.assertNotIn('secret-value', output.getvalue())

    def test_unknown_error_reports_fixed_stage_without_exception_text(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), patch.object(
                oauth.subprocess, 'run', side_effect=RuntimeError('secret-value')):
            with self.assertRaises(RuntimeError):
                oauth.synchronize('opencode', self.source, self.db)
        self.assertIn('OC2_OAUTH DB_PATH_VERIFY FAIL', output.getvalue())
        self.assertNotIn('secret-value', output.getvalue())


class GuestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name) / 'oc2'
        self.base.mkdir()
        self.orig = guest.__dict__['BASE']
        guest.__dict__['BASE'] = self.base
        self.bundle = self.base / 'bundles' / 'bundle1'
        self.bundle.mkdir(parents=True)
        self.config = {'$schema': 'https://opencode.ai/config.json', 'shell': 'bash',
                       'snapshot': True, 'plugins': [], 'mcp': {}}
        self.client = {'$schema': 'https://opencode.ai/v2/cli.json', 'plugins': []}
        for name, value in [('opencode.jsonc', self.config), ('cli.json', self.client)]:
            (self.bundle / name).write_text(json.dumps(value))
        hashes = {n: hashlib.sha256((self.bundle / n).read_bytes()).hexdigest()
                  for n in ('opencode.jsonc', 'cli.json')}
        self.manifest = {'schema': 'dotfiles-ai/sandbox-export/v0', 'generator': 'v0.2',
            'source': 'apm.yml', 'source_sha256': '0' * 64,
            'config_format': 'legacy-minimal',
            'opencode_version': '2.2.5', 'plugins_exported': 0,
                         'mcp_entries_exported': 0, 'artifacts_sha256': hashes}
        (self.bundle / 'export-manifest.json').write_text(json.dumps(self.manifest))

    def tearDown(self) -> None:
        guest.__dict__['BASE'] = self.orig
        self.tmp.cleanup()

    def test_v2_multi_provider_bundle_passes_guest_validation(self):
        source = self.base / 'source'
        source.mkdir()
        (source / 'apm.yml').write_text(
            'provider:\n'
            '  openai:\n'
            '    whitelist: [gpt-6-luna]\n'
            '  cloudflare-ai-gateway-custom:\n'
            "    npm: '@ai-sdk/openai-compatible'\n"
            '    name: Cloudflare AI Gateway Custom\n'
            '    options:\n'
            "      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat'\n"
            "      apiKey: ''\n"
            '      headers:\n'
            "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
            '    models:\n'
            '      custom-ollama-cloud/kimi-k2.7-code:\n'
            '        name: Kimi K2.7 Code\n'
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
            '      auth_method: docker_custom_secret\n',
            encoding='utf-8',
        )
        bundle = self.base / 'v2-bundle'
        generated = subprocess.run(
            [sys.executable, str(SCRIPTS / 'prepare_opencode_v2.py'),
             '--repo-root', str(source), '--out', str(bundle)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(generated.returncode, 0, generated.stderr)
        digest = guest.verify(bundle)
        self.assertEqual(digest, hashlib.sha256((bundle / 'export-manifest.json').read_bytes()).hexdigest())
        server = json.loads((bundle / 'opencode.jsonc').read_text())
        self.assertEqual(set(server['providers']), {'openai', 'cloudflare-ai-gateway-custom'})

    def test_materialize_idempotently(self) -> None:
        digest = guest.verify(self.bundle)
        d1 = guest.prepare(self.bundle, digest)
        d2 = guest.prepare(self.bundle, digest)
        self.assertEqual(d1, d2)
        self.assertTrue((d1 / 'config/opencode/cli.json').exists())
        self.assertTrue((d1 / 'project').is_dir())

    def test_manifest_tampering_stops(self) -> None:
        (self.bundle / 'opencode.jsonc').write_text('{"shell":"zsh"}')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            guest.verify(self.bundle)

    def test_extra_secret_file_stops(self) -> None:
        (self.bundle / '.env').write_text('SECRET=present')
        with self.assertRaisesRegex(ValueError, 'bundle'):
            guest.verify(self.bundle)

    def test_symlink_rejected(self) -> None:
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

    def test_assets_materialize_and_reuse(self) -> None:
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

    def test_guest_rejects_legacy_routing_asset_even_with_valid_hashes(self) -> None:
        self._assert_unapproved_asset_rejected('metadata/agent-routes.json')

    def test_guest_rejects_imported_agent_asset_even_with_valid_hashes(self) -> None:
        self._assert_unapproved_asset_rejected('config/opencode/agents/legacy.md')

    def test_assets_tampering_rejected(self) -> None:
        path, sha = self._assets()
        path.write_bytes(path.read_bytes().replace(b'tokyonight', b'othername'))
        with self.assertRaisesRegex(ValueError, 'asset SHA mismatch'):
            guest.verify_assets(path, sha)

    def test_assets_extra_path_rejected(self) -> None:
        path, sha = self._assets()
        data = json.loads(path.read_bytes())
        data['files']['../../secret'] = 'forbidden'
        raw = json.dumps(data).encode()
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'allowlist mismatch'):
            guest.verify_assets(path, hashlib.sha256(raw).hexdigest())

    def test_assets_symlink_rejected(self) -> None:
        path, sha = self._assets()
        real = path.parent / 'real.json'
        path.rename(real)
        path.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            guest.verify_assets(path, sha)

    def test_existing_runtime_asset_tampering_rejected(self) -> None:
        path, sha = self._assets()
        data = guest.verify_assets(path, sha)
        cfg_sha = guest.verify(self.bundle)
        target = guest.prepare(self.bundle, cfg_sha, data, sha)
        (target / 'config/opencode/AGENTS.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'runtime asset mismatch'):
            guest.prepare(self.bundle, cfg_sha, data, sha)

    def test_receipt_tampering_stops(self) -> None:
        digest = guest.verify(self.bundle)
        out = guest.prepare(self.bundle, digest)
        (out / 'receipt.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'receipt mismatch'):
            guest.prepare(self.bundle, digest)



class AssetExporterTest(unittest.TestCase):
    def setUp(self) -> None:
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

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_export_selected_assets_with_v1_command_fields_removed(self) -> None:
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

    def test_symlinked_source_rejected(self) -> None:
        target = self.root / 'global-rules/AGENTS.global.md'
        target.unlink()
        target.symlink_to(self.root / 'opencode/tui.jsonc')
        with self.assertRaisesRegex(assets.AssetError, 'linked'):
            assets.build(self.root)

    def test_unapproved_theme_rejected(self) -> None:
        (self.root / assets.THEME_SOURCE).write_text('{"theme":"../../bad"}')
        with self.assertRaisesRegex(assets.AssetError, 'unapproved TUI theme'):
            assets.build(self.root)



class NativeV2IndependenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = AssetExporterTest()
        self.fixture.setUp()
        self.root = self.fixture.root

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def test_no_legacy_routing_source_required(self) -> None:
        self.assertFalse((self.root / 'opencode/omo.jsonc').exists())
        raw, digest = assets.build(self.root)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_legacy_source_ignored_even_if_malformed(self) -> None:
        before = assets.build(self.root)
        legacy = self.root / 'opencode/omo.jsonc'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('this is not valid json')
        self.assertEqual(before, assets.build(self.root))

    def test_legacy_source_symlink_ignored(self) -> None:
        before = assets.build(self.root)
        legacy = self.root / 'opencode/omo.jsonc'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to('/etc/passwd')
        self.assertEqual(before, assets.build(self.root))

    def test_unapproved_agent_directory_ignored(self) -> None:
        before = assets.build(self.root)
        agent = self.root / 'opencode/agents/old.md'
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text('model: unknown/unapproved\n')
        self.assertEqual(before, assets.build(self.root))

    def test_exported_manifest_has_no_agent_routes(self) -> None:
        raw, _ = assets.build(self.root)
        payload = json.loads(raw)
        self.assertFalse(any(p.startswith('metadata/') or
                             '/agents/' in p for p in payload['files']))


if __name__ == '__main__':
    unittest.main()

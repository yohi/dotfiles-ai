"""Offline tests for the explicit opt-in Host Broker integration.

No network, credential, sbx, Broker, or OpenCode process is used. Capabilities
are synthetic values.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import oc2  # noqa: E402
import oc2_host_broker as hb  # noqa: E402
import oc2_host_broker_runtime as rbr  # noqa: E402

TOKEN = 'ocb_' + 'A' * 43
URL = 'https://host.docker.internal:18080/v1'
CA_DATA = b'-----BEGIN CERTIFICATE-----\nunit-test-public-ca\n-----END CERTIFICATE-----\n'
CA_SHA256 = hashlib.sha256(CA_DATA).hexdigest()
MANIFEST_SHA = 'd' * 64
GENERATOR_FP = oc2.phase4_generator_fingerprint((
    oc2.HERE / 'oc2_host_broker.py', oc2.HERE / 'oc2_host_broker_runtime.py'))


def bound_digest(chosen, manifest_sha=MANIFEST_SHA):
    return rbr.broker_runtime_identity(chosen, manifest_sha, GENERATOR_FP)




def selection(**overrides):
    values = {
        'url': URL, 'mode': 'm1', 'sandbox_label': 'oc2-dev', 'capability_fd': 3,
        'broker_ca_sha256': CA_SHA256,
    }
    values.update(overrides)
    return hb.build_selection(**values)


DIGEST = bound_digest(selection())
RUNTIME = f'{hb.GUEST_ROOT}/runtime/{DIGEST[:16]}'


class SelectionTests(unittest.TestCase):
    def test_valid_selection_is_accepted(self):
        for url in (URL, 'https://127.0.0.1:1/v1', 'https://127.0.0.1:65535/v1/'):
            self.assertTrue(selection(url=url).url.endswith('/v1'))
        m2 = selection(mode='m2', fixture_rel='fixtures/data')
        self.assertEqual(m2.fixture_rel, 'fixtures/data')
        self.assertEqual(selection().broker_ca_sha256, CA_SHA256)

    def test_invalid_urls_are_rejected(self):
        for url in (
            None, '', 'http://host.docker.internal:1/v1', 'https://example.com:1/v1',
            'https://host.docker.internal/v1', 'https://host.docker.internal:1/v2',
            'https://host.docker.internal:1/v1?x=1', 'https://host.docker.internal:1/v1#f',
            'https://u:p@host.docker.internal:1/v1', 'https://localhost:1/v1',
            'https://host.docker.internal:0/v1', 'https://host.docker.internal:1/v1/x',
            'https://host.docker.internal:1/v1 ', 'https://[::1]:1/v1',
        ):
            with self.subTest(url=url), self.assertRaises(hb.HostBrokerError):
                selection(url=url)

    def test_ca_digest_must_be_full_lowercase_sha256(self):
        for digest in ('', 'a' * 63, 'A' * 64, None):
            with self.subTest(digest=digest), self.assertRaises(hb.HostBrokerError):
                selection(broker_ca_sha256=digest)

    def test_unknown_mode_provider_model_label_and_fd_fail_closed(self):
        cases = (
            {'mode': 'm3'}, {'mode': None}, {'mode': 'M1'}, {'provider': 'openai'},
            {'model': 'gpt-5'}, {'sandbox_label': ''}, {'sandbox_label': 'a b'},
            {'capability_fd': 0}, {'capability_fd': 2}, {'capability_fd': 1024},
            {'capability_fd': True}, {'capability_fd': '3'},
            {'mode': 'm1', 'fixture_rel': 'fixtures/f'},
            {'mode': 'm2'}, {'mode': 'm2', 'fixture_rel': ''},
            {'mode': 'm2', 'fixture_rel': 'relative'},
            {'mode': 'm2', 'fixture_rel': 'fixtures/../x'},
            {'mode': 'm2', 'fixture_rel': RUNTIME + '/fixtures'},
            {'mode': 'm2', 'fixture_rel': '/fixtures'},
            {'mode': 'm2', 'fixture_rel': 'fixtures//a'},
            {'mode': 'm2', 'fixture_rel': 'fixtures/./a'},
            {'mode': 'm2', 'fixture_rel': 'fixtures\\a'},
            {'mode': 'm2', 'fixture_rel': 'fixtures/a\0b'},
            {'mode': 'm2', 'fixture_rel': 'config/opencode'},
            {'mode': 'm2', 'fixture_rel': 'fixtures/a/b/c/d'},
            {'mode': 'm2', 'fixture_rel': 5},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(hb.HostBrokerError):
                selection(**overrides)

    def test_identity_mismatch_stops(self):
        chosen = selection()
        self.assertEqual(hb.bind_identity(chosen, 'oc2-dev', DIGEST), RUNTIME)
        with self.assertRaises(hb.HostBrokerError):
            hb.bind_identity(chosen, 'other-sandbox', DIGEST)
        with self.assertRaises(hb.HostBrokerError):
            hb.bind_identity(chosen, 'oc2-dev', 'xyz')
        for bad in ('../x', '/etc', 'fixtures/../../x', None):
            forged = hb.HostBrokerSelection(URL, 'm2', 'oc2-dev', 3, CA_SHA256, bad)
            with self.subTest(bad=bad), self.assertRaises(hb.HostBrokerError):
                hb.bind_identity(forged, 'oc2-dev', DIGEST)
        with self.assertRaises(hb.HostBrokerError):
            hb.bind_identity(
                hb.HostBrokerSelection(URL, 'm1', 'oc2-dev', 3, CA_SHA256, 'fixtures'), 'oc2-dev', DIGEST)


class CapabilityTests(unittest.TestCase):
    def test_pipe_capability_is_read_once_and_redacted(self):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, (TOKEN + '\n').encode())
        os.close(write_fd)
        capability = hb.read_capability(read_fd)
        self.assertEqual(capability.reveal(), (TOKEN + '\n').encode())
        for text in (repr(capability), str(capability), f'{capability}'):
            self.assertNotIn(TOKEN, text)
        with self.assertRaises(OSError):
            os.fstat(read_fd)

    def test_non_pipe_malformed_and_oversized_are_refused(self):
        with tempfile.TemporaryFile() as handle:
            handle.write(TOKEN.encode())
            handle.flush()
            with self.assertRaises(hb.HostBrokerError):
                hb.check_capability_fd(handle.fileno())
        with self.assertRaises(hb.HostBrokerError):
            hb.check_capability_fd(999)
        for payload in (b'', b'ocb_short', b'sk-' + b'a' * 40, TOKEN.encode() + b'x',
                        b'x' * 300, b'\xff\xfe'):
            read_fd, write_fd = os.pipe()
            os.write(write_fd, payload)
            os.close(write_fd)
            with self.subTest(payload=payload[:8]), self.assertRaises(hb.HostBrokerError) as ctx:
                hb.read_capability(read_fd)
            self.assertNotIn(TOKEN, str(ctx.exception))


class ProbeBrokerTests(unittest.TestCase):
    def test_tls_wrap_failure_closes_connected_socket(self):
        class Connection:
            closed = False

            def close(self):
                self.closed = True

        class Context:
            def wrap_socket(self, connection, *, server_hostname):
                raise ssl.SSLError('handshake failed')

        connection = Connection()
        with patch.object(hb.ssl, 'create_default_context', return_value=Context()):
            with self.assertRaisesRegex(hb.HostBrokerError, 'TLS verification failed'):
                hb.probe_broker(URL, CA_DATA, connect=lambda *_args, **_kwargs: connection)
        self.assertTrue(connection.closed)


class FsRunner:
    """Fake Sandbox backed by a local temp directory; no sbx or network.

    The Guest verifier script really runs (against the temp tree), so Guest-side
    checks are exercised independently of the Host's own verification.
    """

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.user = 'tester'
        self.calls: list[tuple[str, ...]] = []
        self.fed: list[tuple[tuple[str, ...], bytes]] = []
        self.after_cp: Callable[[pathlib.Path], None] | None = None

    def local(self, guest_path):
        return self.root / str(guest_path).lstrip('/')

    def directory_status(self, name, destination):
        path = self.local(destination)
        if path.is_symlink():
            return 12
        return 10 if path.is_dir() else (0 if not path.exists() else 12)

    def destination_status(self, name, destination):
        path = self.local(destination)
        if path.is_symlink():
            return 12
        if path.is_dir():
            return 13
        return 10 if path.is_file() else 0

    def sbx_feed(self, *args, data):
        self.fed.append((args, data))

    def sbx(self, *args, capture=False, tty=False):
        self.calls.append(args)
        head = args[0]
        if head == 'version':
            return 'sbx v0.51.0'
        if args[:2] == ('create', '--help'):
            return '--kit'
        if head == 'cp':
            target = self.local(args[2].split(':', 1)[1])
            source = pathlib.Path(args[1])
            target.write_bytes(source.read_bytes())
            target.chmod(source.stat().st_mode & 0o777)
            if self.after_cp is not None:
                self.after_cp(target)
            return ''
        if head != 'exec':
            return ''
        rest = args[2:]
        if rest[0] == 'mkdir':
            for item in rest:
                if item.startswith('/'):
                    self.local(item).mkdir(parents=True, exist_ok=True)
            return ''
        if rest[0] == 'sha256sum':
            data = self.local(rest[1]).read_bytes()
            return hashlib.sha256(data).hexdigest() + '  ' + rest[1] + '\n'
        if rest[0] == 'sh':
            return '2.2.5'
        if rest[:3] == ('python3', '-I', '-c'):
            script = rbr.GUEST_VERIFY_SCRIPT.replace(
                "ROOT = '/home/agent/workspace/oc2'",
                f'ROOT = {str(self.local(hb.GUEST_ROOT))!r}', 1)
            result = subprocess.run(
                [sys.executable, '-I', '-c', script, str(self.local(rest[4])), rest[5], rest[6], rest[7]],
                capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise oc2.Stop('sbx command failed (exit 1): ' + result.stderr.strip())
            return result.stdout
        return ''


def make_request(config_file, **overrides):
    values = {
        'name': 'oc2-dev', 'digest': DIGEST, 'cli': oc2.PINNED[0],
        'workspace': '/workspace/project', 'config_file': config_file,
    }
    values.update(overrides)
    return oc2.SandboxLaunch(**values)


PROVIDER_SOURCE = (
    b'export const PROVIDER_ID = "oc-cf-aig";\nexport const MODEL_ID = "gpt-6-luna";\n'
    b'url.protocol !== "https:";\n'
)
SOURCE_FILES = {
    'bin/guest-launch.mjs': b'#!/usr/bin/env node\n// fake guest launcher\n',
    'src/guest/index.js': b'// fake plugin entry\n',
    'src/guest/provider.mjs': PROVIDER_SOURCE,
}
COMMIT = 'c' * 40


def fake_manifest(files=None):
    files = SOURCE_FILES if files is None else files
    return {
        'schema': rbr.MANIFEST_SCHEMA, 'source_repo': rbr.SOURCE_REPO,
        'source_commit': COMMIT, 'provider': hb.PROVIDER_ID, 'model': hb.MODEL_ID,
        'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
                  for name, data in files.items()},
    }


def write_source(root, files=None):
    for name, data in (SOURCE_FILES if files is None else files).items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def verified(files=None):
    return rbr.VerifiedArtifacts(
        fake_manifest(files), 'd' * 64, dict(SOURCE_FILES if files is None else files))


def runtime_config(root):
    path = root / 'opencode.jsonc'
    path.write_bytes(rbr.config_bytes(RUNTIME))
    return path


def broker_launch(prompt='say hello', ca_certificate=None, **selection_overrides):
    return oc2.HostBrokerLaunch(
        selection(**selection_overrides), hb.Capability(TOKEN), verified(),
        ca_certificate or hb.BrokerCaCertificate(CA_DATA, CA_SHA256), prompt)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_pinned_manifest_is_valid_and_hash_locked(self):
        manifest, digest = rbr.load_manifest()
        self.assertEqual(digest, rbr.MANIFEST_SHA256)
        self.assertEqual(set(manifest['files']), rbr.ALLOWED_FILES)
        with self.assertRaises(hb.HostBrokerError):
            rbr.load_manifest(expected_sha256='0' * 64)

    def test_manifest_with_extra_traversal_or_wrong_identity_is_refused(self):
        for mutate in (
            lambda m: m['files'].__setitem__('../evil.mjs', {'sha256': '0' * 64, 'size': 1}),
            lambda m: m.__setitem__('provider', 'openai'),
            lambda m: m.__setitem__('source_commit', 'main'),
            lambda m: m['files']['src/guest/index.js'].__setitem__('size', 0),
            lambda m: m.__setitem__('extra', 1),
        ):
            manifest = fake_manifest()
            mutate(manifest)
            raw = json.dumps(manifest).encode()
            path = self.tmp / 'm.json'
            path.write_bytes(raw)
            with self.subTest(), self.assertRaises(hb.HostBrokerError):
                rbr.load_manifest(path, hashlib.sha256(raw).hexdigest())

    def verify(self, source, manifest=None, head=COMMIT):
        return rbr.verify_source(
            source, manifest or fake_manifest(), 'd' * 64, git_head=lambda _p: head)

    def test_valid_source_is_read_and_only_allowlisted_files_are_returned(self):
        source = write_source(self.tmp / 'src')
        (source / 'bin' / 'host-broker.mjs').write_text('host only', encoding='utf-8')
        result = self.verify(source)
        self.assertEqual(set(result.files), rbr.ALLOWED_FILES)

    def test_http_only_provider_artifact_is_refused_even_with_matching_hashes(self):
        files = dict(SOURCE_FILES)
        files['src/guest/provider.mjs'] = (
            b'export const PROVIDER_ID = "oc-cf-aig";\n'
            b'export const MODEL_ID = "gpt-6-luna";\n'
            b'url.protocol !== "http:";\n'
        )
        source = write_source(self.tmp / 'http-provider', files)
        with self.assertRaises(hb.HostBrokerError):
            self.verify(source, fake_manifest(files))

    def test_hash_commit_size_marker_and_link_mismatches_are_refused(self):
        source = write_source(self.tmp / 'a')
        with self.assertRaises(hb.HostBrokerError):
            self.verify(source, head='e' * 40)
        (source / 'src/guest/index.js').write_bytes(b'// tampered entry\n')
        with self.assertRaises(hb.HostBrokerError):
            self.verify(source)
        missing = write_source(self.tmp / 'b')
        (missing / 'bin/guest-launch.mjs').unlink()
        with self.assertRaises(hb.HostBrokerError):
            self.verify(missing)
        files = dict(SOURCE_FILES, **{'src/guest/provider.mjs': b'// no markers\n'})
        marker = write_source(self.tmp / 'c', files)
        with self.assertRaises(hb.HostBrokerError):
            self.verify(marker, fake_manifest(files))
        linked = write_source(self.tmp / 'd')
        (linked / 'src/guest/index.js').unlink()
        (linked / 'src/guest/index.js').symlink_to(self.tmp / 'a/src/guest/index.js')
        with self.assertRaises(hb.HostBrokerError):
            self.verify(linked)
        dirlink = write_source(self.tmp / 'e')
        shutil.move(str(dirlink / 'src'), str(self.tmp / 'moved'))
        (dirlink / 'src').symlink_to(self.tmp / 'moved')
        with self.assertRaises(hb.HostBrokerError):
            self.verify(dirlink)
        with self.assertRaises(hb.HostBrokerError):
            self.verify(self.tmp / 'does-not-exist')


class BrokerConfigTests(unittest.TestCase):
    def test_config_is_fixed_credential_free_and_provider_less(self):
        config = rbr.build_broker_config(RUNTIME)
        self.assertEqual(config['providers'], {})
        self.assertEqual(config['model'], 'oc-cf-aig/gpt-6-luna')
        self.assertEqual(config['plugins'], [RUNTIME + '/broker/src/guest'])
        raw = rbr.config_bytes(RUNTIME).decode()
        for forbidden in ('ocb_', '{env:', 'apiKey', 'Authorization', 'openai', 'cloudflare',
                          'sk-', 'token', 'secret'):
            self.assertNotIn(forbidden, raw.replace('oc-cf-aig', ''))
        allowed = [p['resource'] for p in config['policies']
                   if p['effect'] == 'allow']
        self.assertEqual(allowed, ['oc-cf-aig', RUNTIME + '/broker/src/guest'])

    def test_any_deviation_from_the_contract_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'c.jsonc'
            path.write_bytes(rbr.config_bytes(RUNTIME))
            self.assertEqual(len(rbr.assert_broker_config(path, RUNTIME)), 64)
            base = rbr.build_broker_config(RUNTIME)
            for mutate in (
                lambda c: c['providers'].__setitem__('openai', {}),
                lambda c: c.__setitem__('model', 'openai/gpt-6-luna'),
                lambda c: c.__setitem__('agents', {}),
                lambda c: c['policies'].append(
                    {'action': 'provider.use', 'resource': 'openai', 'effect': 'allow'}),
                lambda c: c['plugins'].append('/tmp/evil'),
                lambda c: c['mcp'].__setitem__('x', {}),
            ):
                mutated = json.loads(json.dumps(base))
                mutate(mutated)
                path.write_text(json.dumps(mutated, indent=2) + '\n', encoding='utf-8')
                with self.subTest(), self.assertRaises(hb.HostBrokerError):
                    rbr.assert_broker_config(path, RUNTIME)
            path.unlink()
            path.symlink_to('/etc/hostname')
            with self.assertRaises(hb.HostBrokerError):
                rbr.assert_broker_config(path, RUNTIME)

    def test_runtime_identity_binds_contract_inputs(self):
        base = rbr.broker_runtime_identity(selection(), 'a' * 64, 'b' * 64)
        self.assertRegex(base, r'^[0-9a-f]{64}$')
        self.assertEqual(base, rbr.broker_runtime_identity(selection(), 'a' * 64, 'b' * 64))
        for other in (
            rbr.broker_runtime_identity(selection(mode='m2', fixture_rel='fixtures/f'),
                                        'a' * 64, 'b' * 64),
            rbr.broker_runtime_identity(selection(url='https://127.0.0.1:1/v1'), 'a' * 64, 'b' * 64),
            rbr.broker_runtime_identity(selection(broker_ca_sha256='f' * 64), 'a' * 64, 'b' * 64),
            rbr.broker_runtime_identity(selection(), 'c' * 64, 'b' * 64),
            rbr.broker_runtime_identity(selection(), 'a' * 64, 'c' * 64),
        ):
            self.assertNotEqual(base, other)


class M2IdentityChainTests(unittest.TestCase):
    def test_m2_success_chain_places_fixture_under_the_bound_runtime(self):
        chosen = selection(mode='m2', fixture_rel='fixtures/data')
        digest = bound_digest(chosen)
        runtime = hb.bind_identity(chosen, 'oc2-dev', digest)
        self.assertEqual(runtime, f'{hb.GUEST_ROOT}/runtime/{digest[:16]}')
        argv = rbr.build_guest_exec_args(chosen, oc2.PINNED[0], runtime, 'hello')
        self.assertIn('--mode=m2', argv)
        self.assertIn(f'--fixture-root={runtime}/fixtures/data', argv)
        self.assertEqual(sum(part.startswith('--fixture-root=') for part in argv), 1)
        self.assertFalse(any('ocb_' in part or part.startswith('--capability') for part in argv))
        # The fixture identifier is bound into the Runtime Identity.
        other = selection(mode='m2', fixture_rel='fixtures/other')
        self.assertNotEqual(digest, bound_digest(other))

    def test_m2_forged_selection_is_refused_when_building_guest_args(self):
        for bad in ('../x', '/etc/passwd', 'fixtures/../x', 'config'):
            forged = hb.HostBrokerSelection(URL, 'm2', 'oc2-dev', 3, CA_SHA256, bad)
            with self.subTest(bad=bad), self.assertRaises(hb.HostBrokerError):
                rbr.build_guest_exec_args(forged, oc2.PINNED[0], RUNTIME, 'hi')

    def test_m2_launch_places_artifacts_and_passes_only_the_derived_fixture_path(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        chosen = selection(mode='m2', fixture_rel='fixtures/data')
        digest = bound_digest(chosen)
        runtime = hb.bind_identity(chosen, 'oc2-dev', digest)
        runner = FsRunner(tmp / 'guest')
        runner.root.mkdir()
        config = tmp / 'opencode.jsonc'
        config.write_bytes(rbr.config_bytes(runtime))
        broker = oc2.HostBrokerLaunch(
            chosen, hb.Capability(TOKEN), verified(), hb.BrokerCaCertificate(CA_DATA, CA_SHA256), 'hi')
        with patch.dict(os.environ, {}, clear=True):
            oc2.launch(runner, make_request(config, digest=digest), broker)
        args, data = runner.fed[0]
        self.assertIn(f'--fixture-root={runtime}/fixtures/data', args)
        self.assertEqual(data, (TOKEN + '\n').encode())
        self.assertNotIn(TOKEN, repr(args) + repr(runner.calls))

    def test_runtime_identity_and_label_mismatches_stop_and_bad_capability_cannot_be_built(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        chosen = selection(mode='m2', fixture_rel='fixtures/data')
        digest = bound_digest(chosen)
        runtime = hb.bind_identity(chosen, 'oc2-dev', digest)
        config = tmp / 'opencode.jsonc'
        config.write_bytes(rbr.config_bytes(runtime))
        broker = oc2.HostBrokerLaunch(
            chosen, hb.Capability(TOKEN), verified(), hb.BrokerCaCertificate(CA_DATA, CA_SHA256), 'hi')
        for request in (make_request(config, digest=bound_digest(selection())),
                        make_request(config, digest='f' * 64),
                        make_request(config, digest=digest, name='another-sb')):
            runner = FsRunner(tmp / 'guest')
            runner.root.mkdir(exist_ok=True)
            with self.subTest(digest=request.digest[:6], name=request.name), \
                    patch.dict(os.environ, {}, clear=True), self.assertRaises(oc2.Stop):
                oc2.launch(runner, request, broker)
            self.assertEqual(runner.fed, [])
        for bad in ('ocb_short', '', 'sk-' + 'a' * 40):
            with self.assertRaises(hb.HostBrokerError):
                hb.Capability(bad)


class TtyAndArgvTests(unittest.TestCase):
    def test_tty_and_missing_prompt_fail_closed(self):
        args = (selection(), oc2.PINNED[0], RUNTIME, 'hello')
        with self.assertRaises(hb.HostBrokerError) as ctx:
            rbr.build_guest_exec_args(*args, tty=True)
        self.assertIn('TTY', str(ctx.exception))
        for prompt in (None, '', '   ', 'x' * 5000, 'use ' + TOKEN, 'a\0b', 'sk-abcdefgh12345'):
            with self.subTest(prompt=str(prompt)[:10]), self.assertRaises(hb.HostBrokerError):
                rbr.build_guest_exec_args(selection(), oc2.PINNED[0], RUNTIME, prompt)

    def test_guest_argv_is_fixed_non_interactive_and_secret_free(self):
        argv = rbr.build_guest_exec_args(selection(), oc2.PINNED[0], RUNTIME, 'hello')
        self.assertEqual(argv, (
            'node', RUNTIME + '/broker/bin/guest-launch.mjs', '--mode=m1',
            '--broker-url=' + URL, '--opencode=' + oc2.PINNED[0],
            '--', 'run', '--standalone', 'hello',
        ))
        m2 = rbr.build_guest_exec_args(
            selection(mode='m2', fixture_rel='fixtures/fx'), oc2.PINNED[0], RUNTIME, 'hi')
        self.assertIn('--mode=m2', m2)
        self.assertIn('--fixture-root=' + RUNTIME + '/fixtures/fx', m2)
        for part in (*argv, *m2):
            self.assertNotIn('ocb_', part)
            self.assertFalse(part.startswith('--capability'))
        with self.assertRaises(hb.HostBrokerError):
            rbr.build_guest_exec_args(selection(), 'relative/opencode', RUNTIME, 'hi')


class PlacementAndLaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.runner = FsRunner(self.tmp / 'guest')
        self.runner.root.mkdir()
        self.config = runtime_config(self.tmp)
        self.request = make_request(self.config)

    def launch(self, broker=None):
        with patch.dict(os.environ, {}, clear=True):
            oc2.launch(self.runner, self.request, broker or broker_launch())

    def test_verified_artifacts_are_placed_and_verified_independently(self):
        self.launch()
        placed = self.runner.local(RUNTIME + '/broker')
        self.assertEqual(
            {str(p.relative_to(placed)) for p in placed.rglob('*') if p.is_file()},
            set(rbr.ALLOWED_FILES) | {'ca/host-broker-ca.pem'})
        for name, data in SOURCE_FILES.items():
            self.assertEqual((placed / name).read_bytes(), data)
        self.assertEqual((placed / 'ca/host-broker-ca.pem').read_bytes(), CA_DATA)
        self.assertEqual(
            self.runner.local(RUNTIME + '/config/opencode/opencode.jsonc').read_bytes(),
            rbr.config_bytes(RUNTIME))
        self.assertEqual(len(self.runner.fed), 1)
        args, data = self.runner.fed[0]
        self.assertEqual(data, (TOKEN + '\n').encode())
        self.assertIn('NODE_EXTRA_CA_CERTS=' + RUNTIME + '/broker/ca/host-broker-ca.pem', args)
        self.assertIn(RUNTIME + '/broker/bin/guest-launch.mjs', args)
        self.assertEqual(args[:2], ('exec', '-i'))
        for flag in ('-t', '-it', '--tty'):
            self.assertNotIn(flag, args)

    def test_capability_and_host_secrets_never_reach_sandbox_commands(self):
        hostile = {
            'SSH_AUTH_SOCK': '/tmp/ssh-agent-secret', 'GH_TOKEN': 'gho_hostsecretvalue',
            'CF_AIG_TOKEN': 'cf-host-secret', 'OPENAI_API_KEY': 'sk-hostsecretvalue12',
            hb.CAPABILITY_ENV: TOKEN,
        }
        with patch.dict(os.environ, hostile, clear=True):
            oc2.launch(self.runner, self.request, broker_launch())
        blob = repr(self.runner.calls) + repr([args for args, _ in self.runner.fed])
        for value in (*hostile.values(), TOKEN):
            self.assertNotIn(value, blob)
        for name in ('SSH_AUTH_SOCK', 'GH_TOKEN', 'CF_AIG_TOKEN', 'OPENAI_API_KEY'):
            self.assertNotIn(name, blob)
        self.assertNotIn('oc2_oauth.py', blob)
        guest_files = ''.join(
            p.read_text(errors='replace') for p in self.runner.root.rglob('*') if p.is_file())
        self.assertNotIn(TOKEN, guest_files)

    def test_existing_identical_files_are_reused_and_mismatches_are_not_overwritten(self):
        base = self.runner.local(RUNTIME + '/broker')
        (base / 'bin').mkdir(parents=True)
        (base / 'bin/guest-launch.mjs').write_bytes(SOURCE_FILES['bin/guest-launch.mjs'])
        self.launch()
        cps = [c for c in self.runner.calls if c[0] == 'cp' and 'guest-launch' in c[1] + c[2]]
        self.assertEqual(cps, [])
        self.runner.fed.clear()
        (base / 'src/guest/index.js').write_bytes(b'// someone else\n')
        with self.assertRaises(oc2.Stop):
            self.launch()
        self.assertEqual(self.runner.fed, [])
        self.assertEqual((base / 'src/guest/index.js').read_bytes(), b'// someone else\n')

    def test_symlink_and_directory_destinations_are_refused(self):
        base = self.runner.local(RUNTIME + '/broker')
        (base / 'bin').mkdir(parents=True)
        (base / 'bin/guest-launch.mjs').symlink_to('/etc/hostname')
        with self.assertRaises(oc2.Stop):
            self.launch()
        self.assertEqual(self.runner.fed, [])
        (base / 'bin/guest-launch.mjs').unlink()
        (base / 'bin/guest-launch.mjs').mkdir()
        with self.assertRaises(oc2.Stop):
            self.launch()
        self.assertEqual(self.runner.fed, [])

    def test_symlinked_artifact_directory_is_refused(self):
        base = self.runner.local(RUNTIME)
        base.mkdir(parents=True)
        (base / 'broker').symlink_to(self.tmp)
        with self.assertRaises(oc2.Stop):
            self.launch()
        self.assertEqual(self.runner.fed, [])

    def test_guest_side_tampering_after_copy_is_detected(self):
        def corrupt(target):
            if target.name == 'index.js':
                target.write_bytes(b'// swapped in guest\n')

        self.runner.after_cp = corrupt
        with self.assertRaises(oc2.Stop):
            self.launch()
        self.assertEqual(self.runner.fed, [])

    def run_guest_script(self):
        script = rbr.GUEST_VERIFY_SCRIPT.replace(
            "ROOT = '/home/agent/workspace/oc2'",
            f'ROOT = {str(self.runner.local(hb.GUEST_ROOT))!r}', 1)
        return subprocess.run(
            [sys.executable, '-I', '-c', script, str(self.runner.local(RUNTIME)),
             json.dumps(fake_manifest(), sort_keys=True),
             hashlib.sha256(rbr.config_bytes(RUNTIME)).hexdigest(), CA_SHA256],
            capture_output=True, text=True, check=False)

    def test_guest_verifier_rejects_extra_linked_and_modified_content_on_its_own(self):
        self.launch()
        self.assertEqual(self.run_guest_script().returncode, 0)
        base = self.runner.local(RUNTIME + '/broker')
        (base / 'src/guest/extra.mjs').write_text('x', encoding='utf-8')
        self.assertNotEqual(self.run_guest_script().returncode, 0)
        (base / 'src/guest/extra.mjs').unlink()
        (base / 'src/guest/index.js').write_bytes(b'// edited\n')
        self.assertNotEqual(self.run_guest_script().returncode, 0)
        (base / 'src/guest/index.js').unlink()
        (base / 'src/guest/index.js').symlink_to('/etc/hostname')
        self.assertNotEqual(self.run_guest_script().returncode, 0)
        (base / 'src/guest/index.js').unlink()
        (base / 'src/guest/index.js').write_bytes(SOURCE_FILES['src/guest/index.js'])
        self.assertEqual(self.run_guest_script().returncode, 0)
        config = self.runner.local(RUNTIME + '/config/opencode/opencode.jsonc')
        config.write_text('{"providers": {"openai": {}}}\n', encoding='utf-8')
        self.assertNotEqual(self.run_guest_script().returncode, 0)

    def test_guest_verifier_binds_the_staged_ca_bytes_to_the_runtime_identity(self):
        self.launch()
        ca_file = self.runner.local(RUNTIME + '/broker/ca/host-broker-ca.pem')
        self.assertEqual(ca_file.read_bytes(), CA_DATA)
        self.assertEqual(self.run_guest_script().returncode, 0)
        ca_file.write_bytes(CA_DATA + b'tampered')
        self.assertNotEqual(self.run_guest_script().returncode, 0)
        ca_file.write_bytes(CA_DATA)
        ca_file.unlink()
        ca_file.symlink_to(self.tmp / 'outside-ca.pem')
        self.assertNotEqual(self.run_guest_script().returncode, 0)

    def test_identity_mismatches_stop_before_any_placement(self):
        for broker in (broker_launch(sandbox_label='another'),):
            with self.assertRaises(oc2.Stop):
                self.launch(broker)
        other = make_request(self.config, digest='e' * 64)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(oc2.Stop):
            oc2.launch(self.runner, other, broker_launch())
        self.assertEqual(self.runner.fed, [])
        self.assertFalse(self.runner.local(RUNTIME + '/broker').exists())

    def test_mismatched_ca_identity_stops_before_any_placement(self):
        wrong_ca = hb.BrokerCaCertificate(b'wrong public CA', 'f' * 64)
        with self.assertRaises(oc2.Stop):
            self.launch(broker_launch(ca_certificate=wrong_ca))
        self.assertEqual(self.runner.fed, [])
        self.assertFalse(self.runner.local(RUNTIME + '/broker').exists())

    def test_config_not_matching_runtime_stops(self):
        self.config.write_bytes(rbr.config_bytes(hb.GUEST_ROOT + '/runtime/' + 'e' * 16))
        with self.assertRaises(oc2.Stop):
            self.launch()
        self.assertEqual(self.runner.fed, [])

    def test_tty_prompt_missing_stops_and_cloudflare_runtime_is_refused(self):
        with self.assertRaises(oc2.Stop):
            self.launch(broker_launch(prompt=''))
        self.assertEqual(self.runner.fed, [])
        request = make_request(self.config, cloudflare=oc2.CloudflareGatewayRuntime('0' * 32, 'gw'))
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(oc2.Stop):
            oc2.launch(self.runner, request, broker_launch())
        self.assertEqual(self.runner.fed, [])

    def test_default_launch_is_unchanged(self):
        with patch.dict(os.environ, {}, clear=True):
            oc2.launch(self.runner, self.request)
        self.assertEqual(self.runner.fed, [])
        auth, tui = self.runner.calls[-2:]
        self.assertIn('oc2_oauth.py', auth)
        self.assertEqual(tui[-2:], (oc2.PINNED[0], '--standalone'))
        self.assertFalse(any('--broker-url=' in part for call in self.runner.calls for part in call))
        self.assertFalse(any(
            part.startswith(('NODE_EXTRA_CA_CERTS=', 'OC2_HOST_BROKER_URL='))
            for call in self.runner.calls for part in call
        ))


class RunHostBrokerTests(unittest.TestCase):
    """_run_host_broker end to end against the fake Sandbox (no sbx/network)."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.runner = FsRunner(self.tmp / 'guest')
        self.runner.root.mkdir()

    def run_broker(self, *, artifacts=True, probe_ok=True, mode='m1', label='oc2-dev'):
        read_fd, write_fd = os.pipe()
        os.write(write_fd, (TOKEN + '\n').encode())
        os.close(write_fd)
        sel = hb.build_selection(
            url=URL, mode=mode, sandbox_label=label, capability_fd=read_fd,
            broker_ca_sha256=CA_SHA256,
            fixture_rel=None if mode == 'm1' else 'fixtures')
        ca_certificate = hb.BrokerCaCertificate(CA_DATA, CA_SHA256)
        args = oc2.argparse.Namespace(
            sandbox='oc2-dev', host_broker_artifacts=self.tmp / 'src' if artifacts else None,
            host_broker_prompt='say hello', host_broker_ca_cert=self.tmp / 'ca.pem')

        def fake_download(destination: pathlib.Path) -> pathlib.Path:
            """Write a fake binary into the private empty directory supplied by the caller."""
            assert destination.is_dir()
            assert destination.stat().st_mode & 0o077 == 0
            assert not any(destination.iterdir())
            binary = destination / 'opencode'
            binary.write_bytes(b'fake')
            return binary

        def probe(_url, _ca_data):
            if not probe_ok:
                raise hb.HostBrokerError('Host Broker is not reachable; no fallback provider is used')

        result_artifacts = verified()
        with patch.object(oc2, 'Runner', return_value=self.runner), \
                patch.object(oc2.shutil, 'which', return_value='/usr/bin/sbx'), \
                patch.object(oc2, 'download_verified_cli', fake_download), \
                patch.object(oc2, 'transfer_workspace', return_value='/workspace/project'), \
                patch.object(oc2_host_broker_probe(), 'probe_broker', probe), \
                patch.object(rbr, 'load_manifest', return_value=(fake_manifest(), 'd' * 64)), \
                patch.object(rbr, 'verify_source', return_value=result_artifacts), \
                patch.dict(os.environ, {}, clear=True), \
                contextlib.redirect_stdout(io.StringIO()):
            return oc2._run_host_broker(args, None, sel, ca_certificate)

    def test_broker_launch_creates_sandbox_without_credential_mixin(self):
        self.assertEqual(self.run_broker(), 0)
        creates = [c for c in self.runner.calls if c[0] == 'create' and '--name' in c]
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0].count('--kit'), 1)
        self.assertNotIn('oc2-credentials', repr(self.runner.calls))
        self.assertEqual(len(self.runner.fed), 1)
        self.assertNotIn('secret', repr([c for c in self.runner.calls if c[0] != 'cp']))
        self.assertNotIn(TOKEN, repr(self.runner.calls))
        digest_dirs = list(self.runner.local(hb.GUEST_ROOT + '/runtime').iterdir())
        self.assertEqual(len(digest_dirs), 1)
        self.assertTrue((digest_dirs[0] / 'broker/bin/guest-launch.mjs').is_file())
        self.assertEqual(
            (digest_dirs[0] / 'broker/ca/host-broker-ca.pem').read_bytes(), CA_DATA,
        )

    def test_unreachable_broker_missing_artifacts_or_label_stop_without_sandbox(self):
        for kwargs in ({'probe_ok': False}, {'artifacts': False}, {'label': 'other'}):
            self.runner.calls.clear()
            with self.subTest(kwargs=kwargs), self.assertRaises((hb.HostBrokerError, oc2.Stop)):
                self.run_broker(**kwargs)
            self.assertEqual(self.runner.fed, [])
            self.assertFalse([c for c in self.runner.calls if c[0] == 'create' and '--name' in c])


def oc2_host_broker_probe():
    return hb


class CliTests(unittest.TestCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                patch.object(oc2, 'Runner') as runner_cls, \
                patch.object(hb, 'load_broker_ca',
                             return_value=hb.BrokerCaCertificate(CA_DATA, CA_SHA256)), \
                patch.dict(os.environ, {}, clear=False):
            os.environ.pop(hb.CAPABILITY_ENV, None)
            code = oc2.main(list(argv))
        runner_cls.assert_not_called()
        return code, out.getvalue(), err.getvalue()

    BASE = ('--host-broker-url', URL, '--host-broker-ca-cert', '/tmp/oc2-test-ca.pem',
            '--host-broker-mode', 'm1',
            '--host-broker-sandbox-label', 'oc2-dev', '--host-broker-capability-fd', '3',
            '--host-broker-prompt', 'say hello')

    def test_options_without_opt_in_are_refused(self):
        for option in (('--host-broker-url', URL), ('--host-broker-ca-cert', '/tmp/ca.pem'),
                       ('--host-broker-prompt', 'x'),
                       ('--host-broker-artifacts', '/tmp')):
            code, _out, err = self.run_main(*option)
            self.assertEqual(code, 1)
            self.assertIn('require --use-host-broker', err)

    def test_ca_certificate_is_required_with_host_broker_opt_in(self):
        args = list(self.BASE)
        index = args.index('--host-broker-ca-cert')
        del args[index:index + 2]
        code, _out, err = self.run_main('--use-host-broker', *args, '--sandbox', 'oc2-dev')
        self.assertEqual(code, 1)
        self.assertIn('--host-broker-ca-cert is required', err)

    def test_conflicting_modes_are_refused(self):
        for extra in ('--use-cloudflare-ai-gateway', '--allow-paid-inference', '--prepare-only'):
            with self.subTest(extra=extra):
                code, _out, err = self.run_main(
                    '--use-host-broker', *self.BASE, '--sandbox', 'oc2-dev', extra)
                self.assertEqual(code, 1)
                self.assertIn('cannot be combined', err)

    def test_invalid_cli_values_and_tui_request_are_refused(self):
        for override in (('--host-broker-mode', 'm9'), ('--host-broker-url', 'https://x:1/v1'),
                         ('--host-broker-capability-fd', '1')):
            argv = list(self.BASE)
            argv[argv.index(override[0]) + 1] = override[1]
            with self.subTest(override=override):
                code, _out, err = self.run_main(
                    '--use-host-broker', *argv, '--sandbox', 'oc2-dev')
                self.assertEqual(code, 1)
                self.assertIn('OC2_STOP', err)
        no_prompt = [a for a in self.BASE[:-2]]
        code, _out, err = self.run_main('--use-host-broker', *no_prompt, '--sandbox', 'oc2-dev')
        self.assertEqual(code, 1)
        self.assertIn('TTY', err)

    def test_label_must_match_sandbox(self):
        code, _out, err = self.run_main('--use-host-broker', *self.BASE, '--sandbox', 'other-sb')
        self.assertEqual(code, 1)
        self.assertIn('does not match', err)

    def test_capability_in_environment_is_refused(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                patch.dict(os.environ, {hb.CAPABILITY_ENV: TOKEN}):
            code = oc2.main(['--use-host-broker', *self.BASE, '--sandbox', 'oc2-dev'])
        self.assertEqual(code, 1)
        self.assertNotIn(TOKEN, out.getvalue() + err.getvalue())

    def test_dry_run_plans_without_secrets_or_sandbox_calls(self):
        code, out, err = self.run_main(
            '--use-host-broker', *self.BASE, '--sandbox', 'oc2-dev', '--dry-run',
            '--workspace', str(pathlib.Path.cwd()))
        self.assertEqual(code, 0, err)
        self.assertIn('explicit Host Broker provider=oc-cf-aig model=gpt-6-luna mode=m1', out)
        self.assertIn('no TTY', out)
        self.assertNotIn('ocb_', out + err)

    def test_dry_run_without_opt_in_has_no_broker_plan(self):
        code, out, _err = self.run_main(
            '--sandbox', 'oc2-dev', '--dry-run', '--workspace', str(pathlib.Path.cwd()))
        self.assertEqual(code, 0)
        self.assertNotIn('Host Broker', out)


if __name__ == '__main__':
    unittest.main()

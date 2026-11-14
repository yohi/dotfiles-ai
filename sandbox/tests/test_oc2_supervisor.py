"""Offline tests for the OC2 Alternative A Guest Supervisor integration.

No docker, sbx, network, sandbox, credential, real process or real sleep is
used.  Docker is replaced by fakes (FakeTransport / the FakeDocker of
test_oc2_writer); the Guest filesystem is replaced by FakeGuestFs.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS = pathlib.Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str, directory: pathlib.Path = SCRIPTS):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, directory / (name + '.py'))
    if spec is None or spec.loader is None:
        raise ImportError(f'could not load module: {name}')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


w = load('oc2_writer')
sup = load('oc2_supervisor')
tw = load('test_oc2_writer', TESTS)

CID, CID2, OTHER = tw.CID, tw.CID2, tw.OTHER
BOOT, STARTED, IMAGE_ID = tw.BOOT, tw.STARTED, tw.IMAGE_ID
SENTINEL = tw.SENTINEL
DOCKER_PATH = '/usr/bin/docker'
SCOPE_REL = f'/system.slice/docker-{CID}.scope'
SCOPE = '/sys/fs/cgroup' + SCOPE_REL
INODE = 987654
WRITER_BLOB = '877ac9289655d82d4ce5d94ee081e8298332742c'


def status_text(uid: int, saved: int | None = None) -> str:
    saved = uid if saved is None else saved
    return f'Name:\tx\nUid:\t{uid}\t{uid}\t{saved}\t{uid}\nGid:\t{uid}\t{uid}\t{uid}\t{uid}\n'


def exc_texts(exc: BaseException) -> str:
    """Return str/repr of ``exc`` and its whole cause/context chain."""
    seen, out, todo = [], [], [exc]
    while todo:
        cur = todo.pop()
        if cur is None or any(cur is s for s in seen):
            continue
        seen.append(cur)
        out += [str(cur), repr(cur)]
        todo += [cur.__cause__, cur.__context__]
    return '\n'.join(out)


# --- Fakes -------------------------------------------------------------------------

class FakeGuestFs:
    """In-memory GuestFs with explicit absent / unknown / symlink states."""

    def __init__(self):
        self.dirs: dict[str, int] = {}
        self.files: dict[str, object] = {}
        self.symlinks: set[str] = set()
        self.unknown: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    @classmethod
    def standard(cls):
        fs = cls()
        fs.dirs.update({'/sys/fs/cgroup': 1, '/sys/fs/cgroup/system.slice': 2,
                        SCOPE: INODE, '/proc': 3})
        fs.files.update({
            '/proc/sys/kernel/random/boot_id': BOOT + '\n',
            '/proc/1/status': status_text(0),
            '/proc/4242/status': status_text(10001),
            '/proc/4242/cgroup': f'0::{SCOPE_REL}\n',
        })
        return fs

    def writer_exit(self):
        self.dirs.pop(SCOPE, None)
        for path in [p for p in self.files if p.startswith('/proc/4242/')]:
            del self.files[path]

    def _check(self, path):
        if path in self.unknown:
            raise sup.GuestFsUnknown('unknown')

    def read_text(self, path):
        self.calls.append(('read_text', path))
        self._check(path)
        if path in self.symlinks:
            raise sup.GuestFsUnknown('symlink')
        value = self.files.get(path)
        if value is None:
            raise sup.GuestFsAbsent('absent')
        if isinstance(value, BaseException):
            raise value
        return value

    def lstat(self, path):
        self.calls.append(('lstat', path))
        self._check(path)
        if path in self.symlinks:
            return sup.FsStat(5, 'symlink')
        if path in self.dirs:
            return sup.FsStat(self.dirs[path], 'dir')
        if path in self.files:
            return sup.FsStat(7, 'file')
        raise sup.GuestFsAbsent('absent')

    def listdir(self, path):
        self.calls.append(('listdir', path))
        self._check(path)
        if path not in self.dirs:
            raise sup.GuestFsAbsent('absent')
        prefix = path + '/'
        names = set()
        for key in list(self.dirs) + list(self.files) + list(self.symlinks):
            if key.startswith(prefix):
                names.add(key[len(prefix):].split('/')[0])
        return tuple(sorted(names))


class HookDocker(tw.FakeDocker):
    """FakeDocker that lists the Writer once created and supports hooks."""

    def __init__(self, spec, existing=None, fs=None):
        super().__init__(spec, existing)
        self.hooks: dict = {}
        self.fs = fs

    def run(self, argv, *, timeout):
        verb = list(argv)[1]
        hook = self.hooks.get(verb)
        if hook is not None:
            hook()
        if verb == 'ps' and not self.responses.get('ps'):
            self.calls.append(list(argv))
            ids = [i['Id'] for i in self.existing]
            if self.state != 'none':
                ids.append(CID)
            return 0, ''.join(i + '\n' for i in ids)
        result = super().run(argv, timeout=timeout)
        if verb in ('stop', 'kill') and self.fs is not None and self.state == 'exited':
            self.fs.writer_exit()
        return result


class SimTimeout(Exception):
    pass


class FakeTransport:
    """Transport returning canned TransportResults and recording argv."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[tuple[list, int, int]] = []

    def __call__(self, argv, timeout, max_output):
        self.calls.append((list(argv), timeout, max_output))
        if self.results:
            item = self.results.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        return sup.TransportResult(0, b'ok\n', False, False)


class BridgeTransport:
    """Transport that forwards to a FakeDocker (no real process)."""

    def __init__(self, docker):
        self.docker = docker
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout, max_output):
        assert argv[0] == DOCKER_PATH
        self.calls.append(list(argv))
        try:
            rc, out = self.docker.run(['docker'] + list(argv[1:]), timeout=timeout)
        except SimTimeout:
            return sup.TransportResult(-1, b'', True, False)
        return sup.TransportResult(rc, out.encode('utf-8'), False, False)


def runner_for(transport, **kw):
    return sup.CliDockerRunner(DOCKER_PATH, transport, **kw)


def ok(stdout: bytes = b'') -> object:
    return sup.TransportResult(0, stdout, False, False)


def all_builder_argvs(spec):
    return [w.build_create_argv(spec), w.build_create_argv(tw.make_spec(tty=True)),
            w.build_start_argv(CID), w.build_stop_argv(CID), w.build_stop_argv(CID, 7),
            w.build_kill_argv(CID), w.build_inspect_argv(CID), list(w.LIST_ALL_ARGV)]


# 1 -- DockerRunner adapter ---------------------------------------------------------
class DockerRunnerTest(unittest.TestCase):
    def test_argv_forwarded_with_docker_path(self):
        for argv in all_builder_argvs(tw.make_spec()):
            with self.subTest(verb=argv[1]):
                transport = FakeTransport(ok(b'out\n'))
                rc, out = runner_for(transport).run(argv, timeout=30)
                self.assertEqual((rc, out), (0, 'out\n'))
                self.assertEqual(transport.calls,
                                 [([DOCKER_PATH] + argv[1:], 30, sup.MAX_OUTPUT_BYTES)])

    def test_disallowed_commands_rejected_before_transport(self):
        spec = tw.make_spec()
        create = w.build_create_argv(spec)
        priv = create[:2] + ['--privileged'] + create[2:]
        pid_host = create[:2] + ['--pid', 'host'] + create[2:]
        extra_v = create[:-2] + ['-v', '/:/host:rw'] + create[-2:]
        bad_env = create[:-2] + ['-e', 'API_TOKEN=' + SENTINEL] + create[-2:]
        cases = [
            ['docker', 'exec', CID, 'sh'], ['docker', 'rm', '-f', CID],
            ['docker', 'run', '--rm', 'alpine'], ['docker', 'cp', CID + ':/x', '/tmp'],
            ['docker', 'network', 'ls'], ['docker', 'volume', 'ls'], ['docker', 'build', '.'],
            ['docker', 'context', 'use', 'remote'], ['docker', '--context', 'x', 'ps'],
            ['docker', '-H', 'tcp://x', 'ps', '-a', '-q', '--no-trunc'],
            ['docker', 'start', 'oc2-writer-x'], ['docker', 'start', CID, CID2],
            ['docker', 'start', '-a', CID], ['docker', 'inspect', CID],
            ['docker', 'inspect', '--type', 'image', CID], ['docker', 'ps', '-a', '-q'],
            ['docker', 'stop', CID], ['docker', 'stop', '--timeout', '0', CID],
            ['docker', 'stop', '--timeout', '999', CID],
            ['docker', 'kill', CID], ['docker', 'kill', '--signal', 'TERM', CID],
            ['/bin/sh', 'create'], ['podman', 'ps', '-a', '-q', '--no-trunc'],
            priv, pid_host, extra_v, bad_env, create[:-1], create + ['\x00'],
            ['docker'], [], 'docker ps -a -q --no-trunc', None,
        ]
        for argv in cases:
            with self.subTest(argv=argv if not isinstance(argv, list) else argv[:4]):
                transport = FakeTransport()
                with self.assertRaises(sup.DockerCommandRejected) as ctx:
                    runner_for(transport).run(argv, timeout=10)
                self.assertEqual(transport.calls, [])
                self.assertNotIn(SENTINEL, exc_texts(ctx.exception))

    def test_rejected_error_has_no_argv_text(self):
        argv = w.build_create_argv(tw.make_spec(env=(('HOME', SENTINEL),)))
        argv.insert(2, '--privileged')
        with self.assertRaises(sup.DockerCommandRejected) as ctx:
            runner_for(FakeTransport()).run(argv, timeout=10)
        text = exc_texts(ctx.exception)
        self.assertNotIn(SENTINEL, text)
        self.assertNotIn('--privileged', text)

    def test_docker_path_validation(self):
        for path in ('', 'docker', 'bin/docker', '/usr/bin/../bin/docker', '//usr/bin/docker',
                     '/usr/bin/podman', '/usr/bin/docker/', '/usr/b in/docker', None, 1):
            with self.subTest(path=path):
                with self.assertRaises(sup.SupervisorInputError):
                    sup.CliDockerRunner(path, FakeTransport())
        with self.assertRaises(sup.SupervisorInputError):
            sup.CliDockerRunner(DOCKER_PATH, 'not callable')

    def test_timeout_clamped_and_validated(self):
        transport = FakeTransport()
        runner_for(transport).run(w.build_start_argv(CID), timeout=100000)
        self.assertEqual(transport.calls[0][1], sup.MAX_DOCKER_TIMEOUT_S)
        transport = FakeTransport()
        runner_for(transport, max_timeout=5).run(w.build_start_argv(CID), timeout=45)
        self.assertEqual(transport.calls[0][1], 5)
        for bad_timeout in (0, -1, True, '5', 1.5, None):
            with self.subTest(timeout=bad_timeout):
                transport = FakeTransport()
                with self.assertRaises(sup.SupervisorInputError):
                    runner_for(transport).run(w.build_start_argv(CID), timeout=bad_timeout)
                self.assertEqual(transport.calls, [])

    def test_timeout_result(self):
        transport = FakeTransport(sup.TransportResult(-1, SENTINEL.encode(), True, False))
        with self.assertRaises(sup.DockerTimeoutError) as ctx:
            runner_for(transport).run(w.build_stop_argv(CID), timeout=45)
        self.assertNotIn(SENTINEL, exc_texts(ctx.exception))

    def test_non_zero_exit(self):
        transport = FakeTransport(sup.TransportResult(125, b'Error: ' + SENTINEL.encode(),
                                                      False, False))
        with self.assertRaisesRegex(sup.DockerCommandError, 'rc=125') as ctx:
            runner_for(transport).run(w.build_inspect_argv(CID), timeout=10)
        self.assertNotIn(SENTINEL, exc_texts(ctx.exception))

    def test_malformed_and_non_utf8_output(self):
        for result in (sup.TransportResult(0, b'\xff\xfe' + SENTINEL.encode(), False, False),
                       sup.TransportResult(0, b'abc\x00def', False, False),
                       (0, b'tuple'), None, sup.TransportResult(True, b'', False, False),
                       sup.TransportResult(0, 'str', False, False)):
            with self.subTest(result=type(result).__name__):
                with self.assertRaises(sup.DockerOutputError) as ctx:
                    runner_for(FakeTransport(result)).run(w.build_inspect_argv(CID),
                                                          timeout=10)
                self.assertNotIn(SENTINEL, exc_texts(ctx.exception))

    def test_oversize_output_fails_closed(self):
        with self.assertRaisesRegex(sup.DockerOutputError, 'limit'):
            runner_for(FakeTransport(sup.TransportResult(0, b'x' * 8, False, True)),
                       max_output=8).run(w.build_inspect_argv(CID), timeout=10)
        with self.assertRaisesRegex(sup.DockerOutputError, 'limit'):
            runner_for(FakeTransport(ok(b'x' * 9)), max_output=8).run(
                w.build_inspect_argv(CID), timeout=10)
        self.assertEqual(runner_for(FakeTransport(ok(b'x' * 8)), max_output=8).run(
            w.build_inspect_argv(CID), timeout=10), (0, 'x' * 8))

    def test_transport_exception_does_not_leak(self):
        transport = FakeTransport(RuntimeError('env HOME=' + SENTINEL))
        argv = w.build_create_argv(tw.make_spec(env=(('HOME', SENTINEL),)))
        with self.assertRaises(sup.DockerCommandError) as ctx:
            runner_for(transport).run(argv, timeout=10)
        self.assertNotIn(SENTINEL, exc_texts(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)
        self.assertIsNone(ctx.exception.__context__)

    def test_create_secret_env_never_in_error(self):
        argv = w.build_create_argv(tw.make_spec(env=(('HOME', SENTINEL),)))
        transport = FakeTransport(sup.TransportResult(1, SENTINEL.encode(), False, False))
        with self.assertRaises(sup.DockerCommandError) as ctx:
            runner_for(transport).run(argv, timeout=10)
        self.assertNotIn(SENTINEL, exc_texts(ctx.exception))
        self.assertIn('-e', transport.calls[0][0])

    def test_constructor_does_not_call_transport(self):
        transport = FakeTransport()
        runner_for(transport)
        self.assertEqual(transport.calls, [])
        self.assertEqual({n for n in dir(sup.CliDockerRunner) if not n.startswith('_')},
                         {'run'})


# 2 -- SubprocessTransport (never spawns a real process here) -------------------------
class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakePipe:
    """Fake stdout pipe.  ``script`` items: bytes chunk, None (not ready), or
    an exception.  ``endless`` keeps producing data after the script."""

    def __init__(self, clock, script=(), endless=False, block_s=0.0):
        self.clock = clock
        self.script = list(script)
        self.endless = endless
        self.block_s = block_s
        self.reads = 0
        self.requested: list[int] = []
        self.closed = False

    def close(self):
        self.closed = True

    def read(self, size, timeout_s):
        self.reads += 1
        self.requested.append(size)
        if self.reads > 10000:
            raise AssertionError('unbounded read loop')
        if self.script:
            item = self.script.pop(0)
        elif self.endless:
            item = b'x' * size
        else:
            item = b''
        if item is None:
            self.clock.now += min(self.block_s or timeout_s, timeout_s)
            return None
        if isinstance(item, BaseException):
            raise item
        return item


def fake_reader(stream, size, timeout_s):
    return stream.read(size, timeout_s)


class FakeProc:
    def __init__(self, pipe, pid=4321, rc=0, exit_wait_ok=True, reap_ok=True,
                 kill_raises=False):
        self.stdout = pipe
        self.pid = pid
        self.rc = rc
        self.returncode = None
        self.exit_wait_ok = exit_wait_ok
        self.reap_ok = reap_ok
        self.kill_raises = kill_raises
        self.killed = False
        self.kills = 0
        self.waits: list[float] = []

    def kill(self):
        self.kills += 1
        if self.kill_raises:
            raise OSError('kill ' + SENTINEL)
        self.killed = True

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if len(self.waits) > 5:
            raise AssertionError('unbounded wait loop')
        if self.killed:
            if not self.reap_ok:
                raise subprocess.TimeoutExpired(['x', SENTINEL], timeout)
            self.returncode = -9
            return self.returncode
        if not self.exit_wait_ok:
            raise subprocess.TimeoutExpired(['x', SENTINEL], timeout)
        self.returncode = self.rc
        return self.rc


class FakePopen:
    def __init__(self, proc=None, error=None):
        self.proc = proc
        self.error = error
        self.calls: list[tuple[list, dict]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.error is not None:
            raise self.error
        return self.proc


class FakeKillpg:
    def __init__(self, proc=None, error=None):
        self.proc = proc
        self.error = error
        self.calls: list[tuple[int, int]] = []

    def __call__(self, pgid, sig):
        self.calls.append((pgid, sig))
        if self.error is not None:
            raise self.error
        if self.proc is not None:
            self.proc.killed = True


ARGV = [DOCKER_PATH, 'ps', '-a', '-q', '--no-trunc']


class SubprocessTransportTest(unittest.TestCase):
    def make(self, script=(), env=None, endless=False, block_s=0.0, killpg_error=None,
             popen_error=None, **proc_kw):
        self.clock = FakeClock()
        self.pipe = FakePipe(self.clock, script, endless=endless, block_s=block_s)
        self.proc = FakeProc(self.pipe, **proc_kw)
        self.popen = FakePopen(self.proc, popen_error)
        self.killpg = FakeKillpg(self.proc, killpg_error)
        return sup.SubprocessTransport(env, _popen=self.popen, _clock=self.clock,
                                       _reader=fake_reader, _killpg=self.killpg)

    def assert_killed_and_reaped(self):
        self.assertEqual(self.killpg.calls, [(4321, sup.signal.SIGKILL)])
        self.assertTrue(self.pipe.closed)
        self.assertEqual(self.proc.waits, [sup._REAP_TIMEOUT_S])

    def test_source_never_uses_shell(self):
        source = (SCRIPTS / 'oc2_supervisor.py').read_text(encoding='utf-8')
        self.assertIn('shell=False', source)
        self.assertNotIn('shell=True', source)
        # Only the bounded Popen read loop is allowed: no unbounded capture.
        for frag in ('os.system', 'os.popen', 'shlex', "'--pid'", '.communicate(',
                     'subprocess.run(', 'check_output', 'getoutput', '.read()',
                     'stdout.read('):
            self.assertNotIn(frag, source)
        self.assertIn('subprocess.Popen', source)
        self.assertEqual(source.count('self._popen('), 1)
        self.assertIn('start_new_session=True', source)
        self.assertIn('stdin=subprocess.DEVNULL', source)
        self.assertIn('stderr=subprocess.DEVNULL', source)
        # SubprocessTransport is never instantiated by the module itself.
        self.assertNotIn('SubprocessTransport(', source)

    def test_popen_kwargs_and_env_not_inherited(self):
        with mock.patch.dict(os.environ, {'OC2_TEST_SECRET': SENTINEL}):
            transport = self.make([b'abc', b''])
            result = transport(list(ARGV), 7, 10)
        self.assertEqual(result, sup.TransportResult(0, b'abc', False, False))
        self.assertEqual(len(self.popen.calls), 1)
        argv, kwargs = self.popen.calls[0]
        self.assertEqual(argv, ARGV)
        self.assertIsInstance(argv, list)
        self.assertIs(kwargs['shell'], False)
        self.assertEqual(kwargs['env'], {})
        self.assertIs(kwargs['stdin'], subprocess.DEVNULL)
        self.assertIs(kwargs['stdout'], subprocess.PIPE)
        self.assertIs(kwargs['stderr'], subprocess.DEVNULL)
        self.assertIs(kwargs['start_new_session'], True)
        self.assertIs(kwargs['close_fds'], True)
        self.assertNotIn('timeout', kwargs)
        self.assertEqual(self.killpg.calls, [])
        self.assertTrue(self.pipe.closed)
        transport = self.make([b''], env={'LANG': 'C'})
        transport(list(ARGV), 7, 10)
        self.assertEqual(self.popen.calls[0][1]['env'], {'LANG': 'C'})

    def test_output_below_and_equal_limit(self):
        transport = self.make([b'abc', b'de', b''])
        self.assertEqual(transport(list(ARGV), 5, 8),
                         sup.TransportResult(0, b'abcde', False, False))
        transport = self.make([b'abcd', b'efgh', b''])
        self.assertEqual(transport(list(ARGV), 5, 8),
                         sup.TransportResult(0, b'abcdefgh', False, False))
        self.assertEqual(self.killpg.calls, [])
        self.assertLessEqual(max(self.pipe.requested), 9)

    def test_limit_plus_one_truncated(self):
        transport = self.make([b'abcdefgh', b'i', b'never'])
        result = transport(list(ARGV), 5, 8)
        self.assertEqual(result, sup.TransportResult(-9, b'abcdefgh', False, True))
        self.assertEqual(self.pipe.script, [b'never'])
        self.assert_killed_and_reaped()

    def test_far_over_limit_stops_reading(self):
        transport = self.make(endless=True)
        limit = 3 * sup._READ_CHUNK_BYTES + 17
        result = transport(list(ARGV), 5, limit)
        self.assertTrue(result.truncated)
        self.assertFalse(result.timed_out)
        self.assertEqual(len(result.stdout), limit)
        self.assertLessEqual(sum(self.pipe.requested), limit + 1)
        self.assertLessEqual(max(self.pipe.requested), sup._READ_CHUNK_BYTES)
        self.assertEqual(self.pipe.reads, 4)
        self.assert_killed_and_reaped()

    def test_oversized_reader_chunk_fails_closed(self):
        transport = self.make([b'x' * 100])
        with self.assertRaisesRegex(sup.DockerCommandError, 'read failed'):
            transport(list(ARGV), 5, 8)
        self.assert_killed_and_reaped()

    def test_many_tiny_chunks(self):
        transport = self.make([b'a'] * 50 + [b''])
        self.assertEqual(transport(list(ARGV), 5, 50),
                         sup.TransportResult(0, b'a' * 50, False, False))
        transport = self.make([b'a'] * 51 + [b'b'] * 100)
        result = transport(list(ARGV), 5, 50)
        self.assertEqual(result, sup.TransportResult(-9, b'a' * 50, False, True))
        self.assertEqual(self.pipe.reads, 51)

    def test_timeout_without_output(self):
        transport = self.make([None] * 100, block_s=0.5)
        result = transport(list(ARGV), 2, 10)
        self.assertEqual(result, sup.TransportResult(-1, b'', True, False))
        self.assertEqual(self.pipe.reads, 4)
        self.assertGreaterEqual(self.clock.now, 1002.0)
        self.assert_killed_and_reaped()

    def test_timeout_during_large_output(self):
        clock_holder = {}

        def chunk_then_advance(stream, size, timeout_s):
            clock_holder['clock'].now += 0.5
            return stream.read(size, timeout_s)

        transport = self.make(endless=True)
        clock_holder['clock'] = self.clock
        transport._reader = chunk_then_advance
        result = transport(list(ARGV), 2, 10 * 1024 * 1024)
        self.assertEqual(result, sup.TransportResult(-1, b'', True, False))
        self.assertEqual(self.pipe.reads, 4)
        self.assert_killed_and_reaped()

    def test_eof_but_process_does_not_exit_is_timeout(self):
        transport = self.make([b'ok', b''], exit_wait_ok=False)
        result = transport(list(ARGV), 3, 10)
        self.assertEqual(result, sup.TransportResult(-1, b'', True, False))
        self.assertEqual(self.proc.waits, [3.0, sup._REAP_TIMEOUT_S])
        self.assertEqual(self.killpg.calls, [(4321, sup.signal.SIGKILL)])

    def test_non_zero_exit_preserved(self):
        transport = self.make([b'Error', b''], rc=125)
        self.assertEqual(transport(list(ARGV), 5, 10),
                         sup.TransportResult(125, b'Error', False, False))
        self.assertEqual(self.killpg.calls, [])

    def test_popen_start_failure(self):
        for error in (OSError('no such file ' + SENTINEL), ValueError(SENTINEL),
                      subprocess.SubprocessError(SENTINEL)):
            with self.subTest(error=type(error).__name__):
                transport = self.make(popen_error=error)
                with self.assertRaisesRegex(sup.DockerCommandError, 'start failed') as ctx:
                    transport(list(ARGV), 5, 10)
                self.assertNotIn(SENTINEL, exc_texts(ctx.exception))
                self.assertIsNone(ctx.exception.__context__)
                self.assertEqual(self.pipe.reads, 0)

    def test_read_error_kills_and_fails(self):
        transport = self.make([b'ab', OSError('read ' + SENTINEL)])
        with self.assertRaisesRegex(sup.DockerCommandError, 'read failed') as ctx:
            transport(list(ARGV), 5, 10)
        self.assertNotIn(SENTINEL, exc_texts(ctx.exception))
        self.assert_killed_and_reaped()

    def test_reap_failure_fails_closed(self):
        for script, kw in (([b'x' * 9], {}), ([None] * 10, {'block_s': 1.0}),
                           ([OSError('x')], {})):
            with self.subTest(script=type(script[0]).__name__):
                transport = self.make(script, reap_ok=False, **kw)
                with self.assertRaises(sup.TransportReapError) as ctx:
                    transport(list(ARGV), 2, 8)
                self.assertIsInstance(ctx.exception, sup.DockerCommandError)
                self.assertNotIn(SENTINEL, exc_texts(ctx.exception))
                self.assertIsNone(ctx.exception.__context__)
                self.assertEqual(len(self.killpg.calls), 1)
                self.assertEqual(len(self.proc.waits), 1)
                self.assertTrue(self.pipe.closed)

    def test_killpg_failure_falls_back_to_kill_once(self):
        transport = self.make([b'x' * 9], killpg_error=PermissionError(SENTINEL))
        result = transport(list(ARGV), 2, 8)
        self.assertTrue(result.truncated)
        self.assertEqual(self.proc.kills, 1)
        # Neither signal path works and the child is still alive: fail closed.
        transport = self.make([b'x' * 9], killpg_error=PermissionError(SENTINEL),
                              kill_raises=True, exit_wait_ok=False)
        with self.assertRaises(sup.TransportReapError) as ctx:
            transport(list(ARGV), 2, 8)
        self.assertNotIn(SENTINEL, exc_texts(ctx.exception))
        self.assertEqual(self.proc.kills, 1)
        self.assertEqual(len(self.proc.waits), 1)

    def test_group_already_gone_is_reaped(self):
        transport = self.make([b'x' * 9], killpg_error=ProcessLookupError())
        self.proc.killed = True
        self.assertTrue(transport(list(ARGV), 2, 8).truncated)
        self.assertEqual(self.proc.kills, 0)

    def test_unsafe_pid_never_signals_group(self):
        for pid in (0, 1, -5, None, True):
            with self.subTest(pid=pid):
                transport = self.make([b'x' * 9], pid=pid)
                self.assertTrue(transport(list(ARGV), 2, 8).truncated)
                self.assertEqual(self.killpg.calls, [])
                self.assertEqual(self.proc.kills, 1)

    def test_runner_fails_closed_on_transport_outcomes(self):
        transport = self.make([b'x' * 9])
        with self.assertRaisesRegex(sup.DockerOutputError, 'limit'):
            runner_for(transport, max_output=8).run(list(w.LIST_ALL_ARGV), timeout=5)
        transport = self.make([None] * 10, block_s=1.0)
        with self.assertRaises(sup.DockerTimeoutError):
            runner_for(transport).run(list(w.LIST_ALL_ARGV), timeout=2)
        transport = self.make([b'x' * 9], reap_ok=False)
        with self.assertRaisesRegex(sup.DockerCommandError, 'transport failed') as ctx:
            runner_for(transport, max_output=8).run(list(w.LIST_ALL_ARGV), timeout=5)
        self.assertIsNone(ctx.exception.__context__)
        self.assertEqual(self.popen.calls[0][0], [DOCKER_PATH] + list(w.LIST_ALL_ARGV[1:]))

    def test_invalid_call_arguments(self):
        transport = self.make()
        for argv, timeout, max_output in ((['docker', 'ps'], 5, 10), ([], 5, 10),
                                          ('x', 5, 10), (list(ARGV), 0, 10),
                                          (list(ARGV), True, 10), (list(ARGV), 5, 0),
                                          (list(ARGV), 5, 1.5)):
            with self.subTest(argv=argv, timeout=timeout, max_output=max_output):
                with self.assertRaises(sup.SupervisorInputError):
                    transport(argv, timeout, max_output)
        self.assertEqual(self.popen.calls, [])

    def test_poll_read_on_os_pipe(self):
        read_fd, write_fd = os.pipe()
        try:
            with os.fdopen(read_fd, 'rb', buffering=0) as stream:
                self.assertIsNone(sup._poll_read(stream, 4, 0))
                os.write(write_fd, b'abcdefgh')
                self.assertEqual(sup._poll_read(stream, 4, 1), b'abcd')
                self.assertEqual(sup._poll_read(stream, 100, 1), b'efgh')
                os.close(write_fd)
                write_fd = -1
                self.assertEqual(sup._poll_read(stream, 4, 1), b'')
        finally:
            if write_fd >= 0:
                os.close(write_fd)

    def test_env_validation(self):
        for env in ({'DOCKER_HOST': 'tcp://x'}, {'docker_context': 'x'}, {'A=B': 'x'},
                    {'LANG': 'C\x00'}, {'LANG': 1}):
            with self.subTest(env=list(env)):
                with self.assertRaises(sup.SupervisorInputError):
                    sup.SubprocessTransport(env)

    def test_default_seams_are_real_but_unused_at_construction(self):
        transport = sup.SubprocessTransport()
        self.assertIs(transport._popen, subprocess.Popen)
        self.assertIs(transport._killpg, os.killpg)
        self.assertIs(transport._reader, sup._poll_read)


# 3 -- LocalGuestFs (temporary directory only) -----------------------------------------
class LocalGuestFsTest(unittest.TestCase):
    def test_no_follow_and_absent_vs_unknown(self):
        fs = sup.LocalGuestFs()
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, 'f')
            with open(target, 'w', encoding='utf-8') as handle:
                handle.write('hello\n')
            link = os.path.join(tmp, 'l')
            os.symlink(target, link)
            os.mkdir(os.path.join(tmp, 'd'))
            self.assertEqual(fs.read_text(target), 'hello\n')
            with self.assertRaises(sup.GuestFsUnknown):
                fs.read_text(link)
            with self.assertRaises(sup.GuestFsAbsent):
                fs.read_text(os.path.join(tmp, 'missing'))
            self.assertEqual(fs.lstat(link).kind, 'symlink')
            self.assertEqual(fs.lstat(os.path.join(tmp, 'd')).kind, 'dir')
            self.assertEqual(set(fs.listdir(tmp)), {'f', 'l', 'd'})
            with self.assertRaises(sup.GuestFsUnknown):
                fs.listdir(link)
            for bad_path in ('relative', tmp + '/../x', tmp + '/', ''):
                with self.assertRaises(sup.GuestFsUnknown):
                    fs.read_text(bad_path)


# 4 -- GuestHostProbe ----------------------------------------------------------------
class ProbeBase(unittest.TestCase):
    def setUp(self):
        self.spec = tw.make_spec()
        self.fs = FakeGuestFs.standard()
        self.docker = HookDocker(self.spec, fs=self.fs)
        self.docker.state = 'running'
        self.probe = sup.GuestHostProbe(self.docker, self.fs,
                                        repo_source=self.spec.repo_source)

    def identity(self, cid=CID):
        return w.WriterIdentity(cid, IMAGE_ID, STARTED, INODE, BOOT)

    def other(self, status='running', mounts=None, binds=None):
        info = tw.make_inspect(tw.make_spec(tw.GEN2), OTHER, status)
        info['Name'] = '/unrelated'
        info['Config']['Labels'] = {}
        if mounts is not None:
            info['Mounts'] = mounts
        if binds is not None:
            info['HostConfig']['Binds'] = binds
        return info


class BootIdTest(ProbeBase):
    def test_boot_id(self):
        self.assertEqual(self.probe.boot_id(), BOOT)
        for value in ('not-a-uuid\n', 'ABCDEF01-2222-4333-8444-555555555555', '',
                      BOOT + 'x', BOOT.replace('-', '')):
            with self.subTest(value=value):
                self.fs.files['/proc/sys/kernel/random/boot_id'] = value
                self.assertIsNone(self.probe.boot_id())
        self.fs.unknown.add('/proc/sys/kernel/random/boot_id')
        self.assertIsNone(self.probe.boot_id())
        self.fs.unknown.clear()
        del self.fs.files['/proc/sys/kernel/random/boot_id']
        self.assertIsNone(self.probe.boot_id())
        self.fs.files['/proc/sys/kernel/random/boot_id'] = RuntimeError('boom')
        self.assertIsNone(self.probe.boot_id())


class CgroupInodeTest(ProbeBase):
    def test_ok(self):
        self.assertEqual(self.probe.cgroup_inode(CID), INODE)
        self.assertEqual(self.docker.verbs(), ['inspect', 'inspect'])
        self.assertIn(('lstat', SCOPE), self.fs.calls)

    def test_cgroupfs_driver_path_ok(self):
        rel = f'/docker/{CID}'
        self.fs.dirs.update({'/sys/fs/cgroup/docker': 9, '/sys/fs/cgroup' + rel: 4321})
        self.fs.files['/proc/4242/cgroup'] = f'0::{rel}\n'
        self.assertEqual(self.probe.cgroup_inode(CID), 4321)

    def test_absent_or_unreadable(self):
        cases = {
            'scope absent': lambda fs: fs.dirs.pop(SCOPE),
            'scope unknown': lambda fs: fs.unknown.add(SCOPE),
            'proc cgroup absent': lambda fs: fs.files.pop('/proc/4242/cgroup'),
            'proc cgroup unknown': lambda fs: fs.unknown.add('/proc/4242/cgroup'),
            'proc status unknown': lambda fs: fs.unknown.add('/proc/4242/status'),
            'root unknown': lambda fs: fs.unknown.add('/sys/fs/cgroup'),
            'symlink component': lambda fs: fs.symlinks.add('/sys/fs/cgroup/system.slice'),
            'symlink final': lambda fs: fs.symlinks.add(SCOPE),
            'scope is file': lambda fs: (fs.dirs.pop(SCOPE), fs.files.update({SCOPE: 'x'})),
            'cgroup v1 lines': lambda fs: fs.files.update(
                {'/proc/4242/cgroup': f'1:name=systemd:/x\n0::{SCOPE_REL}\n'}),
            'traversal': lambda fs: fs.files.update(
                {'/proc/4242/cgroup': f'0::/system.slice/../system.slice/docker-{CID}.scope\n'}),
            'disagreement': lambda fs: fs.files.update(
                {'/proc/4242/cgroup': f'0::/system.slice/docker-{OTHER}.scope\n'}),
            'nested child': lambda fs: fs.files.update(
                {'/proc/4242/cgroup': f'0::{SCOPE_REL}/child\n'}),
            'relative': lambda fs: fs.files.update(
                {'/proc/4242/cgroup': f'0::system.slice/docker-{CID}.scope\n'}),
            'pid not writer uid': lambda fs: fs.files.update(
                {'/proc/4242/status': status_text(0)}),
            'fs raises': lambda fs: fs.files.update({'/proc/4242/cgroup': RuntimeError('x')}),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                self.setUp()
                mutate(self.fs)
                self.assertIsNone(self.probe.cgroup_inode(CID))
                self.assertIsNone(self.probe.observe(self.identity()).writer_uid_pids)

    def test_safe_rel_and_walk_reject_traversal(self):
        for rel in ('/a/../b', '../a', 'a', '/a//b', '/a/./b', '/', '', '/a/b/', '/a\x00',
                    '/a b', None):
            with self.subTest(rel=rel):
                self.assertIsNone(sup._safe_cgroup_rel(rel))
                self.assertEqual(self.probe._walk_cgroup(rel), ('unknown', None))

    def test_docker_side_failures(self):
        running = tw.make_inspect(self.spec, CID, 'running')
        changed = copy.deepcopy(running)
        changed['State']['Pid'] = 5555
        restarted = copy.deepcopy(running)
        restarted['State']['StartedAt'] = '2026-11-14T09:09:09Z'
        swapped = tw.make_inspect(self.spec, CID2, 'running')
        stopped = tw.stopped_inspect(self.spec)
        cases = {
            'inspect fails': [(1, '')],
            'inspect raises': [RuntimeError('x')],
            'malformed': [(0, '{bad')],
            'not running': [(0, json.dumps([stopped]))],
            'id swapped': [(0, json.dumps([swapped]))],
            'pid changed after read': [(0, json.dumps([running])), (0, json.dumps([changed]))],
            'restarted after read': [(0, json.dumps([running])),
                                     (0, json.dumps([restarted]))],
        }
        for name, queued in cases.items():
            with self.subTest(case=name):
                self.setUp()
                self.docker.queue('inspect', *queued)
                self.assertIsNone(self.probe.cgroup_inode(CID))

    def test_invalid_cid_no_docker_call(self):
        for cid in ('', 'oc2-writer-x', CID[:12], CID.upper(), '-f', None):
            with self.subTest(cid=cid):
                self.assertIsNone(self.probe.cgroup_inode(cid))
        self.assertEqual(self.docker.calls, [])


class ObserveTest(ProbeBase):
    def confirmed(self):
        self.assertEqual(self.probe.cgroup_inode(CID), INODE)
        self.docker.state = 'exited'
        self.fs.writer_exit()

    def test_clean_after_stop(self):
        # Docker-side zero RW holders is not proof of kernel-wide absence, so
        # the Docker-only probe reports rw_mount_holders as unknown (None).
        self.confirmed()
        obs = self.probe.observe(self.identity())
        self.assertEqual(obs, w.StopObservation(False, (), None, BOOT))
        self.assertEqual(self.probe._docker_rw_mount_holders(), ())

    def test_docker_zero_is_not_absence(self):
        self.confirmed()
        self.docker.existing = []
        self.assertEqual(self.probe._docker_rw_mount_holders(), ())
        holders = self.probe.observe(self.identity()).rw_mount_holders
        self.assertIsNone(holders)
        self.assertNotEqual(holders, ())
        self.assertIn(['docker', 'ps', '-a', '-q', '--no-trunc'], self.docker.calls)

    def test_unknown_rw_holders_never_stopped_verified(self):
        self.confirmed()
        obs = self.probe.observe(self.identity())
        self.assertIsNone(obs.rw_mount_holders)
        stopped = tw.stopped_inspect(self.spec)
        verdict = w.verify_writer_stopped(self.identity(), stopped, stopped, obs, obs)
        self.assertFalse(verdict.verified)
        self.assertEqual(verdict.status, w.STATUS_GUEST_QUIESCENCE_UNVERIFIED)
        self.assertTrue(any('rw mount holders unknown' in r for r in verdict.reasons))
        # Only rw_mount_holders is missing: an independent sufficient
        # observation of () would be the only route to STOPPED_VERIFIED.
        sufficient = dataclasses.replace(obs, rw_mount_holders=())
        self.assertTrue(w.verify_writer_stopped(self.identity(), stopped, stopped,
                                                sufficient, sufficient).verified)

    def test_cgroup_present_absent_unknown(self):
        self.confirmed()
        self.fs.dirs[SCOPE] = INODE
        self.assertIs(self.probe.observe(self.identity()).cgroup_exists, True)
        del self.fs.dirs[SCOPE]
        self.assertIs(self.probe.observe(self.identity()).cgroup_exists, False)
        self.fs.unknown.add('/sys/fs/cgroup/system.slice')
        self.assertIsNone(self.probe.observe(self.identity()).cgroup_exists)
        self.fs.unknown.clear()
        self.fs.unknown.add(SCOPE)
        self.assertIsNone(self.probe.observe(self.identity()).cgroup_exists)

    def test_absence_requires_readable_parent_listing(self):
        self.confirmed()
        original = self.fs.listdir

        def failing_listdir(path):
            if path == '/sys/fs/cgroup/system.slice':
                raise sup.GuestFsUnknown('unreadable')
            return original(path)

        self.fs.listdir = failing_listdir
        self.assertIsNone(self.probe.observe(self.identity()).cgroup_exists)

    def test_unconfirmed_identity_is_unknown(self):
        self.docker.state = 'exited'
        self.fs.writer_exit()
        obs = self.probe.observe(self.identity())
        self.assertIsNone(obs.cgroup_exists)
        self.assertIsNone(obs.writer_uid_pids)
        self.assertEqual(obs.boot_id, BOOT)

    def test_invalid_identity_all_unknown(self):
        for ident in (None, 'x', w.WriterIdentity('bad', IMAGE_ID, STARTED, INODE, BOOT)):
            with self.subTest(ident=ident):
                self.assertEqual(self.probe.observe(ident),
                                 w.StopObservation(None, None, None, None))

    def test_writer_uid_process_remaining(self):
        self.confirmed()
        self.fs.files['/proc/555/status'] = status_text(10001)
        self.fs.files['/proc/556/status'] = status_text(1000, saved=10001)
        self.assertEqual(self.probe.observe(self.identity()).writer_uid_pids, (555, 556))

    def test_unreadable_proc_entry_fails_closed(self):
        self.confirmed()
        self.fs.files['/proc/777/status'] = status_text(0)
        self.fs.unknown.add('/proc/777/status')
        self.assertIsNone(self.probe.observe(self.identity()).writer_uid_pids)
        self.fs.unknown.clear()
        self.fs.files['/proc/777/status'] = 'Name:\tx\nUid:\tbad\n'
        self.assertIsNone(self.probe.observe(self.identity()).writer_uid_pids)
        self.fs.files['/proc/777/status'] = RuntimeError('boom')
        self.assertIsNone(self.probe.observe(self.identity()).writer_uid_pids)
        del self.fs.files['/proc/777/status']
        self.fs.unknown.add('/proc')
        self.assertIsNone(self.probe.observe(self.identity()).writer_uid_pids)

    def test_vanished_pid_ignored(self):
        self.confirmed()
        original = self.fs.listdir
        self.fs.listdir = lambda path: original(path) + (('888',) if path == '/proc' else ())
        self.assertEqual(self.probe.observe(self.identity()).writer_uid_pids, ())

    def test_rw_holder_other_running_container(self):
        self.confirmed()
        repo = self.spec.repo_source
        self.docker.existing = [self.other(mounts=[
            {'Type': 'bind', 'Source': repo, 'Destination': '/src', 'RW': True}],
            binds=[f'{repo}:/src'])]
        obs = self.probe.observe(self.identity())
        self.assertEqual(obs.rw_mount_holders, (OTHER,))
        inspected = [c[-1] for c in self.docker.calls if c[1] == 'inspect']
        self.assertIn(OTHER, inspected)
        self.assertIn(['docker', 'ps', '-a', '-q', '--no-trunc'], self.docker.calls)

    def test_rw_holder_variants(self):
        repo = self.spec.repo_source
        parent = repo.rsplit('/', 2)[0]
        cases = {
            'ro mount': ([{'Type': 'bind', 'Source': repo, 'Destination': '/s', 'RW': False}],
                         [f'{repo}:/s:ro'], 'running', None),
            'rw exited': ([{'Type': 'bind', 'Source': repo, 'Destination': '/s', 'RW': True}],
                          [f'{repo}:/s'], 'exited', None),
            'rw parent dir': ([{'Type': 'bind', 'Source': parent, 'Destination': '/s',
                                'RW': True}], [f'{parent}:/s'], 'running', (OTHER,)),
            'rw root': ([{'Type': 'bind', 'Source': '/', 'Destination': '/h', 'RW': True}],
                        ['/:/h'], 'running', (OTHER,)),
            'rw subdir': ([{'Type': 'bind', 'Source': repo + '/.git', 'Destination': '/g',
                            'RW': True}], [], 'running', (OTHER,)),
            'binds rw only': ([], [f'{repo}:/s:rw'], 'running', (OTHER,)),
            'paused rw': ([{'Type': 'bind', 'Source': repo, 'Destination': '/s', 'RW': True}],
                          [], 'paused', (OTHER,)),
            'unrelated rw': ([{'Type': 'bind', 'Source': repo + '-other', 'Destination': '/s',
                               'RW': True}], [], 'running', None),
        }
        for name, (mounts, binds, status, expected) in cases.items():
            with self.subTest(case=name):
                self.setUp()
                self.confirmed()
                other = self.other(status=status, mounts=mounts, binds=binds)
                if status == 'paused':
                    other['State']['Running'] = True
                self.docker.existing = [other]
                self.assertEqual(self.probe.observe(self.identity()).rw_mount_holders,
                                 expected)
                # Docker-side view: None (no Docker-visible holder) means ().
                self.assertEqual(self.probe._docker_rw_mount_holders(), expected or ())

    def test_running_writer_itself_reported(self):
        self.assertEqual(self.probe.cgroup_inode(CID), INODE)
        self.assertEqual(self.probe.observe(self.identity()).rw_mount_holders, (CID,))

    def test_enumeration_failures_unknown(self):
        def malformed_mounts(info):
            info['Mounts'] = 'x'

        def malformed_rw(info):
            info['Mounts'] = [{'Type': 'bind', 'Source': '/x', 'RW': 'yes'}]

        def unknown_status(info):
            info['State']['Status'] = 'weird'
            info['State']['Running'] = False

        def missing_state(info):
            del info['State']

        def bad_binds(info):
            info['HostConfig']['Binds'] = 'x'

        for mutate in (malformed_mounts, malformed_rw, unknown_status, missing_state,
                       bad_binds):
            with self.subTest(case=mutate.__name__):
                self.setUp()
                self.confirmed()
                other = self.other()
                mutate(other)
                self.docker.existing = [other]
                self.assertIsNone(self.probe.observe(self.identity()).rw_mount_holders)
                self.assertIsNone(self.probe._docker_rw_mount_holders())
        for queued in (('ps', (1, '')), ('ps', RuntimeError('x')),
                       ('ps', (0, 'not-an-id\n')), ('inspect', (1, '')),
                       ('inspect', (0, '[]'))):
            with self.subTest(queued=queued):
                self.setUp()
                self.confirmed()
                self.docker.queue(*queued)
                self.assertIsNone(self.probe.observe(self.identity()).rw_mount_holders)

    def test_no_repo_source_is_unknown(self):
        probe = sup.GuestHostProbe(self.docker, self.fs)
        self.assertIsNone(probe.observe(self.identity()).rw_mount_holders)
        for repo in ('relative', '/a/../b', '//a', '/a/'):
            with self.assertRaises(sup.SupervisorInputError):
                sup.GuestHostProbe(self.docker, self.fs, repo_source=repo)

    def test_observe_never_raises(self):
        self.confirmed()

        class Exploding:
            def __getattr__(self, name):
                raise RuntimeError('boom')

        probe = sup.GuestHostProbe(Exploding(), Exploding(), repo_source=self.spec.repo_source)
        self.assertEqual(probe.observe(self.identity()), w.StopObservation(None, None, None,
                                                                          None))
        self.assertIsNone(probe.cgroup_inode(CID))
        self.assertIsNone(probe.boot_id())


# 5 -- GuestSupervisor ---------------------------------------------------------------
class SupervisorBase(unittest.TestCase):
    def setUp(self):
        self.spec = tw.make_spec()
        self.docker = HookDocker(self.spec)
        self.bridge = BridgeTransport(self.docker)
        self.runner = runner_for(self.bridge)
        self.probe = tw.FakeProbe()
        self.sleeper = tw.Sleeper()
        self.factory_calls = 0

    def factory(self, spec):
        self.factory_calls += 1
        return w.WriterLifecycle(self.runner, self.probe, sleep=self.sleeper)

    def make(self):
        return sup.GuestSupervisor(tw.make_key(), self.factory)

    def running(self):
        s = self.make()
        s.launch(self.spec)
        self.assertIs(s.state, sup.SupervisorState.RUNNING)
        return s

    def creates(self):
        return self.docker.verbs().count('create')


class SupervisorLaunchTest(SupervisorBase):
    def test_happy_path(self):
        s = self.make()
        self.assertIs(s.state, sup.SupervisorState.NEW)
        self.assertIsNone(s.identity)
        self.assertEqual(s.session_key, tw.make_key())
        ident = s.launch(self.spec)
        self.assertEqual(ident, tw.make_identity())
        self.assertIs(s.state, sup.SupervisorState.RUNNING)
        self.assertEqual(s.identity, ident)
        self.assertEqual(self.docker.verbs(), ['ps', 'create', 'inspect', 'start', 'inspect'])
        self.assertTrue(all(c[0] == DOCKER_PATH for c in self.bridge.calls))
        verdict = s.stop()
        self.assertTrue(verdict.verified, verdict.reasons)
        self.assertIs(s.state, sup.SupervisorState.STOPPED_VERIFIED)
        with self.assertRaises(AttributeError):
            s.identity = None

    def test_validation_failure_before_any_docker_call(self):
        s = self.make()
        for spec in (tw.make_spec(image_ref='oc2/writer:latest'),
                     tw.make_spec(env=(('API_TOKEN', SENTINEL),)), 'junk', None):
            with self.subTest(spec=type(spec).__name__):
                with self.assertRaises(sup.SupervisorInputError) as ctx:
                    s.launch(spec)
                self.assertNotIn(SENTINEL, exc_texts(ctx.exception))
        with self.assertRaisesRegex(sup.SupervisorInputError, 'key mismatch'):
            s.launch(tw.make_spec(tw.GEN2))
        self.assertEqual(self.docker.calls, [])
        self.assertEqual(self.factory_calls, 0)
        self.assertIs(s.state, sup.SupervisorState.NEW)

    def test_constructor_validation(self):
        for key in (w.WriterSessionKey('x', tw.SANDBOX, tw.GEN), 'key', None):
            with self.assertRaises(sup.SupervisorInputError):
                sup.GuestSupervisor(key, self.factory)
        with self.assertRaises(sup.SupervisorInputError):
            sup.GuestSupervisor(tw.make_key(), None)

    def assert_launch_fails(self, exc_type, verbs=None):
        s = self.make()
        with self.assertRaises(exc_type) as ctx:
            s.launch(self.spec)
        self.assertIs(s.state, sup.SupervisorState.UNVERIFIED)
        self.assertIsNone(s.identity)
        self.assertEqual(self.creates(), min(1, self.creates()))
        if verbs is not None:
            self.assertEqual(self.docker.verbs(), verbs)
        before = list(self.docker.calls)
        for call in (lambda: s.launch(self.spec), s.stop):
            with self.assertRaises(sup.SupervisorStateError):
                call()
        self.assertEqual(self.docker.calls, before)
        self.assertNotIn(SENTINEL, exc_texts(ctx.exception))
        return ctx.exception

    def test_create_failure(self):
        self.docker.queue('create', (125, 'Error: ' + SENTINEL))
        self.assert_launch_fails(sup.DockerCommandError, ['ps', 'create'])

    def test_create_bad_output(self):
        self.docker.queue('create', (0, 'not-an-id'))
        self.assert_launch_fails(sup.DockerOutputError, ['ps', 'create'])

    def test_conflict(self):
        other = tw.make_inspect(tw.make_spec(tw.GEN2), OTHER, 'exited')
        other['Config']['Labels']['dev.oc2.session-generation'] = tw.GEN
        self.docker.existing = [other]
        self.assert_launch_fails(sup.LaunchFailedError)
        self.assertEqual(self.creates(), 0)

    def test_pre_start_inspect_mismatch(self):
        self.docker.queue('inspect', (0, json.dumps([
            tw.bad(tw.make_inspect(self.spec), 'HostConfig', 'NetworkMode', 'bridge')])))
        self.assert_launch_fails(sup.InspectMismatchError, ['ps', 'create', 'inspect'])

    def test_pre_start_id_mismatch(self):
        self.docker.queue('inspect', (0, json.dumps([tw.make_inspect(self.spec, CID2)])))
        self.assert_launch_fails(sup.IdentityMismatchError, ['ps', 'create', 'inspect'])

    def test_start_failure(self):
        self.docker.queue('start', (1, SENTINEL))
        self.assert_launch_fails(sup.DockerCommandError)
        self.assertEqual(self.creates(), 1)
        self.assertEqual(self.docker.verbs().count('start'), 1)

    def test_start_timeout(self):
        self.docker.queue('start', SimTimeout())
        self.assert_launch_fails(sup.DockerTimeoutError)
        self.assertEqual(self.docker.verbs().count('start'), 1)

    def test_post_start_identity_mismatch_no_relaunch(self):
        swapped = tw.make_inspect(self.spec, CID2, 'running')
        self.docker.queue('inspect', (0, json.dumps([tw.make_inspect(self.spec)])),
                          (0, json.dumps([swapped])), (0, json.dumps([swapped])))
        self.assert_launch_fails(sup.IdentityMismatchError)
        self.assertEqual(self.creates(), 1)
        self.assertEqual(self.docker.verbs().count('start'), 1)
        self.assertNotIn('stop', self.docker.verbs())

    def test_post_start_probe_unavailable(self):
        self.probe = tw.FakeProbe(inode=None)
        self.assert_launch_fails(sup.ProbeUnavailableError)
        self.assertEqual(self.creates(), 1)

    def test_factory_must_return_lifecycle(self):
        s = sup.GuestSupervisor(tw.make_key(), lambda spec: object())
        with self.assertRaises(sup.SupervisorInputError):
            s.launch(self.spec)
        self.assertIs(s.state, sup.SupervisorState.UNVERIFIED)

    def test_factory_exception_unverified(self):
        def boom(spec):
            raise RuntimeError(SENTINEL)

        s = sup.GuestSupervisor(tw.make_key(), boom)
        with self.assertRaises(sup.LaunchFailedError) as ctx:
            s.launch(self.spec)
        self.assertIs(s.state, sup.SupervisorState.UNVERIFIED)
        self.assertNotIn(SENTINEL, str(ctx.exception))

    def test_duplicate_launch(self):
        s = self.running()
        before = list(self.docker.calls)
        with self.assertRaises(sup.SupervisorStateError):
            s.launch(self.spec)
        self.assertEqual(self.docker.calls, before)
        self.assertIs(s.state, sup.SupervisorState.RUNNING)

    def test_launch_while_starting_rejected(self):
        s = self.make()
        seen = []

        def reenter():
            try:
                s.launch(self.spec)
            except sup.SupervisorStateError as exc:
                seen.append(exc)

        self.docker.hooks['create'] = reenter
        s.launch(self.spec)
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.creates(), 1)

    def test_busy_lock_rejects_without_blocking(self):
        s = self.make()
        s._lock.acquire()
        try:
            with self.assertRaisesRegex(sup.SupervisorStateError, 'busy'):
                s.launch(self.spec)
        finally:
            s._lock.release()
        self.assertEqual(self.docker.calls, [])
        self.assertIs(s.state, sup.SupervisorState.NEW)


class SupervisorStopTest(SupervisorBase):
    def stop_with(self, observations=None, configure=None):
        s = self.running()
        if observations is not None:
            self.probe.observations = list(observations)
        if configure is not None:
            configure()
        verdict = s.stop()
        expected = (sup.SupervisorState.STOPPED_VERIFIED if verdict.verified
                    else sup.SupervisorState.UNVERIFIED)
        self.assertIs(s.state, expected)
        return s, verdict

    def test_normal_stop(self):
        s, verdict = self.stop_with()
        self.assertTrue(verdict.verified)
        self.assertEqual(self.sleeper.calls, [w.QUIESCE_OBSERVE_S])
        self.assertNotIn('kill', self.docker.verbs())

    def test_stop_timeout_then_kill_by_id(self):
        s, verdict = self.stop_with(configure=lambda: self.docker.queue('stop', SimTimeout()))
        kills = [c for c in self.bridge.calls if c[1] == 'kill']
        self.assertEqual(kills, [[DOCKER_PATH, 'kill', '--signal', 'KILL', CID]])
        self.assertTrue(verdict.verified, verdict.reasons)

    def test_stop_timeout_and_kill_failure(self):
        def configure():
            self.docker.queue('stop', SimTimeout())
            self.docker.queue('kill', (1, ''))

        s, verdict = self.stop_with(configure=configure)
        self.assertFalse(verdict.verified)
        self.assertIs(s.state, sup.SupervisorState.UNVERIFIED)
        self.assertTrue(any('kill failed' in r for r in verdict.reasons))

    def test_remaining_conditions_unverified(self):
        clean = tw.clean_obs()
        cases = {
            'cgroup remaining': w.StopObservation(True, (), (), BOOT),
            'uid process remaining': w.StopObservation(False, (4242,), (), BOOT),
            'rw holder remaining': w.StopObservation(False, (), (OTHER,), BOOT),
            'boot id mismatch': w.StopObservation(False, (), (), tw.GEN2),
            'unknown': w.StopObservation(None, None, None, None),
        }
        for name, obs in cases.items():
            with self.subTest(case=name):
                self.setUp()
                s, verdict = self.stop_with(observations=[clean, obs])
                self.assertFalse(verdict.verified)
                self.assertIs(s.state, sup.SupervisorState.UNVERIFIED)
                with self.assertRaises(sup.SupervisorStateError):
                    s.stop()

    def test_foreign_identity_rejected(self):
        s = self.running()
        before = list(self.docker.calls)
        foreign = (tw.make_identity(CID2),
                   w.WriterIdentity(CID, IMAGE_ID, '2026-11-14T09:09:09Z', INODE, BOOT),
                   w.WriterIdentity(CID, IMAGE_ID, STARTED, INODE, tw.GEN2), 'x')
        for ident in foreign:
            with self.subTest(ident=ident):
                with self.assertRaises(sup.IdentityMismatchError) as ctx:
                    s.stop(ident)
                self.assertLessEqual(len(str(ctx.exception)), 80)
                self.assertNotIn(CID2, str(ctx.exception))
        self.assertEqual(self.docker.calls, before)
        self.assertIs(s.state, sup.SupervisorState.RUNNING)
        self.assertTrue(s.stop(s.identity).verified)

    def test_identity_from_other_session_rejected(self):
        s = self.running()
        other_docker = HookDocker(tw.make_spec(tw.GEN2))
        other = sup.GuestSupervisor(
            tw.make_key(tw.GEN2),
            lambda spec: w.WriterLifecycle(other_docker, tw.FakeProbe(), sleep=tw.Sleeper()))
        other_docker.queue('create', (0, CID2 + '\n'))
        info = tw.make_inspect(tw.make_spec(tw.GEN2), CID2)
        running = tw.make_inspect(tw.make_spec(tw.GEN2), CID2, 'running')
        other_docker.queue('inspect', (0, json.dumps([info])), (0, json.dumps([running])))
        other_ident = other.launch(tw.make_spec(tw.GEN2))
        with self.assertRaises(sup.IdentityMismatchError):
            s.stop(other_ident)
        self.assertIs(s.state, sup.SupervisorState.RUNNING)

    def test_stop_from_wrong_states(self):
        s = self.make()
        with self.assertRaises(sup.SupervisorStateError):
            s.stop()
        s = self.running()
        s.stop()
        before = list(self.docker.calls)
        for call in (s.stop, lambda: s.launch(self.spec)):
            with self.assertRaises(sup.SupervisorStateError):
                call()
        self.assertEqual(self.docker.calls, before)
        self.assertIs(s.state, sup.SupervisorState.STOPPED_VERIFIED)

    def test_stop_while_stopping_rejected(self):
        s = self.running()
        seen = []

        def reenter():
            for call in (s.stop, lambda: s.launch(self.spec)):
                try:
                    call()
                except sup.SupervisorStateError as exc:
                    seen.append(exc)

        self.docker.hooks['stop'] = reenter
        self.assertIs(s.state, sup.SupervisorState.RUNNING)
        verdict = s.stop()
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.docker.verbs().count('stop'), 1)
        self.assertTrue(verdict.verified)

    def test_lifecycle_stop_exception_or_garbage(self):
        for behaviour in (RuntimeError(SENTINEL), 'garbage'):
            with self.subTest(behaviour=type(behaviour).__name__):
                self.setUp()
                s = self.running()

                def fake_stop(identity, behaviour=behaviour):
                    if isinstance(behaviour, Exception):
                        raise behaviour
                    return behaviour

                s._lifecycle.stop = fake_stop
                with self.assertRaises(sup.StopVerificationError) as ctx:
                    s.stop()
                self.assertIs(s.state, sup.SupervisorState.UNVERIFIED)
                self.assertNotIn(SENTINEL, str(ctx.exception))


class EndToEndOfflineTest(unittest.TestCase):
    """CliDockerRunner + GuestHostProbe + WriterLifecycle + GuestSupervisor."""

    def setUp(self):
        self.spec = tw.make_spec()
        self.fs = FakeGuestFs.standard()
        self.docker = HookDocker(self.spec, fs=self.fs)
        self.bridge = BridgeTransport(self.docker)
        self.sleeper = tw.Sleeper()
        factory = sup.guest_lifecycle_factory(runner_for(self.bridge), self.fs, self.sleeper)
        self.sup = sup.GuestSupervisor(tw.make_key(), factory)

    def test_launch_and_docker_only_stop_unverified(self):
        # GuestHostProbe only has Docker-side RW holder evidence, which can not
        # establish kernel-wide absence: the clean stop ends UNVERIFIED.
        ident = self.sup.launch(self.spec)
        self.assertEqual(ident, w.WriterIdentity(CID, IMAGE_ID, STARTED, INODE, BOOT))
        verdict = self.sup.stop()
        self.assertFalse(verdict.verified)
        self.assertEqual(verdict.status, w.STATUS_GUEST_QUIESCENCE_UNVERIFIED)
        self.assertTrue(any('rw mount holders unknown' in r for r in verdict.reasons))
        for reason in verdict.reasons:
            self.assertIn('rw mount holders unknown', reason)
        self.assertIs(self.sup.state, sup.SupervisorState.UNVERIFIED)
        verbs = self.docker.verbs()
        self.assertGreaterEqual(verbs[verbs.index('stop'):].count('ps'), 2)
        with self.assertRaises(sup.SupervisorStateError):
            self.sup.stop()

    def test_sufficient_observation_reaches_stopped_verified(self):
        # Test-only stand-in for an independent sufficient kernel-side RW
        # holder observation (not implemented by GuestHostProbe).  All other
        # observations come from the real GuestHostProbe logic.
        class SufficientProbe(sup.GuestHostProbe):
            def _rw_mount_holders(self):
                docker_side = self._docker_rw_mount_holders()
                return docker_side if docker_side else ()

        def factory(spec):
            probe = SufficientProbe(runner_for(self.bridge), self.fs,
                                    repo_source=spec.repo_source)
            return w.WriterLifecycle(runner_for(self.bridge), probe, sleep=self.sleeper)

        s = sup.GuestSupervisor(tw.make_key(), factory)
        s.launch(self.spec)
        verdict = s.stop()
        self.assertTrue(verdict.verified, verdict.reasons)
        self.assertIs(s.state, sup.SupervisorState.STOPPED_VERIFIED)

    def test_other_rw_holder_blocks_verification(self):
        self.sup.launch(self.spec)
        other = tw.make_inspect(tw.make_spec(tw.GEN2), OTHER, 'running')
        other['Mounts'].append({'Type': 'bind', 'Source': self.spec.repo_source,
                                'Destination': '/src', 'RW': True})
        self.docker.existing = [other]
        verdict = self.sup.stop()
        self.assertFalse(verdict.verified)
        self.assertTrue(any('rw mount holders remain' in r for r in verdict.reasons))
        self.assertIs(self.sup.state, sup.SupervisorState.UNVERIFIED)

    def test_cgroup_left_behind_blocks_verification(self):
        self.sup.launch(self.spec)
        self.docker.hooks['stop'] = lambda: None
        original = self.fs.writer_exit
        self.fs.writer_exit = lambda: (original(), self.fs.dirs.update({SCOPE: INODE}))
        verdict = self.sup.stop()
        self.assertFalse(verdict.verified)
        self.assertTrue(any('cgroup still exists' in r for r in verdict.reasons))

    def test_cgroup_unresolvable_launch_unverified(self):
        self.fs.files['/proc/4242/cgroup'] = f'0::/system.slice/docker-{OTHER}.scope\n'
        with self.assertRaises(sup.ProbeUnavailableError):
            self.sup.launch(self.spec)
        self.assertIs(self.sup.state, sup.SupervisorState.UNVERIFIED)
        self.assertEqual(self.docker.verbs().count('create'), 1)

    def test_secret_env_never_leaks_through_launch_failure(self):
        spec = tw.make_spec(env=(('HOME', SENTINEL),))
        self.docker.spec = spec
        self.docker.queue('create', (1, SENTINEL))
        with self.assertRaises(sup.DockerCommandError) as ctx:
            self.sup.launch(spec)
        self.assertNotIn(SENTINEL, exc_texts(ctx.exception))


# 6 -- API surface / scope ---------------------------------------------------------
class ApiSurfaceTest(unittest.TestCase):
    def test_no_restart_or_recovery_api(self):
        forbidden = ('restart', 'relaunch', 'exec', 'start_existing', 'recover', 'resume',
                     'reuse', 'retry', 'unpause', 'attach', 'reset')
        for obj in (sup, sup.GuestSupervisor, sup.GuestHostProbe, sup.CliDockerRunner):
            for name in dir(obj):
                for frag in forbidden:
                    self.assertNotIn(frag, name.lower(), f'{obj!r} exposes {name}')
        public = {n for n in dir(sup.GuestSupervisor) if not n.startswith('_')}
        self.assertEqual(public, {'launch', 'stop', 'state', 'identity', 'session_key'})
        self.assertEqual({s.value for s in sup.SupervisorState},
                         {'NEW', 'STARTING', 'RUNNING', 'STOPPING', 'STOPPED_VERIFIED',
                          'UNVERIFIED'})

    def test_stopped_verified_docstring(self):
        for doc in (sup.GuestSupervisor.__doc__, sup.__doc__):
            self.assertIn('is a limited Writer-stop verdict', doc)
            self.assertIn('NOT proof of', doc)
            self.assertIn('Git tree immutability', doc)
        self.assertIn('Process-restart Session recovery is NOT implemented',
                      sup.GuestSupervisor.__doc__)

    def test_no_digest_apply_collect_symbols(self):
        for name in dir(sup):
            low = name.lower()
            for frag in ('digest', 'applyauth', 'apply_auth', 'collect', 'relay', 'lease',
                         'receipt'):
                self.assertNotIn(frag, low, name)

    def test_error_hierarchy(self):
        classes = (sup.SupervisorInputError, sup.DockerCommandError, sup.DockerTimeoutError,
                   sup.DockerOutputError, sup.DockerCommandRejected,
                   sup.InspectMismatchError, sup.IdentityMismatchError,
                   sup.ProbeUnavailableError, sup.StopVerificationError,
                   sup.SupervisorStateError, sup.LaunchFailedError,
                   sup.TransportReapError)
        self.assertEqual(len(set(classes)), len(classes))
        self.assertTrue(issubclass(sup.TransportReapError, sup.DockerCommandError))
        for cls in classes:
            self.assertTrue(issubclass(cls, sup.SupervisorError))
            self.assertTrue(issubclass(cls, w.WriterError))


# 7 -- Regression ------------------------------------------------------------------
class RegressionTest(unittest.TestCase):
    def test_writer_blob_unchanged(self):
        data = (SCRIPTS / 'oc2_writer.py').read_bytes()
        blob = hashlib.sha1(b'blob %d\x00' % len(data) + data).hexdigest()
        self.assertEqual(blob, WRITER_BLOB)

    def test_runtime_does_not_import_supervisor(self):
        for name in ('oc2.py', 'oc2_guest.py', 'oc2_session.py', 'oc2_writer.py'):
            with self.subTest(name=name):
                source = (SCRIPTS / name).read_text(encoding='utf-8')
                self.assertNotIn('oc2_supervisor', source)

    def test_supervisor_does_not_reference_apm_or_launcher(self):
        source = (SCRIPTS / 'oc2_supervisor.py').read_text(encoding='utf-8')
        for frag in ('apm.yml', 'apm.yaml', 'import oc2\n', 'oc2_guest', 'oc2_session',
                     'sbx'):
            self.assertNotIn(frag, source)

    def test_sources_are_printable_ascii(self):
        for path in (SCRIPTS / 'oc2_supervisor.py', TESTS / 'test_oc2_supervisor.py'):
            with self.subTest(path=path.name):
                data = path.read_bytes()
                bad_chars = [b for b in data if not (0x20 <= b <= 0x7E or b == 0x0A)]
                self.assertEqual(bad_chars, [])


if __name__ == '__main__':
    unittest.main()

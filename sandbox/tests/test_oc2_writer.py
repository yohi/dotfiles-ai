"""Offline tests for the OC2 Alternative A Writer lifecycle foundation.

No docker, sbx, network, sandbox, credential, Provider or real sleep is used.
Docker is replaced by FakeDocker returning canned JSON.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import unittest
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.scripts import oc2_writer as writer_types

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    if spec is None or spec.loader is None:
        raise ImportError(f'could not load module: {name}')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


w = load('oc2_writer')

WS = 'a' * 32
SANDBOX = '0f8e9a52-3b1c-11ef-9a7d-0242ac120002'
GEN = '4b2f3c1d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'
GEN2 = '9a8b7c6d-5e4f-4321-8fed-cba987654321'
DIGEST = 'b' * 64
IMAGE_REF = 'oc2/writer@sha256:' + DIGEST
IMAGE_ID = 'sha256:' + 'c' * 64
CID = 'd' * 64
CID2 = 'e' * 64
OTHER = 'f' * 64
STARTED = '2026-11-14T01:02:03.456789Z'
BOOT = '11111111-2222-4333-8444-555555555555'
SENTINEL = 'sk-SENTINEL-DO-NOT-LEAK-7f3a'


def make_key(gen: str = GEN) -> writer_types.WriterSessionKey:
    key: writer_types.WriterSessionKey = w.WriterSessionKey(WS, SANDBOX, gen)
    return key


def make_spec(gen: str = GEN, **overrides) -> writer_types.WriterSpec:
    key = make_key(gen)
    fields = dict(
        key=key,
        image_ref=IMAGE_REF,
        repo_source=f'{w.GUEST_SESSION_ROOT}/{gen}/repo',
        command=('opencode',),
        env=(('HOME', '/home/writer'), ('TERM', 'xterm-256color')),
        tty=False,
    )
    fields.update(overrides)
    spec: writer_types.WriterSpec = w.WriterSpec(**fields)
    return spec


def make_inspect(
    spec: writer_types.WriterSpec, cid: str = CID, status: str = 'created'
) -> dict:
    running = status == 'running'
    return {
        'Id': cid,
        'Name': '/' + w.writer_container_name(spec.key),
        'Image': IMAGE_ID,
        'RestartCount': 0,
        'State': {
            'Status': status,
            'Running': running,
            'Pid': 4242 if running else 0,
            'StartedAt': STARTED if status != 'created' else w._UNSET_TIME,
        },
        'Config': {
            'Image': spec.image_ref,
            'User': '10001:10001',
            'Cmd': list(spec.command),
            'WorkingDir': '/workspace',
            'Tty': spec.tty,
            'Labels': dict(w.writer_labels(spec.key)),
            'Env': [f'{n}={v}' for n, v in spec.env]
            + ['PATH=/usr/local/bin:/usr/bin:/bin'],
        },
        'HostConfig': {
            'Privileged': False,
            'CapDrop': ['ALL'],
            'CapAdd': None,
            'SecurityOpt': ['no-new-privileges'],
            'ReadonlyRootfs': True,
            'PidsLimit': 256,
            'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
            'NetworkMode': 'none',
            'PidMode': '',
            'UsernsMode': '',
            'IpcMode': 'private',
            'CgroupnsMode': 'private',
            'Devices': [],
            'GroupAdd': None,
            'ExtraHosts': None,
            'Dns': [],
            'PortBindings': {},
            'AutoRemove': False,
            'Memory': 6 * 1024 ** 3,
            'Binds': [f'{spec.repo_source}:/workspace:rw'],
            'Tmpfs': dict(w.EXPECTED_TMPFS),
        },
        'Mounts': [{
            'Type': 'bind', 'Source': spec.repo_source, 'Destination': '/workspace',
            'Mode': 'rw', 'RW': True, 'Propagation': 'rprivate',
        }],
        'NetworkSettings': {'Networks': {'none': {}}},
    }


def stopped_inspect(spec: writer_types.WriterSpec, cid: str = CID) -> dict:
    info = make_inspect(spec, cid, 'exited')
    info['State']['StartedAt'] = STARTED
    return info


def make_identity(cid: str = CID) -> writer_types.WriterIdentity:
    identity: writer_types.WriterIdentity = w.WriterIdentity(
        cid, IMAGE_ID, STARTED, 987654, BOOT
    )
    return identity


def clean_obs() -> writer_types.StopObservation:
    observation: writer_types.StopObservation = w.StopObservation(False, (), (), BOOT)
    return observation


class FakeDocker:
    """Scriptable DockerRunner.

    ``responses`` maps a verb ('ps', 'create', 'inspect', 'start', 'stop',
    'kill') to a list of queued results; each result is (rc, stdout) or an
    Exception instance.  When the queue is empty the default is used.
    """

    def __init__(self, spec: writer_types.WriterSpec, existing=None):
        self.spec = spec
        self.calls: list[list[str]] = []
        self.responses: dict[str, list] = {}
        self.existing = list(existing or [])
        self.state = 'none'

    def queue(self, verb: str, *results) -> None:
        self.responses.setdefault(verb, []).extend(results)

    def verbs(self) -> list[str]:
        return [c[1] for c in self.calls]

    def run(self, argv, *, timeout):
        argv = list(argv)
        assert isinstance(timeout, int) and timeout > 0
        self.calls.append(argv)
        verb = argv[1]
        queued = self.responses.get(verb)
        if queued:
            result = queued.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        if verb == 'ps':
            return 0, ''.join(i['Id'] + '\n' for i in self.existing)
        if verb == 'create':
            self.state = 'created'
            return 0, CID + '\n'
        if verb == 'start':
            self.state = 'running'
            return 0, CID + '\n'
        if verb in ('stop', 'kill'):
            self.state = 'exited'
            return 0, CID + '\n'
        if verb == 'inspect':
            target = argv[-1]
            for item in self.existing:
                if item['Id'] == target:
                    return 0, json.dumps([item])
            if self.state == 'exited':
                return 0, json.dumps([stopped_inspect(self.spec)])
            return 0, json.dumps([make_inspect(self.spec, CID, self.state)])
        raise AssertionError('unexpected argv: ' + repr(argv))


class FakeProbe:
    def __init__(self, inode=987654, boot=BOOT, observations=None):
        self.inode = inode
        self.boot = boot
        self.observations = list(observations or [clean_obs(), clean_obs()])
        self.calls: list[str] = []

    def cgroup_inode(self, cid):
        self.calls.append('cgroup_inode')
        if isinstance(self.inode, Exception):
            raise self.inode
        return self.inode

    def boot_id(self):
        self.calls.append('boot_id')
        return self.boot

    def observe(self, identity):
        self.calls.append('observe')
        item = self.observations.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Sleeper:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds):
        self.calls.append(seconds)


def lifecycle(docker, probe=None, sleeper=None):
    return w.WriterLifecycle(docker, probe or FakeProbe(), sleep=sleeper or Sleeper())


def bad(info: dict, *path_and_value):
    """Return a deep copy of ``info`` with path set to value (or deleted)."""
    *path, value = path_and_value
    out = copy.deepcopy(info)
    cur = out
    for part in path[:-1]:
        cur = cur[part]
    if value is DELETE:
        del cur[path[-1]]
    else:
        cur[path[-1]] = value
    return out


DELETE = object()


class InspectAssertMixin(unittest.TestCase):
    def assertRejected(self, info, pattern, spec=None):
        with self.assertRaisesRegex(w.WriterError, pattern):
            w.validate_writer_inspect(info, spec or make_spec())


# 1 ------------------------------------------------------------------------------
class HappyPathTest(unittest.TestCase):
    def test_exact_create_argv(self):
        spec = make_spec()
        name = 'oc2-writer-' + WS[:12] + '-' + GEN.replace('-', '')
        expected = [
            'docker', 'create',
            '--name', name,
            '--user', '10001:10001',
            '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges',
            '--read-only',
            '--pids-limit', '256',
            '--memory', '6g',
            '--restart', 'no',
            '--network', 'none',
            '--ipc', 'private',
            '--cgroupns', 'private',
            '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=64m,uid=10001,gid=10001,mode=0700',
            '--tmpfs',
            '/home/writer:rw,exec,nosuid,nodev,size=1g,uid=10001,gid=10001,mode=0700',
            '-v', f'{w.GUEST_SESSION_ROOT}/{GEN}/repo:/workspace:rw',
            '-w', '/workspace',
            '--label', 'dev.oc2.schema=dotfiles-ai/oc2-writer/v1',
            '--label', 'dev.oc2.role=writer',
            '--label', 'dev.oc2.workspace-id=' + WS,
            '--label', 'dev.oc2.sandbox-id=' + SANDBOX,
            '--label', 'dev.oc2.session-generation=' + GEN,
            '-e', 'HOME=/home/writer',
            '-e', 'TERM=xterm-256color',
            IMAGE_REF, 'opencode',
        ]
        self.assertEqual(w.build_create_argv(spec), expected)
        self.assertEqual(expected.count('-v'), 1)
        for forbidden in ('--rm', '--privileged', '--pid', 'host', '-t'):
            self.assertNotIn(forbidden, expected)
        self.assertFalse(any('docker.sock' in a for a in expected))

    def test_tty_flag_only_when_requested(self):
        argv = w.build_create_argv(make_spec(tty=True))
        self.assertEqual(argv[argv.index(IMAGE_REF) - 1], '-t')

    def test_launch_call_order_and_identity(self):
        docker = FakeDocker(make_spec())
        ident = lifecycle(docker).launch(make_spec())
        self.assertEqual(docker.verbs(), ['ps', 'create', 'inspect', 'start', 'inspect'])
        self.assertEqual(ident, w.WriterIdentity(CID, IMAGE_ID, STARTED, 987654, BOOT))

    def test_other_argv_builders(self):
        self.assertEqual(w.build_start_argv(CID), ['docker', 'start', CID])
        self.assertEqual(w.build_stop_argv(CID), ['docker', 'stop', '--timeout', '15', CID])
        self.assertEqual(w.build_kill_argv(CID), ['docker', 'kill', '--signal', 'KILL', CID])
        for bad_id in ('', 'oc2-writer-x', '-f', '--all', CID[:12], CID.upper(), None):
            with self.subTest(bad_id=bad_id):
                for builder in (w.build_start_argv, w.build_stop_argv, w.build_kill_argv):
                    with self.assertRaises(w.WriterError):
                        builder(bad_id)

    def test_labels_and_policy_constants(self):
        self.assertEqual(len(w.writer_labels(make_key())), 5)
        self.assertEqual((w.WRITER_UID, w.WRITER_GID, w.PIDS_LIMIT, w.MEMORY,
                          w.STOP_TIMEOUT_S, w.QUIESCE_OBSERVE_S),
                         (10001, 10001, 256, '6g', 15, 20))
        self.assertEqual(w.SCHEMA, 'dotfiles-ai/oc2-writer/v1')

    def test_valid_inspect_accepted(self):
        w.validate_writer_inspect(make_inspect(make_spec()), make_spec())
        alt = bad(make_inspect(make_spec()), 'HostConfig', 'SecurityOpt',
                  ['no-new-privileges:true'])
        w.validate_writer_inspect(alt, make_spec())

    def test_happy_stop_verified(self):
        docker = FakeDocker(make_spec())
        docker.state = 'running'
        sleeper = Sleeper()
        verdict = lifecycle(docker, sleeper=sleeper).stop(make_identity())
        self.assertEqual(verdict.status, 'STOPPED_VERIFIED', verdict.reasons)
        self.assertEqual(verdict.reasons, ())
        self.assertEqual(sleeper.calls, [20])
        self.assertEqual(docker.verbs(), ['inspect', 'stop', 'inspect', 'inspect'])
        self.assertNotIn('kill', docker.verbs())


# 2 ------------------------------------------------------------------------------
class UserTest(InspectAssertMixin, unittest.TestCase):
    def test_root_or_invalid_user_rejected(self):
        for user in ('0', 'root', '', '10001', '0:0', '10001:0', 'root:root'):
            with self.subTest(user=user):
                self.assertRejected(bad(make_inspect(make_spec()), 'Config', 'User', user),
                                    'Config.User')

    def test_missing_user_rejected(self):
        self.assertRejected(bad(make_inspect(make_spec()), 'Config', 'User', DELETE),
                            'missing Config.User')


# 3 ------------------------------------------------------------------------------
class CapabilityTest(InspectAssertMixin, unittest.TestCase):
    def test_capabilities_privileged_securityopt(self):
        base = make_inspect(make_spec())
        cases = [
            (('HostConfig', 'CapAdd', ['SYS_ADMIN']), 'CapAdd'),
            (('HostConfig', 'CapDrop', ['NET_RAW']), 'CapDrop'),
            (('HostConfig', 'CapDrop', []), 'CapDrop'),
            (('HostConfig', 'CapDrop', None), 'CapDrop'),
            (('HostConfig', 'Privileged', True), 'Privileged'),
            (('HostConfig', 'Privileged', None), 'Privileged'),
            (('HostConfig', 'SecurityOpt', ['no-new-privileges', 'seccomp=unconfined']),
             'SecurityOpt'),
            (('HostConfig', 'SecurityOpt', ['no-new-privileges', 'apparmor=unconfined']),
             'SecurityOpt'),
            (('HostConfig', 'SecurityOpt', []), 'SecurityOpt'),
            (('HostConfig', 'SecurityOpt', None), 'SecurityOpt'),
            (('HostConfig', 'SecurityOpt', ['no-new-privileges:false']), 'SecurityOpt'),
            (('HostConfig', 'ReadonlyRootfs', False), 'ReadonlyRootfs'),
            (('HostConfig', 'PidsLimit', 0), 'PidsLimit'),
            (('HostConfig', 'Memory', 0), 'Memory'),
            (('HostConfig', 'AutoRemove', True), 'AutoRemove'),
            (('HostConfig', 'Devices', [{'PathOnHost': '/dev/kvm'}]), 'Devices'),
            (('HostConfig', 'GroupAdd', ['docker']), 'GroupAdd'),
            (('HostConfig', 'PidMode', 'host'), 'PidMode'),
            (('HostConfig', 'UsernsMode', 'host'), 'UsernsMode'),
            (('HostConfig', 'IpcMode', 'host'), 'IpcMode'),
            (('HostConfig', 'CgroupnsMode', 'host'), 'CgroupnsMode'),
        ]
        for (*path, value), pattern in cases:
            with self.subTest(path=path, value=value):
                self.assertRejected(bad(base, *path, value), pattern)

    def test_missing_security_fields_rejected(self):
        base = make_inspect(make_spec())
        for field in ('CapAdd', 'CapDrop', 'SecurityOpt', 'Privileged', 'PidMode',
                      'Devices', 'Memory', 'RestartPolicy', 'Tmpfs', 'Binds'):
            with self.subTest(field=field):
                self.assertRejected(bad(base, 'HostConfig', field, DELETE), 'missing')
        self.assertRejected(bad(base, 'HostConfig', DELETE), 'missing')


# 4 ------------------------------------------------------------------------------
class MountTest(InspectAssertMixin, unittest.TestCase):
    def _with_extra_mount(self, source, dest='/x'):
        info = make_inspect(make_spec())
        info['Mounts'].append({'Type': 'bind', 'Source': source, 'Destination': dest,
                               'RW': True})
        info['HostConfig']['Binds'].append(f'{source}:{dest}')
        return info

    def test_socket_and_run_binds_rejected(self):
        for source in ('/var/run/docker.sock', '/run/containerd/containerd.sock',
                       '/run/podman/podman.sock', '/run', '/var/run', '/run/user/1000'):
            with self.subTest(source=source):
                self.assertRejected(self._with_extra_mount(source), 'forbidden')

    def test_extra_bind_rejected(self):
        self.assertRejected(self._with_extra_mount('/home/agent/other'),
                            'exactly one rw bind')

    def test_bind_must_be_rw_repo(self):
        base = make_inspect(make_spec())
        self.assertRejected(bad(base, 'Mounts', 0, 'RW', False), 'exactly one rw bind')
        self.assertRejected(bad(base, 'Mounts', 0, 'Source', '/home/agent'),
                            'exactly one rw bind')
        self.assertRejected(bad(base, 'Mounts', 0, 'Propagation', 'rshared'),
                            'exactly one rw bind')
        self.assertRejected(bad(base, 'Mounts', DELETE), 'missing Mounts')
        self.assertRejected(bad(base, 'HostConfig', 'Mounts',
                                [{'Type': 'volume', 'Target': '/v'}]), 'HostConfig.Mounts')

    def test_tmpfs_must_match(self):
        base = make_inspect(make_spec())
        self.assertRejected(bad(base, 'HostConfig', 'Tmpfs', {'/tmp': 'rw'}), 'Tmpfs')
        extra = dict(w.EXPECTED_TMPFS, **{'/run': 'rw'})
        self.assertRejected(bad(base, 'HostConfig', 'Tmpfs', extra), 'Tmpfs')
        self.assertRejected(bad(base, 'HostConfig', 'Tmpfs', None), 'Tmpfs')


# 5 ------------------------------------------------------------------------------
class NetworkTest(InspectAssertMixin, unittest.TestCase):
    def test_network_modes_rejected(self):
        for mode in ('bridge', 'host', 'container:' + OTHER, 'default', ''):
            with self.subTest(mode=mode):
                self.assertRejected(
                    bad(make_inspect(make_spec()), 'HostConfig', 'NetworkMode', mode),
                    'NetworkMode')

    def test_dns_hosts_ports_rejected(self):
        base = make_inspect(make_spec())
        for field, value in (('Dns', ['1.1.1.1']), ('ExtraHosts', ['h:10.0.0.1']),
                             ('PortBindings', {'80/tcp': [{'HostPort': '8080'}]})):
            with self.subTest(field=field):
                self.assertRejected(bad(base, 'HostConfig', field, value), field)

    def test_attached_network_rejected(self):
        self.assertRejected(bad(make_inspect(make_spec()), 'NetworkSettings', 'Networks',
                                {'bridge': {}}), 'Networks')


# 6 ------------------------------------------------------------------------------
class RestartTest(InspectAssertMixin, unittest.TestCase):
    def test_restart_policies_rejected_on_inspect(self):
        for name in ('always', 'unless-stopped', 'on-failure'):
            with self.subTest(name=name):
                self.assertRejected(
                    bad(make_inspect(make_spec()), 'HostConfig', 'RestartPolicy',
                        {'Name': name, 'MaximumRetryCount': 0}), 'RestartPolicy')
        self.assertRejected(
            bad(make_inspect(make_spec()), 'HostConfig', 'RestartPolicy',
                {'Name': 'no', 'MaximumRetryCount': 3}), 'MaximumRetryCount')

    def _verdict(self, after):
        spec = make_spec()
        return w.verify_writer_stopped(make_identity(), stopped_inspect(spec), after,
                                       clean_obs(), clean_obs())

    def test_restart_after_stop_unverified(self):
        spec = make_spec()
        cases = {
            'RestartCount': bad(stopped_inspect(spec), 'RestartCount', 1),
            'StartedAt changed': bad(stopped_inspect(spec), 'State', 'StartedAt',
                                     '2026-11-14T09:09:09Z'),
            'Running is not false': bad(stopped_inspect(spec), 'State', 'Running', True),
            'Status is not exited': bad(stopped_inspect(spec), 'State', 'Status',
                                        'restarting'),
            'Pid is not 0': bad(stopped_inspect(spec), 'State', 'Pid', 77),
            'RestartPolicy is not no': bad(stopped_inspect(spec), 'HostConfig',
                                           'RestartPolicy', {'Name': 'always'}),
        }
        for reason, after in cases.items():
            with self.subTest(reason=reason):
                verdict = self._verdict(after)
                self.assertEqual(verdict.status, 'GUEST_QUIESCENCE_UNVERIFIED')
                self.assertTrue(any(reason in r for r in verdict.reasons), verdict.reasons)

    def test_baseline_verified(self):
        self.assertEqual(self._verdict(stopped_inspect(make_spec())).status,
                         'STOPPED_VERIFIED')


# 7 ------------------------------------------------------------------------------
class IdentityMismatchTest(InspectAssertMixin, unittest.TestCase):
    def test_label_mismatch_each(self):
        for label in ('dev.oc2.workspace-id', 'dev.oc2.sandbox-id',
                      'dev.oc2.session-generation'):
            with self.subTest(label=label):
                self.assertRejected(
                    bad(make_inspect(make_spec()), 'Config', 'Labels', label, 'x'),
                    'Labels')
        self.assertRejected(bad(make_inspect(make_spec()), 'Config', 'Labels',
                                'dev.oc2.extra', 'x'), 'Labels')
        self.assertRejected(bad(make_inspect(make_spec()), 'Config', 'Labels',
                                'dev.oc2.role', DELETE), 'Labels')

    def test_image_labels_tolerated(self):
        w.validate_writer_inspect(
            bad(make_inspect(make_spec()), 'Config', 'Labels',
                'org.opencontainers.image.source', 'x'), make_spec())

    def test_name_and_image_mismatch(self):
        base = make_inspect(make_spec())
        self.assertRejected(bad(base, 'Name', '/oc2-writer-other'), 'Name')
        w.validate_writer_inspect(bad(base, 'Name', base['Name'][1:]), make_spec())
        self.assertRejected(bad(base, 'Config', 'Image', 'oc2/writer@sha256:' + 'e' * 64),
                            'Config.Image')
        self.assertRejected(bad(base, 'Config', 'Image', 'oc2/writer:latest'),
                            'Config.Image')
        self.assertRejected(bad(base, 'Image', 'oc2/writer'), 'Image id')
        self.assertRejected(bad(base, 'Id', 'abc'), 'Id')

    def test_id_after_stop_and_boot_id(self):
        spec = make_spec()
        v = w.verify_writer_stopped(make_identity(), stopped_inspect(spec, CID2),
                                    stopped_inspect(spec), clean_obs(), clean_obs())
        self.assertFalse(v.verified)
        self.assertTrue(any('Id changed' in r for r in v.reasons))
        other_boot = w.StopObservation(False, (), (), 'another-boot')
        v = w.verify_writer_stopped(make_identity(), stopped_inspect(spec),
                                    stopped_inspect(spec), clean_obs(), other_boot)
        self.assertFalse(v.verified)
        self.assertTrue(any('boot id changed' in r for r in v.reasons))
        v = w.verify_writer_stopped(make_identity(), stopped_inspect(spec),
                                    bad(stopped_inspect(spec), 'Image', 'sha256:' + '9' * 64),
                                    clean_obs(), clean_obs())
        self.assertFalse(v.verified)

    def test_post_start_identity_mismatch_not_returned(self):
        spec = make_spec()
        docker = FakeDocker(spec)
        swapped = make_inspect(spec, CID2, 'running')
        docker.queue('inspect', (0, json.dumps([make_inspect(spec)])),
                     (0, json.dumps([swapped])), (0, json.dumps([swapped])))
        with self.assertRaisesRegex(w.WriterError, 'indeterminate'):
            lifecycle(docker).launch(spec)
        self.assertNotIn('stop', docker.verbs())
        self.assertNotIn('kill', docker.verbs())

    def test_post_start_validation_failure_stops_confirmed_id(self):
        spec = make_spec()
        docker = FakeDocker(spec)
        priv = bad(make_inspect(spec, CID, 'running'), 'HostConfig', 'Privileged', True)
        docker.queue('inspect', (0, json.dumps([make_inspect(spec)])),
                     (0, json.dumps([priv])))
        with self.assertRaisesRegex(w.WriterError, 'not usable'):
            lifecycle(docker).launch(spec)
        self.assertEqual(docker.verbs(),
                         ['ps', 'create', 'inspect', 'start', 'inspect', 'inspect', 'stop'])
        self.assertEqual(docker.calls[-1][-1], CID)

    def test_post_start_probe_failure_not_returned(self):
        spec = make_spec()
        for probe in (FakeProbe(inode=None), FakeProbe(boot=None),
                      FakeProbe(inode=RuntimeError('boom'))):
            with self.subTest(probe=probe.inode):
                docker = FakeDocker(spec)
                with self.assertRaises(w.WriterError):
                    lifecycle(docker, probe).launch(spec)
                self.assertIn('stop', docker.verbs())


# 8 ------------------------------------------------------------------------------
class ConflictTest(unittest.TestCase):
    def _assert_rejected_before_create(self, existing, pattern):
        spec = make_spec()
        docker = FakeDocker(spec, existing=[existing])
        with self.assertRaisesRegex(w.WriterError, pattern):
            lifecycle(docker).launch(spec)
        self.assertNotIn('create', docker.verbs())
        self.assertNotIn('start', docker.verbs())

    def test_same_name_running_and_exited(self):
        for status in ('running', 'exited'):
            with self.subTest(status=status):
                other = make_inspect(make_spec(GEN2), OTHER, status)
                other['Name'] = '/' + w.writer_container_name(make_key())
                self._assert_rejected_before_create(other, 'same name')

    def test_same_generation_label(self):
        other = make_inspect(make_spec(GEN2), OTHER, 'exited')
        other['Config']['Labels']['dev.oc2.session-generation'] = GEN
        self._assert_rejected_before_create(other, 'same session generation')

    def test_same_repo_rw_by_running_container(self):
        other = make_inspect(make_spec(GEN2), OTHER, 'running')
        other['Name'] = '/unrelated'
        other['Config']['Labels'] = {}
        other['Mounts'] = [{'Type': 'bind', 'Source': make_spec().repo_source,
                            'Destination': '/src', 'RW': True}]
        self._assert_rejected_before_create(other, 'bound RW')

    def test_unrelated_container_allowed(self):
        other = make_inspect(make_spec(GEN2), OTHER, 'exited')
        w.check_no_conflict([other], make_spec())

    def test_malformed_existing_fails_closed(self):
        with self.assertRaises(w.WriterError):
            w.check_no_conflict([{'Name': '/x'}], make_spec())
        with self.assertRaises(w.WriterError):
            w.check_no_conflict(['junk'], make_spec())


# 9 ------------------------------------------------------------------------------
class FailClosedTest(unittest.TestCase):
    def _running_docker(self):
        docker = FakeDocker(make_spec())
        docker.state = 'running'
        running = make_inspect(make_spec(), CID, 'running')
        running['State']['StartedAt'] = STARTED
        docker.queue('inspect', (0, json.dumps([running])))
        return docker

    def test_none_observation_fields(self):
        spec = make_spec()
        for field in ('cgroup_exists', 'writer_uid_pids', 'rw_mount_holders', 'boot_id'):
            for which in (0, 1):
                with self.subTest(field=field, which=which):
                    obs = [clean_obs(), clean_obs()]
                    obs[which] = w.StopObservation(**{**obs[which].__dict__, field: None})
                    v = w.verify_writer_stopped(make_identity(), stopped_inspect(spec),
                                                stopped_inspect(spec), obs[0], obs[1])
                    self.assertEqual(v.status, 'GUEST_QUIESCENCE_UNVERIFIED')
                    self.assertTrue(v.reasons)

    def test_remaining_cgroup_pids_holders(self):
        spec = make_spec()
        for obs in (w.StopObservation(True, (), (), BOOT),
                    w.StopObservation(False, (1234,), (), BOOT),
                    w.StopObservation(False, (), ('oc2-other',), BOOT)):
            with self.subTest(obs=obs):
                v = w.verify_writer_stopped(make_identity(), stopped_inspect(spec),
                                            stopped_inspect(spec), clean_obs(), obs)
                self.assertFalse(v.verified)

    def test_none_inputs_and_missing_keys(self):
        spec = make_spec()
        for args in ((None, stopped_inspect(spec), clean_obs(), clean_obs()),
                     (stopped_inspect(spec), None, clean_obs(), clean_obs()),
                     (stopped_inspect(spec), stopped_inspect(spec), None, clean_obs()),
                     (stopped_inspect(spec), stopped_inspect(spec), clean_obs(), None),
                     (bad(stopped_inspect(spec), 'State', 'Pid', DELETE),
                      stopped_inspect(spec), clean_obs(), clean_obs()),
                     (bad(stopped_inspect(spec), 'RestartCount', DELETE),
                      stopped_inspect(spec), clean_obs(), clean_obs())):
            v = w.verify_writer_stopped(make_identity(), *args)
            self.assertEqual(v.status, 'GUEST_QUIESCENCE_UNVERIFIED')
        self.assertFalse(w.verify_writer_stopped(None, None, None, None, None).verified)

    def test_pre_stop_inspect_failure(self):
        docker = FakeDocker(make_spec())
        docker.queue('inspect', (1, ''))
        v = lifecycle(docker).stop(make_identity())
        self.assertFalse(v.verified)
        self.assertNotIn('stop', docker.verbs())
        self.assertNotIn('kill', docker.verbs())

    def test_post_stop_inspect_failure(self):
        docker = self._running_docker()
        docker.queue('inspect', RuntimeError('timeout'))
        v = lifecycle(docker).stop(make_identity())
        self.assertFalse(v.verified)
        self.assertTrue(any('inspect failed' in r for r in v.reasons))

    def test_stop_and_kill_failure(self):
        docker = self._running_docker()
        docker.queue('stop', (1, ''))
        docker.queue('kill', RuntimeError('kill timeout'))
        v = lifecycle(docker).stop(make_identity())
        self.assertFalse(v.verified)
        self.assertIn('kill', docker.verbs())
        self.assertTrue(any('kill failed' in r for r in v.reasons))

    def test_stop_failure_then_kill_by_id(self):
        docker = self._running_docker()
        docker.queue('stop', TimeoutError('stop timeout'))
        v = lifecycle(docker).stop(make_identity())
        kill = [c for c in docker.calls if c[1] == 'kill']
        self.assertEqual(kill, [['docker', 'kill', '--signal', 'KILL', CID]])
        self.assertEqual(v.status, 'STOPPED_VERIFIED', v.reasons)

    def test_stop_timeout_then_swapped_container_no_kill(self):
        docker = self._running_docker()
        docker.queue('stop', TimeoutError('stop timeout'))
        swapped = make_inspect(make_spec(), CID2, 'running')
        docker.queue('inspect', (0, json.dumps([swapped])))
        v = lifecycle(docker).stop(make_identity())
        self.assertFalse(v.verified)
        self.assertNotIn('kill', docker.verbs())

    def test_pre_stop_identity_mismatch_no_stop(self):
        docker = FakeDocker(make_spec())
        restarted = make_inspect(make_spec(), CID, 'running')
        restarted['State']['StartedAt'] = '2026-11-14T05:05:05Z'
        docker.queue('inspect', (0, json.dumps([restarted])))
        v = lifecycle(docker).stop(make_identity())
        self.assertFalse(v.verified)
        self.assertEqual(docker.verbs(), ['inspect'])

    def test_malformed_json(self):
        for payload in ('not json', '[]', '{}', '[1]', json.dumps([{}, {}])):
            with self.subTest(payload=payload):
                with self.assertRaises(w.WriterError):
                    w.parse_inspect_output(payload)
        docker = self._running_docker()
        docker.queue('inspect', (0, '{broken'))
        self.assertFalse(lifecycle(docker).stop(make_identity()).verified)

    def test_probe_exception_and_none(self):
        for observations in ([RuntimeError('probe'), clean_obs()],
                             [clean_obs(), RuntimeError('probe')],
                             [None, clean_obs()],
                             [clean_obs(), w.StopObservation(None, None, None, None)]):
            with self.subTest(observations=observations):
                docker = self._running_docker()
                v = lifecycle(docker, FakeProbe(observations=observations)).stop(
                    make_identity())
                self.assertEqual(v.status, 'GUEST_QUIESCENCE_UNVERIFIED')
                self.assertTrue(v.reasons)

    def test_create_ok_inspect_fails_start_not_called(self):
        spec = make_spec()
        for failure in ((1, ''), (0, 'garbage'), RuntimeError('x')):
            with self.subTest(failure=failure):
                docker = FakeDocker(spec)
                docker.queue('inspect', failure)
                with self.assertRaises(w.WriterError):
                    lifecycle(docker).launch(spec)
                self.assertEqual(docker.verbs(), ['ps', 'create', 'inspect'])

    def test_pre_start_invalid_config_not_started_not_removed(self):
        spec = make_spec()
        docker = FakeDocker(spec)
        docker.queue('inspect', (0, json.dumps([
            bad(make_inspect(spec), 'HostConfig', 'NetworkMode', 'bridge')])))
        with self.assertRaises(w.WriterError):
            lifecycle(docker).launch(spec)
        self.assertEqual(docker.verbs(), ['ps', 'create', 'inspect'])

    def test_create_failure_nothing_else(self):
        spec = make_spec()
        for failure in ((125, ''), (0, ''), (0, 'not-an-id')):
            with self.subTest(failure=failure):
                docker = FakeDocker(spec)
                docker.queue('create', failure)
                with self.assertRaises(w.WriterError):
                    lifecycle(docker).launch(spec)
                self.assertEqual(docker.verbs(), ['ps', 'create'])

    def test_list_failure_blocks_create(self):
        docker = FakeDocker(make_spec())
        docker.queue('ps', (1, ''))
        with self.assertRaises(w.WriterError):
            lifecycle(docker).launch(make_spec())
        self.assertEqual(docker.verbs(), ['ps'])

    def test_verdict_invariants(self):
        with self.assertRaises(w.WriterError):
            w.StopVerdict('STOPPED_VERIFIED', ('x',))
        with self.assertRaises(w.WriterError):
            w.StopVerdict('GUEST_QUIESCENCE_UNVERIFIED', ())
        with self.assertRaises(w.WriterError):
            w.StopVerdict('OK')

    def test_identity_missing_pieces(self):
        running = make_inspect(make_spec(), CID, 'running')
        self.assertEqual(w.capture_identity(running, FakeProbe()).cgroup_inode, 987654)
        for info, probe in ((bad(running, 'Id', DELETE), FakeProbe()),
                            (bad(running, 'Image', None), FakeProbe()),
                            (bad(running, 'State', 'StartedAt', ''), FakeProbe()),
                            (running, FakeProbe(inode=0)),
                            (running, FakeProbe(inode=True)),
                            (running, FakeProbe(boot=''))):
            with self.assertRaises(w.WriterError):
                w.capture_identity(info, probe)


# 10 -----------------------------------------------------------------------------
class SpecValidationTest(unittest.TestCase):
    def test_image_digest_required(self):
        for ref in ('oc2/writer:latest', 'oc2/writer', 'oc2/writer@sha256:' + 'b' * 63,
                    'oc2/writer@sha256:' + 'B' * 64, '-oc2@sha256:' + DIGEST,
                    'oc2/writer@sha512:' + DIGEST, ''):
            with self.subTest(ref=ref):
                with self.assertRaisesRegex(w.WriterError, 'image_ref'):
                    w.validate_writer_spec(make_spec(image_ref=ref))
        w.validate_writer_spec(make_spec(image_ref='ghcr.io:443/o/w@sha256:' + DIGEST))

    def test_repo_path_escape(self):
        root = w.GUEST_SESSION_ROOT
        for path in (f'{root}/{GEN}/repo/..', f'{root}/{GEN}/../{GEN2}/repo',
                     f'{root}/{GEN2}/repo', f'{root}//{GEN}/repo', f'{root}/{GEN}/repo/',
                     f'{root}/{GEN}/./repo', f'{root}/{GEN}/repo-link', '/workspace',
                     f'{root}/{GEN.upper()}/repo', f'{root}/{GEN}/repo:/etc', ''):
            with self.subTest(path=path):
                with self.assertRaisesRegex(w.WriterError, 'repo_source'):
                    w.validate_writer_spec(make_spec(repo_source=path))

    def test_credential_and_proxy_env_names(self):
        names = ('API_TOKEN', 'OPENAI_API_KEY', 'GITHUB_TOKEN', 'AWS_SECRET_ACCESS_KEY',
                 'DB_PASSWORD', 'OPENCODE_AUTH', 'HTTP_PROXY', 'https_proxy', 'All_Proxy',
                 'NO_PROXY', 'no_proxy', 'proxy', 'SSH_AUTH_SOCK', 'KEYRING')
        for name in names:
            with self.subTest(name=name):
                with self.assertRaisesRegex(w.WriterError, 'forbidden env name'):
                    w.validate_writer_spec(make_spec(env=((name, 'v'),)))

    def test_env_allowlist_duplicates_and_format(self):
        with self.assertRaisesRegex(w.WriterError, 'allowlist'):
            w.validate_writer_spec(make_spec(env=(('LD_PRELOAD', '/x.so'),)))
        with self.assertRaisesRegex(w.WriterError, 'duplicate'):
            w.validate_writer_spec(make_spec(env=(('HOME', 'a'), ('HOME', 'b'))))
        with self.assertRaisesRegex(w.WriterError, 'malformed'):
            w.validate_writer_spec(make_spec(env=(('HOME=x', 'a'),)))
        with self.assertRaises(w.WriterError):
            w.validate_writer_spec(make_spec(env=[('HOME', 'a')]))
        for name in sorted(w.ENV_ALLOWLIST):
            w.validate_writer_spec(make_spec(env=((name, 'v'),)))

    def test_inspect_env_rules(self):
        spec = make_spec()
        info = make_inspect(spec)
        info['Config']['Env'].append('HTTPS_PROXY=http://p')
        with self.assertRaisesRegex(w.WriterError, 'forbidden env name'):
            w.validate_writer_inspect(info, spec)
        info = make_inspect(spec)
        info['Config']['Env'] = [e for e in info['Config']['Env'] if not e.startswith('TERM=')]
        with self.assertRaisesRegex(w.WriterError, 'value mismatch for: TERM'):
            w.validate_writer_inspect(info, spec)
        info = make_inspect(spec)
        info['Config']['Env'].append('NODE_VERSION=22')
        w.validate_writer_inspect(info, spec)

    def test_command(self):
        for command in ((), ('',), ('a', None), ['opencode'], ('a\x00b',)):
            with self.subTest(command=command):
                with self.assertRaisesRegex(w.WriterError, 'command'):
                    w.validate_writer_spec(make_spec(command=command))

    def test_session_key_validation(self):
        v1 = str(uuid.uuid1())
        cases = [
            w.WriterSessionKey('', SANDBOX, GEN),
            w.WriterSessionKey('A' * 32, SANDBOX, GEN),
            w.WriterSessionKey('a' * 31, SANDBOX, GEN),
            w.WriterSessionKey(WS, '', GEN),
            w.WriterSessionKey(WS, 'not-a-uuid', GEN),
            w.WriterSessionKey(WS, SANDBOX.upper(), GEN),
            w.WriterSessionKey(WS, SANDBOX, ''),
            w.WriterSessionKey(WS, SANDBOX, v1),
            w.WriterSessionKey(WS, SANDBOX, GEN.replace('-', '')),
            w.WriterSessionKey(WS, SANDBOX, GEN.upper()),
            w.WriterSessionKey(WS, SANDBOX, '{' + GEN + '}'),
        ]
        for key in cases:
            with self.subTest(key=key):
                with self.assertRaises(w.WriterError):
                    key.validate()
        make_key().validate()

    def test_compute_workspace_id(self):
        import hashlib
        expected = hashlib.sha256(b'1000\x00/home/user/repo').hexdigest()[:32]
        self.assertEqual(w.compute_workspace_id(1000, '/home/user/repo'), expected)
        self.assertRegex(expected, r'^[0-9a-f]{32}$')
        self.assertNotEqual(w.compute_workspace_id(1001, '/home/user/repo'), expected)
        for uid, root in ((-1, '/r'), (True, '/r'), ('1000', '/r'), (1000, 'repo'),
                          (1000, ''), (1000, '/r/'), (1000, '/r/../x'), (1000, '/r/./x'),
                          (1000, '//r'), (1000, '/r//x'), (1000, '/r\x00x')):
            with self.subTest(uid=uid, root=root):
                with self.assertRaises(w.WriterError):
                    w.compute_workspace_id(uid, root)


# 11 -----------------------------------------------------------------------------
class ApiSurfaceTest(unittest.TestCase):
    def test_no_restart_exec_start_existing(self):
        forbidden = ('restart', 'exec', 'start_existing', 'resume', 'reuse',
                     'unpause', 'attach')
        for obj in (w, w.WriterLifecycle):
            names = [n.lower() for n in dir(obj)]
            for name in names:
                for frag in forbidden:
                    self.assertNotIn(frag, name, f'{obj!r} exposes {name}')
        public = {n for n in dir(w.WriterLifecycle) if not n.startswith('_')}
        self.assertEqual(public, {'launch', 'stop'})

    def test_relaunch_after_stop_rejected(self):
        spec = make_spec()
        docker = FakeDocker(spec)
        lc = lifecycle(docker)
        ident = lc.launch(spec)
        self.assertTrue(lc.stop(ident).verified)
        docker.existing = [stopped_inspect(spec)]
        before = len(docker.calls)
        with self.assertRaisesRegex(w.WriterError, 'conflict'):
            lc.launch(spec)
        self.assertNotIn('create', [c[1] for c in docker.calls[before:]])
        self.assertNotIn('start', [c[1] for c in docker.calls[before:]])


# 12 -----------------------------------------------------------------------------
class RuntimeRegressionTest(unittest.TestCase):
    """``oc2.py --help`` equality is omitted: not verified to be side-effect free."""

    def test_existing_runtime_does_not_import_writer(self):
        for name in ('oc2.py', 'oc2_guest.py', 'oc2_session.py'):
            with self.subTest(name=name):
                source = (SCRIPTS / name).read_text(encoding='utf-8')
                self.assertNotIn('oc2_writer', source)


# 13 -----------------------------------------------------------------------------
class ApmSsotTest(unittest.TestCase):
    def test_writer_never_references_apm_yml(self):
        source = (SCRIPTS / 'oc2_writer.py').read_text(encoding='utf-8')
        self.assertNotIn('apm.yml', source)
        self.assertNotIn('apm.yaml', source)


# 14 -----------------------------------------------------------------------------
class SecretLeakTest(unittest.TestCase):
    def _assert_clean(self, exc):
        self.assertNotIn(SENTINEL, str(exc))
        self.assertNotIn(SENTINEL, repr(exc))

    def test_spec_errors_do_not_leak_values(self):
        for env in ((('API_TOKEN', SENTINEL),), (('LD_PRELOAD', SENTINEL),),
                    (('HOME', SENTINEL), ('HOME', SENTINEL)),
                    (('HOME', SENTINEL + '\x00'),), (('X=' + SENTINEL, 'v'),)):
            with self.subTest(env=len(env)):
                with self.assertRaises(w.WriterError) as ctx:
                    w.validate_writer_spec(make_spec(env=env))
                self._assert_clean(ctx.exception)

    def test_inspect_errors_do_not_leak_values(self):
        spec = make_spec(env=(('HOME', SENTINEL),))
        info = make_inspect(spec)
        info['Config']['Env'] = ['HOME=other', 'SECRET_X=' + SENTINEL,
                                 'HTTP_PROXY=' + SENTINEL, SENTINEL]
        with self.assertRaises(w.WriterError) as ctx:
            w.validate_writer_inspect(info, spec)
        self._assert_clean(ctx.exception)

    def test_repr_and_launch_errors_do_not_leak(self):
        spec = make_spec(env=(('HOME', SENTINEL),))
        self.assertNotIn(SENTINEL, repr(spec))
        docker = FakeDocker(spec)
        docker.queue('create', (1, 'Error: ' + SENTINEL))
        with self.assertRaises(w.WriterError) as ctx:
            lifecycle(docker).launch(spec)
        self._assert_clean(ctx.exception)

    def test_module_source_is_printable_ascii(self):
        data = (SCRIPTS / 'oc2_writer.py').read_bytes()
        bad_chars = [b for b in data if not (0x20 <= b <= 0x7E or b == 0x0A)]
        self.assertEqual(bad_chars, [])


class NoCollectionDigestTest(unittest.TestCase):
    """STOPPED_VERIFIED is NOT sufficient for Collection consistency or Git tree
    immutability; this module never issues a Collection Digest."""

    def test_no_digest_or_apply_authorization_symbols(self):
        for name in dir(w):
            low = name.lower()
            for frag in ('digest', 'applyauth', 'apply_auth', 'collect'):
                self.assertNotIn(frag, low, name)

    def test_verified_verdict_carries_no_digest(self):
        spec = make_spec()
        verdict = w.verify_writer_stopped(make_identity(), stopped_inspect(spec),
                                          stopped_inspect(spec), clean_obs(), clean_obs())
        self.assertTrue(verdict.verified)
        self.assertEqual({f.name for f in w.StopVerdict.__dataclass_fields__.values()},
                         {'status', 'reasons'})
        self.assertNotIn('digest', repr(verdict).lower())
        self.assertIn('NOT a sufficient condition', w.StopVerdict.__doc__)
        self.assertIn('never issues a Collection Digest', w.verify_writer_stopped.__doc__
                      + w.StopVerdict.__doc__)


if __name__ == '__main__':
    unittest.main()

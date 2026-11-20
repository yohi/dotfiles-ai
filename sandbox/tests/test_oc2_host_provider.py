from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from typing import TYPE_CHECKING, final

TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / 'scripts'
for search_path in (SCRIPTS, TESTS):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

if TYPE_CHECKING:
    import sandbox.scripts.oc2_host_control as hc
    import sandbox.scripts.oc2_host_provider as hp
    import sandbox.scripts.oc2_host_ssh as hs
    import sandbox.scripts.oc2_host_lifecycle as lifecycle
    from sandbox.tests.oc2_host_lifecycle_test_support import (
        FakeGuestStopper,
        FakePreserver,
        HostFixture,
    )
    from sandbox.scripts.oc2_host_control import HostObservation, HostVmIdentity
else:
    import oc2_host_control as hc
    import oc2_host_provider as hp
    import oc2_host_ssh as hs
    from oc2_host_lifecycle_test_support import (
        FakeGuestStopper,
        FakePreserver,
        HostFixture,
    )
    import oc2_host_lifecycle as lifecycle
    from oc2_host_control import HostObservation, HostVmIdentity


@final
class FakeHostEffects:
    def __init__(
        self, observations: tuple[HostObservation, ...], *, ssh_ok: bool = False,
    ) -> None:
        self.observations = list(observations)
        self.ssh_ok = ssh_ok
        self.calls: list[str] = []
        self.shutdown_commands: list[str] = []

    def observe(self, identity: HostVmIdentity) -> HostObservation | None:
        if not identity.vm_id:
            raise AssertionError('Host VM identity missing')
        self.calls.append('observe')
        if not self.observations:
            return None
        return self.observations.pop(0)

    def shutdown(self, config: hp.HostProviderConfig) -> bool:
        if config.management_mode != 'direct-qemu':
            raise AssertionError('unsupported management mode reached shutdown')
        self.calls.append('shutdown')
        self.shutdown_commands.append(hs.POWER_OFF_COMMAND)
        return self.ssh_ok

    def wait_stopped(
        self, identity: HostVmIdentity, *, timeout_seconds: int,
    ) -> HostObservation | None:
        if not identity.vm_id or timeout_seconds <= 0:
            raise AssertionError('invalid Host stop wait')
        self.calls.append('wait')
        if not self.observations:
            return None
        return self.observations.pop(0)


@final
class SequenceRootHelper:
    def __init__(self, observations: tuple[HostObservation, ...]) -> None:
        self.observations = list(observations)

    def read(self, identity: HostVmIdentity) -> HostObservation | None:
        if not identity.vm_id:
            raise AssertionError('Host VM identity missing')
        if not self.observations:
            return None
        return self.observations.pop(0)


@final
class FakeCommandRunner:
    def __init__(self, results: tuple[hs.CommandResult, ...]) -> None:
        self.results = list(results)
        self.argv: list[tuple[str, ...]] = []
        self.inputs: list[bytes] = []
        self.known_hosts_snapshots: list[bytes] = []

    def run(
        self, argv: tuple[str, ...], *, input_bytes: bytes = b'',
    ) -> hs.CommandResult:
        self.argv.append(argv)
        self.inputs.append(input_bytes)
        if argv[0] == '/usr/bin/ssh':
            path = next(
                Path(value.split('=', 1)[1]) for value in argv
                if value.startswith('UserKnownHostsFile=')
            )
            self.known_hosts_snapshots.append(path.read_bytes())
        return self.results.pop(0)


@final
class DirectQemuProviderTests(unittest.TestCase):
    def __init__(self, methodName: str = 'runTest') -> None:
        super().__init__(methodName)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture: HostFixture = HostFixture.create(Path(temporary.name))

    def test_unknown_management_mode_is_rejected_without_effects(self) -> None:
        f = self.fixture
        effects = FakeHostEffects((f.observation(),))
        provider = hp.DirectQemuHostVmControl(
            hp.HostProviderConfig(
                management_mode='libvirt', vm_name=f.host_identity.vm_name,
                ssh_host='127.0.0.1', ssh_port=2223, ssh_user='ubuntu',
                private_key_path=str(Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'),
                known_hosts_path='/unused/known_hosts',
                host_key_fingerprint='SHA256:YVgkTOE0oaHKhbz0kXQYOc2V1qdWME1S/wuo2RsGc5c',
            ),
            effects,
        )

        result = provider.observe(f.host_identity)

        self.assertIsNone(result)
        self.assertEqual(effects.calls, [])

    def test_coordinator_returns_explicit_unsupported_mode_before_guest_stop(self) -> None:
        f = self.fixture
        effects = FakeHostEffects((f.observation(),))
        provider = hp.DirectQemuHostVmControl(
            hp.HostProviderConfig(
                management_mode='libvirt', vm_name=hp.DIRECT_QEMU_VM_NAME,
                ssh_host=hp.SSH_HOST, ssh_port=hp.SSH_PORT, ssh_user=hp.SSH_USER,
                private_key_path=str(Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'),
                known_hosts_path='/unused/known_hosts',
                host_key_fingerprint=hp.PINNED_HOST_KEY_FINGERPRINT,
            ),
            effects,
        )
        events: list[str] = []
        guest = FakeGuestStopper(f.key, f.writer, f.authority, events)
        preserver = FakePreserver(f.preservation_evidence(), events)

        result = lifecycle.coordinate_host_controlled_stop(
            lifecycle.HostControlledStopRequest(
                guest, f.authority, f.writer, f.host_identity, provider, preserver,
            )
        )

        self.assertEqual(result.failures, (hc.HostFailureCode.UNSUPPORTED_MANAGEMENT_MODE,))
        self.assertEqual(events, [])
        self.assertEqual(effects.calls, [])

    def test_shutdown_uses_only_fixed_poweroff_after_identity_and_hostkey_checks(self) -> None:
        f = self.fixture
        effects = FakeHostEffects((f.observation(),), ssh_ok=True)
        provider = hp.DirectQemuHostVmControl(
            hp.HostProviderConfig(
                management_mode='direct-qemu', vm_name=f.host_identity.vm_name,
                ssh_host='127.0.0.1', ssh_port=2223, ssh_user='ubuntu',
                private_key_path=str(Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'),
                known_hosts_path='/unused/known_hosts',
                host_key_fingerprint='SHA256:YVgkTOE0oaHKhbz0kXQYOc2V1qdWME1S/wuo2RsGc5c',
            ),
            effects,
        )

        accepted = provider.request_graceful_shutdown(f.host_identity)

        self.assertTrue(accepted)
        self.assertEqual(effects.shutdown_commands, [hs.POWER_OFF_COMMAND])

    def test_ssh_uses_only_the_verified_host_key_and_disables_user_config(self) -> None:
        """Constrain SSH config, trust sources, and multiplexing to the verified snapshot."""
        key_line = b'[127.0.0.1]:2223 ssh-ed25519 AAAA\n'
        runner = FakeCommandRunner((
            hs.CommandResult(0, key_line, b''),
            hs.CommandResult(0, b'256 SHA256:YVgkTOE0oaHKhbz0kXQYOc2V1qdWME1S/wuo2RsGc5c comment\n', b''),
            hs.CommandResult(0, b'', b''),
        ))
        config = hp.HostProviderConfig(
            management_mode='direct-qemu', vm_name=hp.DIRECT_QEMU_VM_NAME,
            ssh_host=hp.SSH_HOST, ssh_port=hp.SSH_PORT, ssh_user=hp.SSH_USER,
            private_key_path=str(Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'),
            known_hosts_path='/unused/known_hosts',
            host_key_fingerprint=hp.PINNED_HOST_KEY_FINGERPRINT,
        )

        accepted = hs.OpenSshPoweroff(runner).poweroff(config)

        self.assertTrue(accepted)
        ssh_argv = runner.argv[-1]
        self.assertIn('-F', ssh_argv)
        self.assertIn('/dev/null', ssh_argv)
        self.assertTrue(any('ControlMaster=no' in arg for arg in ssh_argv))
        self.assertTrue(any('GlobalKnownHostsFile=none' in arg for arg in ssh_argv))
        self.assertTrue(any('UserKnownHostsFile=' in arg for arg in ssh_argv))
        self.assertEqual(runner.known_hosts_snapshots, [key_line])

    def test_ssh_rejects_fingerprint_occurring_only_in_comment(self) -> None:
        """Reject a fingerprint found in a comment instead of a fingerprint field."""
        runner = FakeCommandRunner((
            hs.CommandResult(0, b'[127.0.0.1]:2223 ssh-ed25519 AAAA\n', b''),
            hs.CommandResult(0, b'256 SHA256:WRONG comment '
                             + hp.PINNED_HOST_KEY_FINGERPRINT.encode() + b'\n', b''),
        ))
        config = hp.HostProviderConfig(
            management_mode='direct-qemu', vm_name=hp.DIRECT_QEMU_VM_NAME,
            ssh_host=hp.SSH_HOST, ssh_port=hp.SSH_PORT, ssh_user=hp.SSH_USER,
            private_key_path=str(Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'),
            known_hosts_path='/unused/known_hosts',
            host_key_fingerprint=hp.PINNED_HOST_KEY_FINGERPRINT,
        )

        accepted = hs.OpenSshPoweroff(runner).poweroff(config)

        self.assertFalse(accepted)
        self.assertFalse(any(argv[0] == '/usr/bin/ssh' for argv in runner.argv))

    def test_ssh_success_does_not_claim_vm_stopped_or_isolated(self) -> None:
        f = self.fixture
        stopped_but_unproven = replace(
            f.observation(stopped=True),
            autostart_policy=hc.AutostartPolicy.UNKNOWN,
            restart_audit_complete=False,
            shared_write_scope_complete=False,
            shared_write_possible=None,
        )
        effects = FakeHostEffects((stopped_but_unproven,), ssh_ok=True)
        provider = hp.DirectQemuHostVmControl(
            hp.HostProviderConfig(
                management_mode='direct-qemu', vm_name=f.host_identity.vm_name,
                ssh_host='127.0.0.1', ssh_port=2223, ssh_user='ubuntu',
                private_key_path=str(Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'),
                known_hosts_path='/unused/known_hosts',
                host_key_fingerprint='SHA256:YVgkTOE0oaHKhbz0kXQYOc2V1qdWME1S/wuo2RsGc5c',
            ),
            effects,
        )

        observation = provider.wait_for_stopped(f.host_identity, timeout_seconds=1)
        result = hc.verify_host_isolation(
            f.host_identity,
            hc.HostStopObservations(f.observation(), f.observation(), observation),
        )

        self.assertIsNotNone(observation)
        self.assertFalse(result.verified)
        self.assertIn(hc.HostFailureCode.AUTOSTART_NOT_DISABLED, result.failures)
        self.assertIn(hc.HostFailureCode.RESTART_AUDIT_INCOMPLETE, result.failures)
        self.assertIn(hc.HostFailureCode.SHARED_WRITE_UNKNOWN, result.failures)

    def test_coordinator_stops_guest_but_withholds_preservation_when_isolation_unknown(self) -> None:
        f = self.fixture
        config = hp.HostProviderConfig(
            management_mode='direct-qemu', vm_name=hp.DIRECT_QEMU_VM_NAME,
            ssh_host=hp.SSH_HOST, ssh_port=hp.SSH_PORT, ssh_user=hp.SSH_USER,
            private_key_path=str(Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'),
            known_hosts_path='/unused/known_hosts',
            host_key_fingerprint=hp.PINNED_HOST_KEY_FINGERPRINT,
        )
        observations = SequenceRootHelper((
            f.observation(), f.observation(), f.observation(), f.observation(stopped=True),
        ))
        runner = FakeCommandRunner((
            hs.CommandResult(0, b'127.0.0.1 ssh-ed25519 AAAA\n', b''),
            hs.CommandResult(0, b'256 ' + hp.PINNED_HOST_KEY_FINGERPRINT.encode() + b'\n', b''),
            hs.CommandResult(0, b'', b''),
        ))
        provider = hp.build_direct_qemu_host_control(
            config, observations, runner,
        )
        events: list[str] = []
        guest = FakeGuestStopper(f.key, f.writer, f.authority, events)
        preserver = FakePreserver(f.preservation_evidence(), events)

        result = lifecycle.coordinate_host_controlled_stop(
            lifecycle.HostControlledStopRequest(
                guest, f.authority, f.writer, f.host_identity, provider, preserver,
            )
        )

        self.assertEqual(runner.argv[-1][0], '/usr/bin/ssh')
        if result.host_isolation is None:
            self.fail('Host isolation result missing')
        self.assertFalse(result.host_isolation.verified)
        self.assertIn(hc.HostFailureCode.AUTOSTART_NOT_DISABLED, result.failures)
        self.assertNotIn('preserve', events)


if __name__ == '__main__':
    unittest.main()

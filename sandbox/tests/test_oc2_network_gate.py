from __future__ import annotations

import json
import pathlib
import sys
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import oc2_network_gate as gate  # noqa: E402
import oc2  # noqa: E402

SANDBOX = 'oc2-env004-policy-1795050720507078434'
POLICY_BEFORE = {
    'rules': [
        {
            'id': 'default-fs-read-allow-all', 'scope': 'global',
            'resource_type': 'filesystem:read', 'decision': 'allow',
            'resources': ['**'], 'status': 'active', 'actions': ['fs:mount:read'],
        },
        {
            'id': 'default-fs-write-allow-all', 'scope': 'global',
            'resource_type': 'filesystem:write', 'decision': 'allow',
            'resources': ['**'], 'status': 'active',
            'actions': ['fs:mount:read', 'fs:mount:write'],
        },
        {
            'id': 'default-deny-all', 'name': 'default-deny-all',
            'policy_name': 'default-deny-all', 'scope': 'global',
            'applies_to': 'all',
            'resource_type': 'network', 'decision': 'deny', 'resources': ['**'],
            'status': 'active', 'actions': ['net:connect:tcp', 'net:connect:udp'],
        },
    ],
}


class PolicyParserTests(unittest.TestCase):
    def test_accepts_measured_global_default_deny_before_allow(self):
        gate.validate_policy_listing(json.dumps(POLICY_BEFORE), SANDBOX, 'before')

    def test_rejects_active_global_network_allow(self):
        value = json.loads(json.dumps(POLICY_BEFORE))
        value['rules'].append({
            'id': 'unsafe', 'scope': 'global', 'resource_type': 'network',
            'decision': 'allow', 'resources': ['**'], 'status': 'active',
            'actions': ['net:connect:tcp'],
        })
        with self.assertRaises(gate.NetworkGateError):
            gate.validate_policy_listing(json.dumps(value), SANDBOX, 'before')

    def test_rejects_missing_tcp_udp_default_deny(self):
        value = json.loads(json.dumps(POLICY_BEFORE))
        value['rules'][-1]['actions'] = ['net:connect:tcp']
        with self.assertRaises(gate.NetworkGateError):
            gate.validate_policy_listing(json.dumps(value), SANDBOX, 'before')

    def test_rejects_malformed_json_and_unrecognized_network_rule(self):
        with self.assertRaises(gate.NetworkGateError):
            gate.validate_policy_listing('{not json', SANDBOX, 'before')
        value = json.loads(json.dumps(POLICY_BEFORE))
        value['rules'].append({
            'id': 'unknown', 'scope': 'global', 'resource_type': 'network',
            'decision': 'deny', 'resources': ['*'], 'status': 'active',
            'actions': ['net:connect:tcp', 'net:connect:udp'],
        })
        with self.assertRaises(gate.NetworkGateError):
            gate.validate_policy_listing(json.dumps(value), SANDBOX, 'before')

    def test_allow_listing_must_bind_exact_sandbox_host_port_and_tcp(self):
        value = json.loads(json.dumps(POLICY_BEFORE))
        value['rules'].insert(0, {
            'id': 'e0dd734a-60e7-4589-959e-4ecfa798eb7f',
            'policy_id': 'd0c763fe-de6c-4efb-871f-6a1ddf8bbc2d',
            'scope': f'sandbox:{SANDBOX}',
            'applies_to': f'sandbox:{SANDBOX}', 'sandbox_id': SANDBOX,
            'resource_type': 'network', 'decision': 'allow',
            'resources': ['localhost:49187'], 'status': 'active',
            'actions': ['net:connect:tcp'],
        })
        gate.validate_policy_listing(json.dumps(value), SANDBOX, 'after', 'localhost:49187')
        value['rules'][0]['sandbox_id'] = 'another-sandbox'
        with self.assertRaises(gate.NetworkGateError):
            gate.validate_policy_listing(json.dumps(value), SANDBOX, 'after', 'localhost:49187')


class PolicyCheckTests(unittest.TestCase):
    def test_measured_allow_and_denies_require_exit_code_and_identity(self):
        allow = {
            'action': 'net:connect:tcp', 'allowed': True,
            'context': f'sandbox:{SANDBOX}', 'resource_type': 'net:domain',
            'resource_value': 'localhost:49187', 'target': 'localhost:49187',
            'type': 'network',
        }
        deny = {
            **allow, 'allowed': False, 'resource_value': 'example.com:443',
            'target': 'example.com:443', 'deny_kind': 'implicit',
            'reason': 'No matching allow rule (default deny)',
        }
        gate.validate_policy_check(json.dumps(allow), 0, SANDBOX, 'localhost:49187', True)
        gate.validate_policy_check(json.dumps(deny), 1, SANDBOX, 'example.com:443', False)
        for rc, payload, expected, target in (
            (1, allow, True, 'localhost:49187'),
            (0, deny, False, 'example.com:443'),
            (0, {**allow, 'context': 'sandbox:other'}, True, 'localhost:49187'),
            (0, {**allow, 'target': 'localhost:49188'}, True, 'localhost:49187'),
        ):
            with self.subTest(rc=rc, expected=expected, target=target), \
                    self.assertRaises(gate.NetworkGateError):
                gate.validate_policy_check(json.dumps(payload), rc, SANDBOX, target, expected)

    def test_host_docker_internal_must_normalize_to_expected_localhost_target(self):
        payload = {
            'action': 'net:connect:tcp', 'allowed': True,
            'context': f'sandbox:{SANDBOX}', 'resource_type': 'net:domain',
            'resource_value': 'localhost:49187', 'target': 'localhost:49187',
            'type': 'network',
        }
        gate.validate_policy_check(
            json.dumps(payload), 0, SANDBOX, 'localhost:49187', True,
            expected_target='localhost:49187',
        )


class DedicatedDaemonTests(unittest.TestCase):
    def test_daemon_name_is_required_and_socket_identity_must_match(self):
        for name in (None, '', 'bad name'):
            with self.subTest(name=name), self.assertRaises(gate.NetworkGateError):
                gate.validate_app_name(name)
        expected = pathlib.Path('/state/sandboxes/sandboxes-oc2-isolated/sandboxd/sandboxd.sock')
        status = f'Status: ● running\nSocket: {expected}\n'
        gate.validate_daemon_identity(status, expected, 0o140000)
        with self.assertRaises(gate.NetworkGateError):
            gate.validate_daemon_identity(status.replace(str(expected), '/tmp/other.sock'), expected,
                                          0o140000)
        with self.assertRaises(gate.NetworkGateError):
            gate.validate_daemon_identity(status.replace('running', 'stopped'), expected, 0o140000)

    def test_runner_pins_app_name_on_every_sbx_invocation(self):
        runner = oc2.Runner('tester', app_name='oc2-isolated')
        with patch.object(oc2.subprocess, 'run', return_value=oc2.subprocess.CompletedProcess(
                ['sbx'], 0, 'ok', '')) as run:
            runner.sbx('policy', 'ls', '--json', capture=True)
        command = run.call_args.args[0]
        self.assertEqual(command[-6:], [
            'sbx', '--app-name', 'oc2-isolated', 'policy', 'ls', '--json',
        ])


class GateFlowTests(unittest.TestCase):
    def test_network_gate_checks_before_allow_then_readback_and_both_allow_and_denials(self):
        class FakeRunner:
            def __init__(self):
                self.calls = []
                self.allow_enabled = False

            def sbx(self, *args, capture=False, tty=False, timeout=180):
                self.calls.append(args)
                if args[:3] == ('--no-input', 'policy', 'allow'):
                    self.allow_enabled = True
                listing = args[0:3] == ('policy', 'ls', '--json')
                return json.dumps(_policy_after() if listing and self.allow_enabled
                                  else POLICY_BEFORE)

            def sbx_result(self, *args, timeout=180):
                self.calls.append(args)
                target = args[-1]
                allowed = (self.allow_enabled
                           and target in {'localhost:49187', 'host.docker.internal:49187'})
                value = {
                    'action': 'net:connect:tcp', 'allowed': allowed,
                    'context': f'sandbox:{SANDBOX}', 'resource_type': 'net:domain',
                    'resource_value': 'localhost:49187' if allowed else target,
                    'target': 'localhost:49187' if allowed else target, 'type': 'network',
                }
                if not allowed:
                    value.update(deny_kind='implicit', reason='No matching allow rule (default deny)')
                return (0 if allowed else 1), json.dumps(value)

        runner = FakeRunner()
        gate.run_network_gate(runner, SANDBOX, 49187)
        self.assertEqual(runner.calls[0][-1], 'localhost:49187')
        self.assertIn('--no-input', runner.calls[1])
        self.assertIn('policy', runner.calls[2])
        self.assertTrue(any(call[-1] == 'host.docker.internal:49187' for call in runner.calls))
        self.assertTrue(any(call[-1] == 'localhost:49188' for call in runner.calls))
        self.assertTrue(any(call[-1] == 'example.com:443' for call in runner.calls))


def _policy_after():
    value = json.loads(json.dumps(POLICY_BEFORE))
    value['rules'].insert(0, {
        'id': 'e0dd734a-60e7-4589-959e-4ecfa798eb7f',
        'policy_id': 'd0c763fe-de6c-4efb-871f-6a1ddf8bbc2d',
        'scope': f'sandbox:{SANDBOX}',
        'applies_to': f'sandbox:{SANDBOX}', 'sandbox_id': SANDBOX,
        'resource_type': 'network', 'decision': 'allow',
        'resources': ['localhost:49187'], 'status': 'active',
        'actions': ['net:connect:tcp'],
    })
    return value


if __name__ == '__main__':
    unittest.main()

from __future__ import annotations

import json
import pathlib
import sys
import unittest
from dataclasses import replace

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import oc2_network_policy as policy  # noqa: E402
import oc2_network_gate as gate  # noqa: E402

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


class TaskBrokerAllowTests(unittest.TestCase):
    def test_discovery_returns_exact_loopback_broker_allow_identity(self):
        sandbox = 'oc2-env004-m1-abc123'
        policy_listing = {
            'rules': [
                {
                    'id': 'e0dd734a-60e7-4589-959e-4ecfa798eb7f',
                    'policy_id': 'd0c763fe-de6c-4efb-871f-6a1ddf8bbc2d',
                    'scope': f'sandbox:{sandbox}',
                    'applies_to': f'sandbox:{sandbox}',
                    'sandbox_id': sandbox,
                    'resource_type': 'network',
                    'decision': 'allow',
                    'resources': ['localhost:49187'],
                    'status': 'active',
                    'actions': ['net:connect:tcp'],
                },
                {
                    'id': 'default-deny-all',
                    'name': 'default-deny-all',
                    'scope': 'global',
                    'applies_to': 'all',
                    'resource_type': 'network',
                    'decision': 'deny',
                    'resources': ['**'],
                    'status': 'active',
                    'actions': ['net:connect:tcp', 'net:connect:udp'],
                },
            ],
        }

        identity = policy.find_task_broker_allow(json.dumps(policy_listing), sandbox)

        self.assertEqual(identity, policy.ScopedNetworkAllow(
            sandbox, sandbox,
            'd0c763fe-de6c-4efb-871f-6a1ddf8bbc2d',
            'e0dd734a-60e7-4589-959e-4ecfa798eb7f',
            'localhost:49187',
        ))


class ScopedAllowCleanupTests(unittest.TestCase):
    def setUp(self):
        self.runner = PolicyRunnerFake()

    def test_cleanup_finds_no_rule_without_weakening_global_default_deny(self):
        identity = gate.find_scoped_network_allow(
            json.dumps(POLICY_BEFORE), SANDBOX, 'localhost:49187',
        )

        self.assertIsNone(identity)
        gate.validate_policy_listing(json.dumps(POLICY_BEFORE), SANDBOX, 'before')

    def test_cleanup_discovers_only_the_task_broker_allow_from_policy_identity(self):
        identity = policy.find_task_broker_allow(json.dumps(_policy_after()), SANDBOX)

        self.assertEqual(identity, policy.ScopedNetworkAllow(
            SANDBOX, SANDBOX,
            'd0c763fe-de6c-4efb-871f-6a1ddf8bbc2d',
            'e0dd734a-60e7-4589-959e-4ecfa798eb7f',
            'localhost:49187',
        ))

    def test_cleanup_refuses_non_loopback_or_non_tcp_scoped_rule(self):
        value = _policy_after()
        value['rules'][0]['resources'] = ['example.com:443']
        with self.assertRaises(gate.NetworkGateError):
            policy.find_task_broker_allow(json.dumps(value), SANDBOX)

    def test_gate_returns_exact_task_owned_rule_identity(self):
        identity = gate.run_network_gate(self.runner, SANDBOX, 49187)

        self.assertEqual(identity.sandbox, SANDBOX)
        self.assertEqual(identity.sandbox_id, SANDBOX)
        self.assertEqual(identity.rule_id, 'e0dd734a-60e7-4589-959e-4ecfa798eb7f')
        self.assertEqual(identity.policy_id, 'd0c763fe-de6c-4efb-871f-6a1ddf8bbc2d')
        self.assertEqual(identity.resource, 'localhost:49187')

    def test_revoke_removes_only_the_matching_scoped_rule_and_reads_back(self):
        identity = gate.run_network_gate(self.runner, SANDBOX, 49187)

        gate.revoke_network_allow(self.runner, identity)

        removals = [call for call in self.runner.calls if call[:4] == (
            '--no-input', 'policy', 'rm', 'network')]
        self.assertEqual(removals, [(
            '--no-input', 'policy', 'rm', 'network', '--id', identity.rule_id,
            '--sandbox', identity.sandbox,
        )])
        self.assertEqual(self.runner.policy, POLICY_BEFORE)
        self.assertEqual(self.runner.calls[-1], ('policy', 'ls', '--json'))

    def test_revoke_refuses_changed_rule_identity_without_removing_anything(self):
        identity = gate.run_network_gate(self.runner, SANDBOX, 49187)
        forged = replace(identity, rule_id='f0dd734a-60e7-4589-959e-4ecfa798eb7f')

        with self.assertRaises(gate.NetworkGateError):
            gate.revoke_network_allow(self.runner, forged)

        self.assertFalse(any(call[:4] == (
            '--no-input', 'policy', 'rm', 'network') for call in self.runner.calls))
        self.assertNotEqual(self.runner.policy, POLICY_BEFORE)

    def test_gate_checks_external_udp_and_dns_policy_denials(self):
        gate.run_network_gate(self.runner, SANDBOX, 49187)

        checks = [call for call in self.runner.calls if call[:2] == ('policy', 'check')]
        self.assertIn(('policy', 'check', 'network', '--json', '--sandbox', SANDBOX,
                       '--protocol', 'udp', '1.1.1.1:53'), checks)
        self.assertIn(('policy', 'check', 'network', '--json', '--sandbox', SANDBOX,
                       '--protocol', 'tcp', 'example.com:443'), checks)
        self.assertIn(('policy', 'check', 'network', '--json', '--sandbox', SANDBOX,
                       '--protocol', 'udp', 'example.com:53'), checks)

    def test_guest_gate_receives_only_public_ca_bytes_on_stdin(self):
        ca_data = b'public-test-ca-bytes'

        gate.probe_guest_broker(self.runner, SANDBOX, 'host.docker.internal', 49187, ca_data)

        args, data = self.runner.fed[-1]
        self.assertEqual(args[:3], ('exec', '-i', SANDBOX))
        self.assertEqual(args[3:5], ('python3', '-c'))
        self.assertIn('socket.getaddrinfo', args[5])
        self.assertIn('dns.sendto', args[5])
        self.assertIn('context.wrap_socket', args[5])
        self.assertEqual(data, ca_data)
        self.assertNotIn(ca_data.decode(), args)


class PolicyRunnerFake:
    def __init__(self):
        self.calls = []
        self.policy = json.loads(json.dumps(POLICY_BEFORE))
        self.fed = []

    def sbx_feed(self, *args, data):
        self.calls.append(args)
        self.fed.append((args, data))

    def sbx(self, *args, capture=False, tty=False, timeout=180):
        self.calls.append(args)
        if args[:3] == ('policy', 'ls', '--json'):
            return json.dumps(self.policy)
        if args[:4] == ('--no-input', 'policy', 'allow', 'network'):
            self.policy = _policy_after()
            return ''
        if args[:4] == ('--no-input', 'policy', 'rm', 'network'):
            rule_id = args[args.index('--id') + 1]
            self.policy['rules'] = [
                rule for rule in self.policy['rules'] if rule.get('id') != rule_id
            ]
            return ''
        return ''

    def sbx_result(self, *args, timeout=180):
        self.calls.append(args)
        protocol = args[args.index('--protocol') + 1]
        target = args[-1]
        has_scoped_allow = any(
            rule.get('scope') == f'sandbox:{SANDBOX}'
            for rule in self.policy['rules']
        )
        is_broker_tcp = has_scoped_allow and protocol == 'tcp' and target in {
            'localhost:49187', 'host.docker.internal:49187',
        }
        value = {
            'action': 'net:connect:' + protocol,
            'allowed': is_broker_tcp,
            'context': f'sandbox:{SANDBOX}',
            'resource_type': 'net:domain',
            'resource_value': 'localhost:49187' if is_broker_tcp else target,
            'target': 'localhost:49187' if is_broker_tcp else target,
            'type': 'network',
        }
        if not is_broker_tcp:
            value.update(deny_kind='implicit', reason='No matching allow rule (default deny)')
        return (0 if is_broker_tcp else 1), json.dumps(value)


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

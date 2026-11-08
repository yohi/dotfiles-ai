from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import TypeAlias

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
SERVER = SCRIPTS / 'oc2_local_mcp.py'
sys.path.insert(0, str(SCRIPTS))
import oc2_local_mcp

JSON: TypeAlias = str | int | float | bool | None | list['JSON'] | dict[str, 'JSON']

def message(method: str, request_id: int | None = None,
            params: dict[str, JSON] | None = None) -> str:
    value: dict[str, JSON] = {'jsonrpc': '2.0', 'method': method}
    if request_id is not None:
        value['id'] = request_id
    if params is not None:
        value['params'] = params
    return json.dumps(value) + '\n'


def initialized_input() -> str:
    return (
        message('initialize', 1, {
            'protocolVersion': '2025-06-18',
            'capabilities': {},
            'clientInfo': {'name': 'oc2-offline-test', 'version': '1'},
        })
        + message('notifications/initialized')
    )


class LocalMcpProtocolTest(unittest.TestCase):
    def _serve(self, payload: str) -> tuple[int, list[dict[str, object]]]:
        output = io.StringIO()
        status = oc2_local_mcp.serve(io.StringIO(payload), output)
        return status, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_initialize_and_initialized_notification_negotiate_protocol(self):
        status, responses = self._serve(initialized_input())

        self.assertEqual(status, 0)
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]['result']['protocolVersion'], '2025-06-18')
        self.assertEqual(responses[0]['result']['capabilities'], {'tools': {}})

    def test_tools_list_exposes_only_oc2_status(self):
        status, responses = self._serve(
            initialized_input() + message('tools/list', 2, {}),
        )

        self.assertEqual(status, 0)
        self.assertEqual(responses[1]['result']['tools'][0]['name'], 'oc2_status')
        self.assertEqual(len(responses[1]['result']['tools']), 1)

    def test_tools_are_rejected_until_initialized_notification(self):
        status, responses = self._serve(
            message('initialize', 1, {
                'protocolVersion': '2025-06-18',
                'capabilities': {},
                'clientInfo': {'name': 'oc2-offline-test', 'version': '1'},
            })
            + message('tools/list', 2, {}),
        )

        self.assertEqual(status, 0)
        self.assertEqual(responses[1]['error']['code'], -32002)

    def test_status_tool_call_returns_only_fixed_component_metadata(self):
        payload = initialized_input() + message(
            'tools/call', 3, {'name': 'oc2_status', 'arguments': {}},
        )
        status, responses = self._serve(payload)

        self.assertEqual(status, 0)
        content = responses[1]['result']['content']
        self.assertEqual(json.loads(content[0]['text']), {
            'schema': 'dotfiles-ai/oc2-native/v2',
            'opencode_version': '2.2.5',
            'components': {'plugins': ['superpowers'], 'mcp_servers': ['oc2-status']},
        })

    def test_invalid_tool_arguments_return_error_without_status_result(self):
        status, responses = self._serve(
            initialized_input() + message(
                'tools/call', 4, {'name': 'oc2_status', 'arguments': {'unexpected': True}},
            ),
        )

        self.assertEqual(status, 0)
        self.assertEqual(responses[1]['error']['code'], -32602)

    def test_malformed_json_emits_parse_error_and_exits(self):
        status, responses = self._serve('{bad json}\n')

        self.assertEqual(status, 1)
        self.assertEqual(responses[0]['error']['code'], -32700)

    def test_stdio_subprocess_roundtrip_keeps_stdout_protocol_only(self):
        payload = (
            initialized_input()
            + message('tools/list', 2, {})
            + message('tools/call', 3, {'name': 'oc2_status', 'arguments': {}})
        )
        result = subprocess.run(
            [sys.executable, '-I', str(SERVER)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env={'PATH': os.environ.get('PATH', '')},
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([item['id'] for item in responses], [1, 2, 3])

    def test_stdio_subprocess_malformed_input_exits_cleanly(self):
        result = subprocess.run(
            [sys.executable, '-I', str(SERVER)],
            input='{bad json}\n',
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env={'PATH': os.environ.get('PATH', '')},
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout)['error']['code'], -32700)


if __name__ == '__main__':
    unittest.main()

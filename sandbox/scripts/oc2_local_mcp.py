from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TextIO, TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']
RequestId: TypeAlias = str | int
JsonObject: TypeAlias = dict[str, JsonValue]

PROTOCOL_VERSION: Final[str] = '2025-06-18'
SERVER_NAME: Final[str] = 'oc2-local-status'
SERVER_VERSION: Final[str] = '0.1.0'
MAX_LINE_BYTES: Final[int] = 1024 * 1024
TOOL_SCHEMA: Final[JsonObject] = {
    'type': 'object',
    'properties': {},
    'additionalProperties': False,
}
STATUS: Final[JsonObject] = {
    'schema': 'dotfiles-ai/oc2-native/v2',
    'opencode_version': '2.2.5',
    'components': {
        'plugins': ['superpowers'],
        'mcp_servers': ['oc2-status'],
    },
}


@dataclass(frozen=True, slots=True)
class DispatchResult:
    response: JsonObject | None
    state: SessionState
    stop: bool


class SessionState(StrEnum):
    NEW = 'new'
    AWAITING_INITIALIZED = 'awaiting-initialized'
    READY = 'ready'


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON object key')
        result[key] = value
    return result


def _response(request_id: RequestId, result: JsonValue) -> JsonObject:
    return {'jsonrpc': '2.0', 'id': request_id, 'result': result}


def _error(request_id: RequestId | None, code: int, message: str) -> JsonObject:
    return {
        'jsonrpc': '2.0',
        'id': request_id,
        'error': {'code': code, 'message': message},
    }


def _request_id(message: JsonObject) -> RequestId | None:
    value = message.get('id')
    if isinstance(value, str):
        return value
    if type(value) is int:
        return value
    return None


def _tool_result() -> JsonObject:
    return {
        'content': [{
            'type': 'text',
            'text': json.dumps(STATUS, sort_keys=True, separators=(',', ':')),
        }],
        'isError': False,
    }


def _dispatch(value: JsonValue, state: SessionState) -> DispatchResult:
    if not isinstance(value, dict):
        return DispatchResult(_error(None, -32600, 'Invalid Request'), state, False)

    request_id = _request_id(value)
    if ('jsonrpc' not in value or value['jsonrpc'] != '2.0'
            or not isinstance(value.get('method'), str)):
        response = _error(request_id, -32600, 'Invalid Request') if 'id' in value else None
        return DispatchResult(response, state, False)

    method = value['method']
    params = value.get('params')
    if method == 'notifications/initialized' and 'id' not in value:
        ready = SessionState.READY if state is SessionState.AWAITING_INITIALIZED else state
        return DispatchResult(None, ready, False)
    if request_id is None:
        return DispatchResult(None, state, False)

    if method == 'initialize':
        if state is not SessionState.NEW:
            return DispatchResult(_error(request_id, -32600, 'Invalid Request'), state, False)
        if not isinstance(params, dict) or not isinstance(params.get('protocolVersion'), str):
            return DispatchResult(_error(request_id, -32602, 'Invalid params'), state, False)
        result: JsonObject = {
            'protocolVersion': PROTOCOL_VERSION,
            'capabilities': {'tools': {}},
            'serverInfo': {'name': SERVER_NAME, 'version': SERVER_VERSION},
        }
        return DispatchResult(_response(request_id, result), SessionState.AWAITING_INITIALIZED, False)

    if state is not SessionState.READY:
        return DispatchResult(_error(request_id, -32002, 'Server not initialized'), state, False)

    if method == 'tools/list':
        if params not in (None, {}):
            return DispatchResult(_error(request_id, -32602, 'Invalid params'), state, False)
        tool: JsonObject = {
            'name': 'oc2_status',
            'description': 'Read the fixed OC2 verification component status.',
            'inputSchema': TOOL_SCHEMA,
        }
        return DispatchResult(_response(request_id, {'tools': [tool]}), state, False)

    if method == 'tools/call':
        if not isinstance(params, dict) or set(params) - {'name', 'arguments'}:
            return DispatchResult(_error(request_id, -32602, 'Invalid params'), state, False)
        arguments = params.get('arguments', {})
        if (params.get('name') != 'oc2_status' or not isinstance(arguments, dict)
                or arguments):
            return DispatchResult(_error(request_id, -32602, 'Invalid params'), state, False)
        return DispatchResult(_response(request_id, _tool_result()), state, False)

    return DispatchResult(_error(request_id, -32601, 'Method not found'), state, False)


def _write(stdout: TextIO, value: JsonObject) -> None:
    stdout.write(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
    stdout.flush()


def serve(stdin: TextIO, stdout: TextIO) -> int:
    """Serve the fixed read-only MCP protocol on newline-delimited stdio."""
    state = SessionState.NEW
    while line := stdin.readline(MAX_LINE_BYTES + 1):
        if len(line.encode('utf-8')) > MAX_LINE_BYTES:
            _write(stdout, _error(None, -32700, 'Parse error'))
            return 1
        try:
            value: JsonValue = json.loads(line, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError):
            _write(stdout, _error(None, -32700, 'Parse error'))
            return 1
        result = _dispatch(value, state)
        state = result.state
        if result.response is not None:
            _write(stdout, result.response)
        if result.stop:
            return 1
    return 0


def main() -> int:
    return serve(sys.stdin, sys.stdout)


if __name__ == '__main__':
    raise SystemExit(main())

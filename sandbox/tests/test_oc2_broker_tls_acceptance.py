from __future__ import annotations

import json
import os
import pathlib
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar


CLI_ENV = 'OC2_OPENCODE_CLI'
MODEL = 'openai/oc2-tls-probe'
API_KEY = 'synthetic-oc2-tls-acceptance-key'


class ResponsesHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list[tuple[str, str | None]]] = []

    def do_POST(self) -> None:
        self.requests.append((self.path, self.headers.get('Authorization')))
        response = {
            'type': 'response.completed',
            'response': {
                'id': 'resp_oc2_tls_test',
                'object': 'response',
                'created_at': 1,
                'status': 'completed',
                'model': 'oc2-tls-probe',
                'output': [{
                    'id': 'msg_oc2_tls_test',
                    'type': 'message',
                    'status': 'completed',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': 'ok', 'annotations': []}],
                }],
                'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2},
            },
        }
        body = f'data: {json.dumps(response)}\n\ndata: [DONE]\n\n'.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    tls_connections: ClassVar[int] = 0
    tls_connection_errors: ClassVar[int] = 0

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        try:
            connection, address = super().get_request()
        except OSError:
            QuietThreadingHTTPServer.tls_connection_errors += 1
            raise
        QuietThreadingHTTPServer.tls_connections += 1
        return connection, address

    def handle_error(self, _request: object, _client_address: object) -> None:
        return


class OpenCodeBrokerTlsAcceptanceTests(unittest.TestCase):
    cli: ClassVar[pathlib.Path]

    @classmethod
    def setUpClass(cls) -> None:
        cli_path = os.environ.get(CLI_ENV)
        if not cli_path:
            raise unittest.SkipTest(f'{CLI_ENV} is required for the offline CLI acceptance test')
        cls.cli = pathlib.Path(cli_path).resolve(strict=True)
        version = subprocess.run(
            [str(cls.cli), '--version'], capture_output=True, timeout=15, check=False,
        )
        if version.returncode != 0 or b'2.2.5' not in version.stdout:
            raise unittest.SkipTest(f'{CLI_ENV} must point to the pinned OpenCode v2.2.5 executable')

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix='oc2-broker-tls-acceptance-')
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.certificates = self.root / 'certificates'
        self.certificates.mkdir(mode=0o700)
        self.config_dir = self.root / 'config' / 'opencode'
        self.config_dir.mkdir(parents=True, mode=0o700)
        self._create_certificate('ip', 'IP:127.0.0.1')
        self._create_certificate('dns', 'DNS:host.docker.internal')

    def _create_certificate(self, name: str, san: str) -> pathlib.Path:
        certificate = self.certificates / f'{name}.pem'
        key = self.certificates / f'{name}.key'
        subprocess.run(
            [
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-days', '2', '-subj', f'/CN={name} OC2 TLS test',
                '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:0',
                '-addext', 'keyUsage=critical,digitalSignature,keyCertSign,cRLSign',
                '-addext', 'extendedKeyUsage=serverAuth',
                '-addext', f'subjectAltName={san}',
                '-keyout', str(key), '-out', str(certificate),
            ],
            capture_output=True,
            timeout=20,
            check=True,
        )
        return certificate

    def _run_cli(
        self, certificate_name: str, *, trusted: bool,
    ) -> tuple[
        subprocess.CompletedProcess[bytes],
        list[tuple[str, str | None]],
        tuple[int, int],
    ]:
        certificate = self.certificates / f'{certificate_name}.pem'
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(
            certfile=certificate,
            keyfile=self.certificates / f'{certificate_name}.key',
        )
        ResponsesHandler.requests = []
        QuietThreadingHTTPServer.tls_connections = 0
        QuietThreadingHTTPServer.tls_connection_errors = 0
        server = QuietThreadingHTTPServer(('127.0.0.1', 0), ResponsesHandler)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f'https://127.0.0.1:{server.server_port}/v1'
            config = {
                '$schema': 'https://opencode.ai/config.json',
                'model': MODEL,
                'provider': {
                    'openai': {
                        'options': {
                            'baseURL': base_url,
                            'apiKey': API_KEY,
                        },
                        'models': {
                            'oc2-tls-probe': {
                                'name': 'Offline TLS acceptance fixture',
                                'limit': {'context': 8192, 'output': 1024},
                            },
                        },
                    },
                },
            }
            (self.config_dir / 'opencode.json').write_text(
                json.dumps(config), encoding='utf-8',
            )
            environment = {
                'HOME': str(self.root / 'home'),
                'PATH': os.environ.get('PATH', ''),
                'XDG_CONFIG_HOME': str(self.root / 'config'),
                'XDG_DATA_HOME': str(self.root / 'data'),
                'XDG_CACHE_HOME': str(self.root / 'cache'),
            }
            if trusted:
                environment['NODE_EXTRA_CA_CERTS'] = str(certificate)
            command = [
                str(self.cli), '--standalone', '--print-logs', '--log-level', 'debug',
                'run', '--model', MODEL, '--format', 'json', 'tls probe',
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    timeout=15,
                    check=False,
                    env=environment,
                    cwd=self.root,
                )
            except subprocess.TimeoutExpired as error:
                result = subprocess.CompletedProcess(
                    command,
                    124,
                    error.stdout if isinstance(error.stdout, bytes) else b'',
                    error.stderr if isinstance(error.stderr, bytes) else b'',
                )
            return (
                result,
                list(ResponsesHandler.requests),
                (QuietThreadingHTTPServer.tls_connections,
                 QuietThreadingHTTPServer.tls_connection_errors),
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_pinned_cli_accepts_broker_signed_by_extra_ca(self) -> None:
        result, requests, tls_counts = self._run_cli('ip', trusted=True)

        diagnostic = '\n'.join((
            result.stdout.decode('utf-8', errors='replace'),
            result.stderr.decode('utf-8', errors='replace'),
            repr(requests),
        )).replace(API_KEY, '[redacted]')
        self.assertEqual(result.returncode, 0, diagnostic)
        self.assertGreater(tls_counts[0], 0)
        self.assertIn(('/v1/responses', f'Bearer {API_KEY}'), requests)

    def test_pinned_cli_rejects_untrusted_broker_certificate(self) -> None:
        _result, requests, tls_counts = self._run_cli('ip', trusted=False)

        self.assertGreater(sum(tls_counts), 0)
        self.assertEqual(requests, [])

    def test_pinned_cli_rejects_broker_hostname_mismatch(self) -> None:
        _result, requests, tls_counts = self._run_cli('dns', trusted=True)

        self.assertGreater(sum(tls_counts), 0)
        self.assertEqual(requests, [])


if __name__ == '__main__':
    unittest.main()

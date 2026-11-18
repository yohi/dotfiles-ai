from __future__ import annotations

import hashlib
import pathlib
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import oc2_host_broker as hb  # noqa: E402

URL = 'https://host.docker.internal:18080/v1'


def _openssl(*args: str) -> None:
    subprocess.run(
        ['openssl', *args], check=True, capture_output=True, text=True, timeout=20,
    )


def _create_ca(root: pathlib.Path, label: str) -> tuple[pathlib.Path, pathlib.Path]:
    cert = root / f'{label}-ca.pem'
    key = root / f'{label}-ca.key'
    _openssl(
        'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
        '-subj', f'/CN={label} OC2 test CA',
        '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:0',
        '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
        '-addext', 'subjectKeyIdentifier=hash',
        '-addext', 'authorityKeyIdentifier=keyid:always,issuer',
        '-keyout', str(key), '-out', str(cert),
    )
    return cert, key


def _issue_leaf(
    root: pathlib.Path,
    label: str,
    ca_cert: pathlib.Path,
    ca_key: pathlib.Path,
    san: str,
    *,
    expired: bool = False,
) -> tuple[pathlib.Path, pathlib.Path]:
    key = root / f'{label}.key'
    csr = root / f'{label}.csr'
    cert = root / f'{label}.pem'
    extensions = root / f'{label}.ext'
    extensions.write_text(
        '[server_cert]\n'
        'basicConstraints=critical,CA:FALSE\n'
        'keyUsage=critical,digitalSignature,keyEncipherment\n'
        'extendedKeyUsage=serverAuth\n'
        'subjectKeyIdentifier=hash\n'
        'authorityKeyIdentifier=keyid,issuer\n'
        f'subjectAltName={san}\n',
        encoding='ascii',
    )
    _openssl(
        'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=host.docker.internal',
        '-keyout', str(key), '-out', str(csr),
    )
    if expired:
        index = root / f'{label}-index.txt'
        new_certs = root / f'{label}-new-certs'
        serial = root / f'{label}-serial'
        config = root / f'{label}-ca.cnf'
        index.write_text('', encoding='ascii')
        new_certs.mkdir()
        serial.write_text('1000\n', encoding='ascii')
        config.write_text(
            '[ca]\n'
            'default_ca=local_ca\n'
            '[local_ca]\n'
            f'database={index}\n'
            f'new_certs_dir={new_certs}\n'
            f'certificate={ca_cert}\n'
            f'private_key={ca_key}\n'
            f'serial={serial}\n'
            'default_md=sha256\n'
            'policy=policy_any\n'
            '[policy_any]\n'
            'commonName=supplied\n',
            encoding='ascii',
        )
        _openssl(
            'ca', '-batch', '-config', str(config), '-in', str(csr), '-out', str(cert),
            '-startdate', '20200101000000Z', '-enddate', '20210101000000Z',
            '-extfile', str(extensions), '-extensions', 'server_cert',
        )
    else:
        _openssl(
            'x509', '-req', '-in', str(csr), '-CA', str(ca_cert), '-CAkey', str(ca_key),
            '-CAserial', str(root / f'{label}-serial'), '-CAcreateserial', '-days', '1',
            '-extfile', str(extensions), '-extensions', 'server_cert', '-out', str(cert),
        )
    return cert, key


class CertificateTests(unittest.TestCase):
    root: pathlib.Path
    trusted_ca: pathlib.Path
    trusted_key: pathlib.Path
    other_ca: pathlib.Path
    other_key: pathlib.Path
    valid_cert: pathlib.Path
    valid_key: pathlib.Path
    dns_only_cert: pathlib.Path
    dns_only_key: pathlib.Path
    expired_cert: pathlib.Path
    expired_key: pathlib.Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(tempfile.mkdtemp(prefix='oc2-broker-ca-tests-'))
        cls.trusted_ca, cls.trusted_key = _create_ca(cls.root, 'trusted')
        cls.other_ca, cls.other_key = _create_ca(cls.root, 'other')
        cls.valid_cert, cls.valid_key = _issue_leaf(
            cls.root, 'valid', cls.trusted_ca, cls.trusted_key,
            'DNS:host.docker.internal,IP:127.0.0.1',
        )
        cls.dns_only_cert, cls.dns_only_key = _issue_leaf(
            cls.root, 'dns-only', cls.trusted_ca, cls.trusted_key,
            'DNS:host.docker.internal',
        )
        cls.expired_cert, cls.expired_key = _issue_leaf(
            cls.root, 'expired', cls.trusted_ca, cls.trusted_key,
            'DNS:host.docker.internal,IP:127.0.0.1', expired=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.root)

    def _tls_server(
        self,
        cert: pathlib.Path,
        key: pathlib.Path,
    ) -> tuple[int, threading.Thread, threading.Event, list[OSError]]:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert, keyfile=key)
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(0.1)
        port = listener.getsockname()[1]
        stop = threading.Event()
        errors: list[OSError] = []

        def serve_one() -> None:
            try:
                while not stop.is_set():
                    try:
                        connection, _address = listener.accept()
                    except TimeoutError:
                        continue
                    break
                else:
                    return
                try:
                    with context.wrap_socket(connection, server_side=True):
                        pass
                except OSError as error:
                    errors.append(error)
            finally:
                listener.close()

        thread = threading.Thread(target=serve_one, daemon=True)
        thread.start()
        return port, thread, stop, errors

    def _probe_and_join(self, url: str, ca_data: bytes, cert: pathlib.Path, key: pathlib.Path) -> None:
        port, thread, stop, errors = self._tls_server(cert, key)
        try:
            hb.probe_broker(url.format(port=port), ca_data)
        finally:
            stop.set()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive(), 'TLS fixture server finished')
        self.assertEqual(errors, [])

    def test_ca_loader_returns_exact_bytes_and_sha256(self) -> None:
        result = hb.load_broker_ca(self.trusted_ca)
        data = self.trusted_ca.read_bytes()
        self.assertEqual(result.data, data)
        self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())

    def test_ca_loader_rejects_symlink_nonregular_oversized_and_malformed_files(self) -> None:
        symlink = self.root / 'linked-ca.pem'
        symlink.symlink_to(self.trusted_ca)
        directory = self.root / 'directory-ca.pem'
        directory.mkdir()
        oversized = self.root / 'oversized-ca.pem'
        oversized.write_bytes(b'x' * (64 * 1024 + 1))
        malformed = self.root / 'malformed-ca.pem'
        malformed.write_text('not a PEM certificate', encoding='ascii')
        for candidate in (symlink, directory, oversized, malformed):
            with self.subTest(path=candidate.name), self.assertRaises(hb.HostBrokerError):
                hb.load_broker_ca(candidate)

    def test_ca_loader_rejects_private_key_and_non_certificate_pem_blocks(self) -> None:
        certificate = self.trusted_ca.read_bytes()
        private_key = self.trusted_key.read_bytes()
        public_key = (
            b'-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n'
        )
        for name, contents in (
            ('private-key', certificate + private_key),
            ('public-key', certificate + public_key),
        ):
            candidate = self.root / f'{name}.pem'
            candidate.write_bytes(contents)
            with self.subTest(name=name), self.assertRaises(hb.HostBrokerError):
                hb.load_broker_ca(candidate)

    def test_probe_accepts_trusted_ca_for_an_allowlisted_hostname(self) -> None:
        self._probe_and_join(
            'https://host.docker.internal:{port}/v1', self.trusted_ca.read_bytes(),
            self.valid_cert, self.valid_key,
        )

    def test_probe_rejects_untrusted_ca_wrong_hostname_and_expired_leaf(self) -> None:
        cases = (
            ('https://host.docker.internal:{port}/v1', self.other_ca.read_bytes(), self.valid_cert, self.valid_key),
            ('https://127.0.0.1:{port}/v1', self.trusted_ca.read_bytes(), self.dns_only_cert, self.dns_only_key),
            ('https://host.docker.internal:{port}/v1', self.trusted_ca.read_bytes(), self.expired_cert, self.expired_key),
        )
        for url, ca_data, cert, key in cases:
            port, thread, stop, errors = self._tls_server(cert, key)
            try:
                with self.subTest(url=url, cert=cert.name), self.assertRaises(hb.HostBrokerError):
                    hb.probe_broker(url.format(port=port), ca_data)
            finally:
                stop.set()
                thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), 'TLS fixture server finished')
            self.assertTrue(errors)
            self.assertTrue(all(isinstance(error, (ssl.SSLError, ConnectionResetError)) for error in errors))

    def test_probe_refuses_unreachable_broker_without_fallback(self) -> None:
        def refuse(_address: tuple[str, int], timeout: float) -> socket.socket:
            raise ConnectionRefusedError(timeout)

        with self.assertRaises(hb.HostBrokerError):
            hb.probe_broker(URL, self.trusted_ca.read_bytes(), connect=refuse)

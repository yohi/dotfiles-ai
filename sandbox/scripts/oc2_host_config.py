from __future__ import annotations

from dataclasses import dataclass

DIRECT_QEMU_VM_NAME = 'oc2-f002-probe-recovery'
SSH_HOST = '127.0.0.1'
SSH_PORT = 2223
SSH_USER = 'ubuntu'
PINNED_HOST_KEY_FINGERPRINT = 'SHA256:YVgkTOE0oaHKhbz0kXQYOc2V1qdWME1S/wuo2RsGc5c'


@dataclass(frozen=True, slots=True)
class HostProviderConfig:
    management_mode: str
    vm_name: str
    ssh_host: str
    ssh_port: int
    ssh_user: str
    private_key_path: str
    known_hosts_path: str
    host_key_fingerprint: str

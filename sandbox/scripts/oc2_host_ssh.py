from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sandbox.scripts.oc2_host_config import (
        HostProviderConfig,
        PINNED_HOST_KEY_FINGERPRINT,
        SSH_HOST,
        SSH_PORT,
        SSH_USER,
    )
else:
    from oc2_host_config import (
        PINNED_HOST_KEY_FINGERPRINT,
        SSH_HOST,
        SSH_PORT,
        SSH_USER,
        HostProviderConfig,
    )

POWER_OFF_COMMAND = 'sudo -n /usr/bin/systemctl poweroff --no-wall'


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class CommandRunner(Protocol):
    def run(
        self, argv: tuple[str, ...], *, input_bytes: bytes = b'',
    ) -> CommandResult: ...


@dataclass(frozen=True, slots=True)
class SubprocessCommandRunner:
    timeout_seconds: int = 15

    def run(
        self, argv: tuple[str, ...], *, input_bytes: bytes = b'',
    ) -> CommandResult:
        result = subprocess.run(
            argv,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
            timeout=self.timeout_seconds,
        )
        return CommandResult(result.returncode, result.stdout, result.stderr)


@dataclass(frozen=True, slots=True)
class OpenSshPoweroff:
    runner: CommandRunner

    def poweroff(self, config: HostProviderConfig) -> bool:
        if (
            config.ssh_host != SSH_HOST
            or config.ssh_port != SSH_PORT
            or config.ssh_user != SSH_USER
            or Path(config.private_key_path)
            != Path.home() / 'oc2-f002-kvm-probe' / 'ssh_client_ed25519'
            or not config.known_hosts_path
            or config.host_key_fingerprint != PINNED_HOST_KEY_FINGERPRINT
        ):
            return False
        host_token = f'[{config.ssh_host}]:{config.ssh_port}'
        try:
            keys = self.runner.run((
                '/usr/bin/ssh-keygen', '-F', host_token,
                '-f', config.known_hosts_path,
            ))
            if keys.returncode != 0 or not keys.stdout:
                return False
            fingerprints = self.runner.run(
                ('/usr/bin/ssh-keygen', '-lf', '-'), input_bytes=keys.stdout,
            )
            if (fingerprints.returncode != 0
                    or config.host_key_fingerprint.encode() not in fingerprints.stdout):
                return False
            remote = f'{config.ssh_user}@{config.ssh_host}'
            result = self.runner.run((
                '/usr/bin/ssh', '-i', config.private_key_path,
                '-p', str(config.ssh_port),
                '-o', 'BatchMode=yes',
                '-o', 'IdentitiesOnly=yes',
                '-o', 'StrictHostKeyChecking=yes',
                '-o', f'UserKnownHostsFile={config.known_hosts_path}',
                '-o', 'ClearAllForwardings=yes',
                '-o', 'ConnectTimeout=10',
                '--', remote, POWER_OFF_COMMAND,
            ))
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

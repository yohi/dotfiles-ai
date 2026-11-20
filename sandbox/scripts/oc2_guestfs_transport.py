from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import selectors
import stat
import subprocess
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sandbox.scripts.oc2_offline_preserver import LibguestfsSettings
else:
    from oc2_offline_preserver import LibguestfsSettings

MAX_GUESTFISH_OUTPUT_BYTES = 64 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class GuestfishCommandResult:
    returncode: int
    stdout: bytes


class GuestfishRunner(Protocol):
    def run(
        self,
        argv: tuple[str, ...],
        *,
        settings: LibguestfsSettings,
    ) -> GuestfishCommandResult: ...


@dataclass(frozen=True, slots=True)
class SubprocessGuestfishRunner:
    timeout_seconds: int = 120

    def run(
        self,
        argv: tuple[str, ...],
        *,
        settings: LibguestfsSettings,
    ) -> GuestfishCommandResult:
        if not _valid_guestfish_settings(settings) or not _valid_argv(argv):
            return GuestfishCommandResult(2, b'')
        env = {
            'PATH': '/usr/bin:/bin',
            'HOME': str(settings.tmp_dir),
            'TMPDIR': str(settings.tmp_dir),
            'LC_ALL': 'C',
            **dict(settings.environment()),
        }
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            shell=False,
        )
        output = bytearray()
        deadline = time.monotonic() + self.timeout_seconds
        try:
            stdout = process.stdout
            if stdout is None:
                process.kill()
                process.wait()
                return GuestfishCommandResult(126, b'')
            with stdout, selectors.DefaultSelector() as selector:
                selector.register(stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        process.kill()
                        process.wait()
                        return GuestfishCommandResult(124, b'')
                    chunk = os.read(stdout.fileno(), _READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_GUESTFISH_OUTPUT_BYTES:
                        process.kill()
                        process.wait()
                        return GuestfishCommandResult(125, b'')
            return GuestfishCommandResult(process.wait(), bytes(output))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def _valid_argv(argv: tuple[str, ...]) -> bool:
    return (
        len(argv) >= 8
        and argv[0] == '/usr/bin/guestfish'
        and '--ro' in argv
        and '--format=qcow2' in argv
        and '-w' not in argv
        and argv[-1] == '-'
        and argv[-3] in {'tar-out', 'download'}
    )


def _valid_guestfish_settings(settings: LibguestfsSettings) -> bool:
    kernel = settings.kernel_image
    modules = settings.modules
    cache = settings.cache_dir
    temporary = settings.tmp_dir
    if (
        settings.backend != 'direct'
        or not settings.kernel_version
        or modules != Path('/lib/modules') / settings.kernel_version
        or any(not path.is_absolute() or '..' in path.parts for path in (kernel, modules, cache, temporary))
        or kernel.is_relative_to(Path('/boot'))
    ):
        return False
    try:
        kernel_stat = kernel.lstat()
        modules_stat = modules.lstat()
        cache_stat = cache.lstat()
        temporary_stat = temporary.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(kernel_stat.st_mode)
        and kernel_stat.st_nlink == 1
        and kernel_stat.st_mode & 0o222 == 0
        and stat.S_ISDIR(modules_stat.st_mode)
        and stat.S_ISDIR(cache_stat.st_mode)
        and cache_stat.st_mode & 0o077 == 0
        and stat.S_ISDIR(temporary_stat.st_mode)
        and temporary_stat.st_mode & 0o077 == 0
    )

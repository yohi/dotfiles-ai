from __future__ import annotations

import os
import stat
import sys


def _ensure_private_directory(base: str, target: str) -> None:
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    current = ''
    try:
        for component in target.split('/')[1:]:
            current += '/' + component
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except FileNotFoundError:
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=descriptor)
            if current == base or current.startswith(base + '/'):
                info = os.fstat(child)
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
                    os.close(child)
                    raise OSError('unsafe runtime directory')
                os.fchmod(child, 0o700)
                if stat.S_IMODE(os.fstat(child).st_mode) != 0o700:
                    os.close(child)
                    raise OSError('runtime directory is not private')
            os.close(descriptor)
            descriptor = child
    finally:
        os.close(descriptor)


def prepare(base: str, paths: list[str]) -> None:
    if not base.startswith('/') or '..' in base.split('/'):
        raise ValueError('unsafe runtime root')
    base = os.path.normpath(base)
    for path in paths:
        if not path.startswith('/') or '..' in path.split('/'):
            raise ValueError('runtime directory escaped its root')
        target = os.path.normpath(path)
        if target != base and not target.startswith(base + '/'):
            raise ValueError('runtime directory escaped its root')
        _ensure_private_directory(base, target)


if __name__ == '__main__':
    try:
        prepare(sys.argv[1], sys.argv[2:])
    except (IndexError, OSError, ValueError):
        raise SystemExit('private runtime directory setup failed') from None

from __future__ import annotations

import json
import os
import pathlib
import secrets
import stat

ACCESS = 'oai-oat01-proxy-managed'
REFRESH = 'oai-ort01-proxy-managed'


class BootstrapConfigError(ValueError):
    pass


def record_from_auth(auth):
    if not isinstance(auth, dict) or not isinstance(auth.get('openai'), dict):
        raise ValueError('invalid OAuth source')
    source = auth['openai']
    if (source.get('type') != 'oauth' or source.get('access') != ACCESS
            or source.get('refresh') != REFRESH or type(source.get('expires')) is not int
            or source['expires'] < 0):
        raise ValueError('invalid OAuth sentinel')
    value = {'type': 'oauth', 'methodID': 'chatgpt-browser', 'access': ACCESS,
             'refresh': REFRESH, 'expires': source['expires']}
    metadata = {}
    for source_key, target_key in (('accountId', 'accountID'), ('enterpriseUrl', 'enterpriseUrl')):
        if source_key in source:
            if not isinstance(source[source_key], str):
                raise ValueError('invalid OAuth metadata')
            metadata[target_key] = source[source_key]
    if metadata:
        value['metadata'] = metadata
    return {'id': 'sbx-openai', 'integrationID': 'openai', 'label': 'Sandbox OpenAI',
            'active': True, 'value': value}


def validate_db(path: pathlib.Path) -> None:
    if not path.is_absolute():
        raise ValueError('unsafe database path')
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError('unsafe database path')
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('unsafe database path')
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = pathlib.Path(str(path) + suffix)
        if sidecar.is_symlink() or (sidecar.exists() and
                (not sidecar.is_file() or sidecar.stat().st_nlink != 1)):
            raise ValueError('unsafe database sidecar')


def capture_import_stderr(db_path: pathlib.Path, stderr: bytes) -> pathlib.Path | None:
    tmp_dir = pathlib.Path(os.environ.get('TMPDIR', ''))
    runtime_dir = tmp_dir.parent
    expected_db = runtime_dir / 'home/.local/share/opencode/oc2.db'
    if (not tmp_dir.is_absolute() or tmp_dir != runtime_dir / 'tmp'
            or db_path != expected_db or not hasattr(os, 'O_NOFOLLOW')):
        return None
    if any(path.is_symlink() for path in (tmp_dir, *tmp_dir.parents)):
        return None
    try:
        directory = tmp_dir.stat()
        if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid()
                or stat.S_IMODE(directory.st_mode) != 0o700):
            return None
        destination = tmp_dir / f'oc2-oauth-import-{secrets.token_hex(8)}.stderr'
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            file_info = os.fstat(descriptor)
            if (not stat.S_ISREG(file_info.st_mode) or file_info.st_uid != os.geteuid()
                    or stat.S_IMODE(file_info.st_mode) != 0o600 or file_info.st_nlink != 1):
                raise OSError('unsafe capture file')
            with os.fdopen(descriptor, 'wb', closefd=False) as output:
                output.write(stderr)
                output.flush()
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return destination
    except OSError:
        return None


def create(base_config: pathlib.Path, runtime_dir: pathlib.Path) -> pathlib.Path:
    expected_base = runtime_dir / 'config/opencode/opencode.jsonc'
    if (not runtime_dir.is_absolute() or base_config != expected_base
            or any(path.is_symlink() for path in (base_config, *base_config.parents))):
        raise BootstrapConfigError('unsafe bootstrap config source')
    try:
        runtime_info = runtime_dir.stat()
        source_info = base_config.lstat()
        if (not stat.S_ISDIR(runtime_info.st_mode) or runtime_info.st_uid != os.geteuid()
                or stat.S_IMODE(runtime_info.st_mode) != 0o700
                or not stat.S_ISREG(source_info.st_mode) or base_config.is_symlink()
                or source_info.st_uid != os.geteuid() or source_info.st_nlink != 1):
            raise BootstrapConfigError('unsafe bootstrap config source')
        base = json.loads(base_config.read_bytes())
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        if isinstance(error, BootstrapConfigError):
            raise
        raise BootstrapConfigError('bootstrap base config is unavailable or invalid') from None
    if not isinstance(base, dict) or not isinstance(base.get('policies'), list):
        raise BootstrapConfigError('bootstrap base policy is unavailable')
    policies = base['policies']
    if any(not isinstance(policy, dict) for policy in policies):
        raise BootstrapConfigError('bootstrap base policy is invalid')
    connect = [policy for policy in policies if policy.get('action') == 'integration.connect']
    deny_all = {'action': 'integration.connect', 'resource': '*', 'effect': 'deny'}
    if connect != [deny_all]:
        raise BootstrapConfigError('bootstrap base connect policy is not the expected deny-all rule')

    bootstrap = dict(base)
    bootstrap['policies'] = [
        *policies,
    ]
    deny_index = bootstrap['policies'].index(deny_all)
    bootstrap['policies'].insert(
        deny_index + 1,
        {'action': 'integration.connect', 'resource': 'openai', 'effect': 'allow'},
    )
    destination = runtime_dir / 'oauth-bootstrap'
    if destination.exists() or destination.is_symlink():
        raise BootstrapConfigError('bootstrap destination already exists')
    created = False
    try:
        os.mkdir(destination, 0o700)
        created = True
        directory_info = destination.lstat()
        if (not stat.S_ISDIR(directory_info.st_mode) or directory_info.st_uid != os.geteuid()
                or stat.S_IMODE(directory_info.st_mode) != 0o700):
            raise OSError('unsafe bootstrap directory')
        os.mkdir(destination / 'node_modules', 0o700)
        dependency_info = (destination / 'node_modules').lstat()
        if (not stat.S_ISDIR(dependency_info.st_mode)
                or dependency_info.st_uid != os.geteuid()
                or stat.S_IMODE(dependency_info.st_mode) != 0o700):
            raise OSError('unsafe bootstrap dependency directory')
        _write_private(destination / 'opencode.jsonc',
                       (json.dumps(bootstrap, indent=2) + '\n').encode('utf-8'))
        return destination
    except OSError:
        if created:
            try:
                cleanup(destination, runtime_dir)
            except BootstrapConfigError:
                raise BootstrapConfigError('bootstrap config creation and cleanup failed') from None
        raise BootstrapConfigError('bootstrap config could not be created') from None


def _write_private(path: pathlib.Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise OSError('unsafe bootstrap config file')
        with os.fdopen(descriptor, 'wb', closefd=False) as output:
            output.write(content)
            output.flush()
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def cleanup(directory: pathlib.Path, runtime_dir: pathlib.Path) -> None:
    expected = runtime_dir / 'oauth-bootstrap'
    if (directory != expected or directory.is_symlink()
            or any(path.is_symlink() for path in (runtime_dir, *runtime_dir.parents))):
        raise BootstrapConfigError('unsafe bootstrap cleanup path')
    if not directory.exists():
        return
    try:
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise BootstrapConfigError('unsafe bootstrap cleanup directory')
        entries = {entry.name for entry in directory.iterdir()}
        if entries - {'opencode.jsonc', 'node_modules'}:
            raise BootstrapConfigError('unexpected bootstrap cleanup contents')
        config = directory / 'opencode.jsonc'
        if config.exists() or config.is_symlink():
            file_info = config.lstat()
            if (not stat.S_ISREG(file_info.st_mode) or config.is_symlink()
                    or file_info.st_uid != os.geteuid()
                    or stat.S_IMODE(file_info.st_mode) != 0o600 or file_info.st_nlink != 1):
                raise BootstrapConfigError('unsafe bootstrap config cleanup file')
            config.unlink()
        dependencies = directory / 'node_modules'
        if dependencies.exists() or dependencies.is_symlink():
            dependency_info = dependencies.lstat()
            if (not stat.S_ISDIR(dependency_info.st_mode) or dependencies.is_symlink()
                    or dependency_info.st_uid != os.geteuid()
                    or stat.S_IMODE(dependency_info.st_mode) != 0o700
                    or any(dependencies.iterdir())):
                raise BootstrapConfigError('unsafe bootstrap dependency cleanup directory')
            dependencies.rmdir()
        directory.rmdir()
    except OSError:
        raise BootstrapConfigError('bootstrap config cleanup failed') from None

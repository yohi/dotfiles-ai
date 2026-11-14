"""OC2 Alternative A: Writer Container lifecycle foundation.

This module builds, validates, launches and stops the per-Session Writer
Container described in Design R0.2 sections 6 ("Session Writer execution
boundary"), 10.1 (stop / stop verification order) and 10.4 (constraints).

Scope and non-goals (fixed by the Owner decision for this task):

* Only the Trusted Supervisor side of Writer launch/stop is modelled.
  Docker access goes through an injected ``DockerRunner``; host-side
  observation goes through an injected ``HostProbe``.  No real
  implementations of either are provided here.
* No Relay, no Collector, no Collection Digest, no ApplyAuthorization, no
  Host Apply and no Receipt v3 persistence are implemented here.
* A ``STOPPED_VERIFIED`` verdict is NOT a sufficient condition for
  Collection consistency or Git tree immutability.  Tree scans, Git
  transaction checks and Collector re-verification are later Collector
  tasks.  This module never issues a Collection Digest.
* There is intentionally no restart / start-existing / exec operation.
  A stopped Writer is never reused (Design 10.1: ``--restart no``).

All policy constants below are initial policy values chosen for the first
implementation.  They are NOT proven safe values; Design 10.4 lists the
evidence as feasibility-only.

Error messages are printable ASCII and never contain environment variable
VALUES or raw runner output.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import posixpath
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

# --- Initial policy constants (not proven safe values) ---------------------

WRITER_UID = 10001
WRITER_GID = 10001
PIDS_LIMIT = 256
MEMORY = '6g'
MEMORY_BYTES = 6 * 1024 * 1024 * 1024
STOP_TIMEOUT_S = 15
QUIESCE_OBSERVE_S = 20
SCHEMA = 'dotfiles-ai/oc2-writer/v1'
GUEST_SESSION_ROOT = '/home/agent/workspace/oc2/sessions'

#: Timeout (seconds) handed to the runner for short docker commands.
DOCKER_CMD_TIMEOUT_S = 60
#: Runner timeout for ``docker stop`` (stop grace period plus margin).
DOCKER_STOP_RUNNER_TIMEOUT_S = STOP_TIMEOUT_S + 30

WRITER_WORKDIR = '/workspace'
WRITER_USER = f'{WRITER_UID}:{WRITER_GID}'
TMPFS_TMP_OPTS = (
    f'rw,nosuid,nodev,noexec,size=64m,uid={WRITER_UID},gid={WRITER_GID},mode=0700'
)
#: ``exec`` is required: OpenTUI loads a native library from the home
#: directory (documented constraint, Design 10.4).
TMPFS_HOME_OPTS = (
    f'rw,exec,nosuid,nodev,size=1g,uid={WRITER_UID},gid={WRITER_GID},mode=0700'
)
EXPECTED_TMPFS = {
    # The tmpfs is owner-only (uid/gid 10001, mode 0700) and noexec; inspect
    # validation rejects any permission drift. Sonar cannot see Docker's options.
    '/tmp': TMPFS_TMP_OPTS,  # NOSONAR - private tmpfs, not the host's public /tmp
    '/home/writer': TMPFS_HOME_OPTS,
}

STATUS_STOPPED_VERIFIED = 'STOPPED_VERIFIED'
STATUS_GUEST_QUIESCENCE_UNVERIFIED = 'GUEST_QUIESCENCE_UNVERIFIED'

LABEL_SCHEMA = 'dev.oc2.schema'
LABEL_ROLE = 'dev.oc2.role'
LABEL_WORKSPACE = 'dev.oc2.workspace-id'
LABEL_SANDBOX = 'dev.oc2.sandbox-id'
LABEL_GENERATION = 'dev.oc2.session-generation'
LABEL_PREFIX = 'dev.oc2.'

ENV_ALLOWLIST = frozenset({
    'HOME', 'USER', 'PATH', 'TERM', 'LANG', 'TMPDIR',
    'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
    'OPENCODE_DB', 'OPENCODE_DISABLE_AUTOUPDATE',
    'OPENCODE_DISABLE_MODELS_FETCH', 'OPENCODE_CONFIG_PROJECT_DISABLE',
})
_FORBIDDEN_ENV_FRAGMENTS = ('PROXY', 'TOKEN', 'KEY', 'SECRET', 'PASSWORD', 'AUTH')
_FORBIDDEN_SOCKETS = ('docker.sock', 'containerd.sock', 'podman.sock')
_FORBIDDEN_PATH_ROOTS = ('/run', '/var/run')

_WORKSPACE_ID_RE = re.compile(r'^[0-9a-f]{32}$')
_CONTAINER_ID_RE = re.compile(r'^[0-9a-f]{64}$')
_IMAGE_ID_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
_ENV_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')
_NAME_COMPONENT = r'[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*'
_IMAGE_REF_RE = re.compile(
    r'^(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::[0-9]{1,5})?/)?'
    + _NAME_COMPONENT + r'(?:/' + _NAME_COMPONENT + r')*'
    + r'@sha256:[0-9a-f]{64}$'
)
_UNSET_TIME = '0001-01-01T00:00:00Z'


class WriterError(Exception):
    """Fail-closed Writer lifecycle error.

    Messages never contain environment variable values or raw runner output.
    """


# --- Identity ----------------------------------------------------------------

def _is_canonical_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return str(parsed) == value


def _is_uuid4(value: object) -> bool:
    if not _is_canonical_uuid(value):
        return False
    parsed = uuid.UUID(str(value))
    return parsed.version == 4 and parsed.variant == uuid.RFC_4122


@dataclasses.dataclass(frozen=True)
class WriterSessionKey:
    """SessionKey = (WorkspaceID, SandboxID, SessionGeneration), Design R0.2 6."""

    workspace_id: str
    sandbox_id: str
    session_generation: str

    def validate(self) -> None:
        """Reject empty or malformed key parts (fail closed)."""
        if not isinstance(self.workspace_id, str) or not _WORKSPACE_ID_RE.match(
                self.workspace_id):
            raise WriterError('invalid workspace_id: expected 32 lowercase hex')
        if not _is_canonical_uuid(self.sandbox_id):
            raise WriterError('invalid sandbox_id: expected canonical lowercase UUID')
        if not _is_uuid4(self.session_generation):
            raise WriterError(
                'invalid session_generation: expected canonical lowercase UUID v4')


def compute_workspace_id(uid: int, canonical_git_root: str) -> str:
    """Return WorkspaceID per Design R0.2 section 6.

    Design formula: ``sha256(uid || NUL || canonical_host_git_root)``, first
    32 hex digits.

    PROVISIONAL byte encoding (the Design does not pin it): ``uid`` is
    encoded as its decimal ASCII representation, the separator is a single
    NUL byte, and the root is encoded as UTF-8.  No extra domain-separation
    prefix is added so that the Design formula is followed literally.

    ``canonical_git_root`` must already be the resolved (realpath) Git root;
    this function only checks the lexical canonical form (absolute,
    normalized, no trailing slash, no NUL) and does not touch the filesystem.
    """
    if isinstance(uid, bool) or not isinstance(uid, int) or uid < 0:
        raise WriterError('invalid uid: expected non-negative integer')
    root = canonical_git_root
    if not isinstance(root, str) or not root:
        raise WriterError('invalid git root: expected non-empty string')
    if '\x00' in root:
        raise WriterError('invalid git root: contains NUL')
    if not root.startswith('/'):
        raise WriterError('invalid git root: must be absolute')
    if root.startswith('//') or posixpath.normpath(root) != root:
        raise WriterError('invalid git root: not in canonical form')
    payload = str(uid).encode('ascii') + b'\x00' + root.encode('utf-8')
    return hashlib.sha256(payload).hexdigest()[:32]


# --- Spec ------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class WriterSpec:
    """Writer launch request.  ``env`` is excluded from repr (no values)."""

    key: WriterSessionKey
    image_ref: str
    repo_source: str
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = dataclasses.field(repr=False)
    tty: bool = False


def expected_repo_source(key: WriterSessionKey) -> str:
    """Return the only acceptable Session repository path for ``key``."""
    return f'{GUEST_SESSION_ROOT}/{key.session_generation}/repo'


def writer_container_name(key: WriterSessionKey) -> str:
    """Return ``oc2-writer-<ws[:12]>-<generation hex>`` for ``key``."""
    key.validate()
    return 'oc2-writer-{}-{}'.format(
        key.workspace_id[:12], key.session_generation.replace('-', ''))


def writer_labels(key: WriterSessionKey) -> dict[str, str]:
    """Return exactly the 5 Writer labels for ``key``."""
    key.validate()
    return {
        LABEL_SCHEMA: SCHEMA,
        LABEL_ROLE: 'writer',
        LABEL_WORKSPACE: key.workspace_id,
        LABEL_SANDBOX: key.sandbox_id,
        LABEL_GENERATION: key.session_generation,
    }


def _safe_env_name(name: object) -> str:
    """Return ``name`` for messages only if it is a plain identifier."""
    if isinstance(name, str) and _ENV_NAME_RE.match(name):
        return name
    return '<invalid name>'


def _env_name_forbidden(name: str) -> bool:
    upper = name.upper()
    return upper.endswith('_PROXY') or any(f in upper for f in _FORBIDDEN_ENV_FRAGMENTS)


def _check_env_name_rules(name: object, *, require_allowlist: bool) -> str | None:
    """Return a reason string if ``name`` violates the env name rules."""
    if not isinstance(name, str) or not _ENV_NAME_RE.match(name):
        return 'malformed env name'
    if _env_name_forbidden(name):
        return f'forbidden env name: {name}'
    if require_allowlist and name not in ENV_ALLOWLIST:
        return f'env name not in allowlist: {name}'
    return None


def validate_writer_spec(spec: WriterSpec) -> None:
    """Validate ``spec`` strictly; raise ``WriterError`` on any problem."""
    if not isinstance(spec, WriterSpec):
        raise WriterError('invalid spec type')
    if not isinstance(spec.key, WriterSessionKey):
        raise WriterError('invalid session key type')
    spec.key.validate()
    if not isinstance(spec.image_ref, str) or not _IMAGE_REF_RE.match(spec.image_ref):
        raise WriterError('image_ref must be <name>@sha256:<64 hex>')
    if not isinstance(spec.repo_source, str) or spec.repo_source != expected_repo_source(
            spec.key):
        raise WriterError(
            'repo_source must equal GUEST_SESSION_ROOT/<session_generation>/repo')
    if not isinstance(spec.command, tuple) or not spec.command:
        raise WriterError('command must be a non-empty tuple')
    for arg in spec.command:
        if not isinstance(arg, str) or not arg or '\x00' in arg:
            raise WriterError('command elements must be non-empty strings without NUL')
    if not isinstance(spec.tty, bool):
        raise WriterError('tty must be bool')
    if not isinstance(spec.env, tuple):
        raise WriterError('env must be a tuple of (name, value) pairs')
    seen: set[str] = set()
    for pair in spec.env:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise WriterError('env entries must be (name, value) pairs')
        name, value = pair
        reason = _check_env_name_rules(name, require_allowlist=True)
        if reason:
            raise WriterError(reason)
        if name in seen:
            raise WriterError(f'duplicate env name: {name}')
        seen.add(name)
        if not isinstance(value, str) or '\x00' in value:
            raise WriterError(f'invalid env value type or NUL for: {name}')


def validate_container_id(cid: object) -> str:
    """Accept only a full 64 lowercase hex container ID.

    Names, short IDs, empty strings and option-like strings are rejected.
    """
    if not isinstance(cid, str) or not _CONTAINER_ID_RE.match(cid):
        raise WriterError('invalid container id: expected 64 lowercase hex')
    return cid


# --- argv builders -----------------------------------------------------------------

def build_create_argv(spec: WriterSpec) -> list[str]:
    """Return the ``docker create`` argv for a validated ``spec``."""
    validate_writer_spec(spec)
    argv = [
        'docker', 'create',
        '--name', writer_container_name(spec.key),
        '--user', WRITER_USER,
        '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges',
        '--read-only',
        '--pids-limit', str(PIDS_LIMIT),
        '--memory', MEMORY,
        '--restart', 'no',
        '--network', 'none',
        '--ipc', 'private',
        '--cgroupns', 'private',
        '--tmpfs', '/tmp:' + TMPFS_TMP_OPTS,
        '--tmpfs', '/home/writer:' + TMPFS_HOME_OPTS,
        '-v', f'{spec.repo_source}:{WRITER_WORKDIR}:rw',
        '-w', WRITER_WORKDIR,
    ]
    for name, value in writer_labels(spec.key).items():
        argv += ['--label', f'{name}={value}']
    for name, value in spec.env:
        argv += ['-e', f'{name}={value}']
    if spec.tty:
        argv.append('-t')
    argv.append(spec.image_ref)
    argv.extend(spec.command)
    return argv


def build_start_argv(cid: str) -> list[str]:
    """Return ``docker start <id>`` (no attach) for a validated ID."""
    return ['docker', 'start', validate_container_id(cid)]


def build_stop_argv(cid: str, timeout: int = STOP_TIMEOUT_S) -> list[str]:
    """Return ``docker stop --timeout N <id>`` (TERM, then KILL by docker)."""
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
        raise WriterError('invalid stop timeout')
    return ['docker', 'stop', '--timeout', str(timeout), validate_container_id(cid)]


def build_kill_argv(cid: str) -> list[str]:
    """Return ``docker kill --signal KILL <id>`` for a validated ID."""
    return ['docker', 'kill', '--signal', 'KILL', validate_container_id(cid)]


def build_inspect_argv(cid: str) -> list[str]:
    """Return ``docker inspect --type container <id>`` for a validated ID."""
    return ['docker', 'inspect', '--type', 'container', validate_container_id(cid)]


LIST_ALL_ARGV = ('docker', 'ps', '-a', '-q', '--no-trunc')


# --- inspect helpers -----------------------------------------------------------------

_MISSING = object()


def _get(obj: Any, *path: str) -> Any:
    """Return the nested value or ``_MISSING`` when a key is absent.

    An explicit ``None`` is preserved; callers must not interpret missing or
    unknown data as proof that a container or process is absent.
    """
    cur = obj
    for part in path:
        if not isinstance(cur, Mapping) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, (list, dict, tuple)) and len(value) == 0)


def _strip_name(value: Any) -> Any:
    if isinstance(value, str) and value.startswith('/'):
        return value[1:]
    return value


def _path_forbidden(path: Any) -> bool:
    if not isinstance(path, str):
        return True
    if any(sock in path for sock in _FORBIDDEN_SOCKETS):
        return True
    norm = posixpath.normpath(path) if path else path
    return any(norm == root or norm.startswith(root + '/') for root in _FORBIDDEN_PATH_ROOTS)


def parse_inspect_output(stdout: str) -> dict[str, Any]:
    """Parse ``docker inspect`` stdout (a JSON array of exactly one object)."""
    try:
        data = json.loads(stdout)
    except (TypeError, ValueError) as exc:
        raise WriterError('malformed docker inspect output') from exc
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise WriterError('unexpected docker inspect output shape')
    return data[0]


def validate_writer_inspect(inspect: Mapping[str, Any], spec: WriterSpec) -> None:
    """Strictly validate a container inspect against ``spec`` (fail closed).

    Tolerated docker 29 forms: ``Name`` with a leading slash, ``Tmpfs`` as a
    dict, top-level ``Mounts`` list.  Security checks are not loosened.

    Labels: the 5 ``dev.oc2.*`` labels must match exactly and no other
    ``dev.oc2.*`` label may exist.  Other labels (merged from the image by
    Docker) are tolerated because Docker merges image labels into the
    container config.

    Env: every ``Config.Env`` entry (including image-derived defaults such as
    ``PATH``) must pass the forbidden-name rules (proxy / credential-like
    names); image-derived names outside the spec allowlist are tolerated
    only when they pass those rules.  Every spec env pair must be present
    with its exact value.  Values are never included in error messages.
    """
    validate_writer_spec(spec)
    if not isinstance(inspect, Mapping):
        raise WriterError('inspect is not an object')
    problems: list[str] = []

    def expect(path: tuple[str, ...], ok: Callable[[Any], bool], what: str) -> None:
        value = _get(inspect, *path)
        if value is _MISSING:
            problems.append('missing ' + '.'.join(path))
        elif not ok(value):
            problems.append(what)

    expect(('Id',), lambda v: isinstance(v, str) and bool(_CONTAINER_ID_RE.match(v)),
           'Id is not a 64 hex container id')
    expect(('Name',), lambda v: _strip_name(v) == writer_container_name(spec.key),
           'container Name mismatch')
    expect(('Image',), lambda v: isinstance(v, str) and bool(_IMAGE_ID_RE.match(v)),
           'Image id is not sha256:<64 hex>')
    expect(('Config', 'Image'), lambda v: v == spec.image_ref, 'Config.Image mismatch')
    expect(('Config', 'User'), lambda v: v == WRITER_USER,
           'Config.User must be 10001:10001')
    expect(('Config', 'Cmd'), lambda v: isinstance(v, list) and v == list(spec.command),
           'Config.Cmd mismatch')
    expect(('Config', 'WorkingDir'), lambda v: v == WRITER_WORKDIR,
           'Config.WorkingDir mismatch')
    expect(('Config', 'Tty'), lambda v: v is spec.tty, 'Config.Tty mismatch')

    hc = ('HostConfig',)
    expect(hc + ('Privileged',), lambda v: v is False, 'Privileged must be false')
    expect(hc + ('CapDrop',), lambda v: v == ['ALL'], 'CapDrop must be [ALL]')
    expect(hc + ('CapAdd',), _is_empty, 'CapAdd must be empty')
    expect(hc + ('SecurityOpt',),
           lambda v: v in (['no-new-privileges'], ['no-new-privileges:true']),
           'SecurityOpt must be exactly no-new-privileges')
    expect(hc + ('ReadonlyRootfs',), lambda v: v is True, 'ReadonlyRootfs must be true')
    expect(hc + ('PidsLimit',),
           lambda v: not isinstance(v, bool) and v == PIDS_LIMIT,
           'PidsLimit must be 256')
    expect(hc + ('RestartPolicy', 'Name'), lambda v: v == 'no',
           'RestartPolicy.Name must be no')
    expect(hc + ('RestartPolicy', 'MaximumRetryCount'),
           lambda v: not isinstance(v, bool) and v == 0,
           'RestartPolicy.MaximumRetryCount must be 0')
    expect(hc + ('NetworkMode',), lambda v: v == 'none', 'NetworkMode must be none')
    expect(hc + ('PidMode',), lambda v: v == '', 'PidMode must be empty')
    expect(hc + ('UsernsMode',), lambda v: v == '', 'UsernsMode must be empty')
    expect(hc + ('IpcMode',), lambda v: v == 'private', 'IpcMode must be private')
    expect(hc + ('CgroupnsMode',), lambda v: v == 'private',
           'CgroupnsMode must be private')
    for field in ('Devices', 'GroupAdd', 'ExtraHosts', 'Dns', 'PortBindings'):
        expect(hc + (field,), _is_empty, field + ' must be empty')
    expect(hc + ('AutoRemove',), lambda v: v is False, 'AutoRemove must be false')
    expect(hc + ('Memory',), lambda v: not isinstance(v, bool) and v == MEMORY_BYTES,
           'Memory must be 6g')
    for optional in ('Mounts', 'VolumesFrom'):
        value = _get(inspect, 'HostConfig', optional)
        if value is not _MISSING and not _is_empty(value):
            problems.append('HostConfig.' + optional + ' must be empty')
    networks = _get(inspect, 'NetworkSettings', 'Networks')
    if networks is not _MISSING and networks is not None:
        if not isinstance(networks, Mapping) or not set(networks) <= {'none'}:
            problems.append('NetworkSettings.Networks must only contain none')

    expected_bind = f'{spec.repo_source}:{WRITER_WORKDIR}:rw'
    binds = _get(inspect, 'HostConfig', 'Binds')
    if binds is _MISSING:
        problems.append('missing HostConfig.Binds')
    elif binds != [expected_bind]:
        problems.append('HostConfig.Binds must be exactly the repo bind')
    if isinstance(binds, list):
        for bind in binds:
            src = bind.split(':', 1)[0] if isinstance(bind, str) else None
            if _path_forbidden(src):
                problems.append('forbidden bind source')

    tmpfs = _get(inspect, 'HostConfig', 'Tmpfs')
    if tmpfs is _MISSING:
        problems.append('missing HostConfig.Tmpfs')
    elif not isinstance(tmpfs, Mapping) or dict(tmpfs) != EXPECTED_TMPFS:
        problems.append('HostConfig.Tmpfs mismatch')
    if isinstance(tmpfs, Mapping):
        for dest in tmpfs:
            if _path_forbidden(dest):
                problems.append('forbidden tmpfs destination')

    mounts = _get(inspect, 'Mounts')
    if mounts is _MISSING:
        problems.append('missing Mounts')
    elif not isinstance(mounts, list):
        problems.append('Mounts is not a list')
    else:
        for mount in mounts:
            if not isinstance(mount, Mapping):
                problems.append('malformed Mounts entry')
                continue
            if _path_forbidden(mount.get('Source')) or _path_forbidden(
                    mount.get('Destination')):
                problems.append('forbidden mount path (socket or /run)')
        ok_bind = (
            len(mounts) == 1 and isinstance(mounts[0], Mapping)
            and mounts[0].get('Type') == 'bind'
            and mounts[0].get('Source') == spec.repo_source
            and mounts[0].get('Destination') == WRITER_WORKDIR
            and mounts[0].get('RW') is True
            and mounts[0].get('Propagation', '') in ('', 'rprivate')
        )
        if not ok_bind:
            problems.append('Mounts must be exactly one rw bind of repo_source')

    labels = _get(inspect, 'Config', 'Labels')
    if labels is _MISSING or not isinstance(labels, Mapping):
        problems.append('missing Config.Labels')
    else:
        expected_labels = writer_labels(spec.key)
        ours = {k: v for k, v in labels.items()
                if isinstance(k, str) and k.startswith(LABEL_PREFIX)}
        if ours != expected_labels:
            problems.append('Config.Labels mismatch')

    env = _get(inspect, 'Config', 'Env')
    if env is _MISSING or not isinstance(env, list):
        problems.append('missing Config.Env')
    else:
        parsed: dict[str, str] = {}
        for entry in env:
            if not isinstance(entry, str) or '=' not in entry:
                problems.append('malformed Config.Env entry')
                continue
            name, value = entry.split('=', 1)
            reason = _check_env_name_rules(name, require_allowlist=False)
            if reason:
                problems.append('Config.Env ' + reason)
                continue
            if name in parsed:
                problems.append('duplicate Config.Env name: ' + name)
            parsed[name] = value
        for name, value in spec.env:
            if parsed.get(name) != value:
                problems.append('Config.Env value mismatch for: ' + name)

    if problems:
        raise WriterError('writer inspect rejected: ' + '; '.join(problems))


def check_no_conflict(existing: Sequence[Mapping[str, Any]], spec: WriterSpec) -> None:
    """Reject if any existing container (running or exited) conflicts.

    Conflict = same container name, same session-generation label, or a RW
    bind of the same repo_source.  Malformed entries fail closed.
    """
    validate_writer_spec(spec)
    name = writer_container_name(spec.key)
    generation = spec.key.session_generation
    for item in existing:
        if not isinstance(item, Mapping):
            raise WriterError('conflict check: malformed container entry')
        other_name = _get(item, 'Name')
        if not isinstance(other_name, str):
            raise WriterError('conflict check: container entry without Name')
        if _strip_name(other_name) == name:
            raise WriterError('conflict: container with the same name exists')
        labels = _get(item, 'Config', 'Labels')
        if labels is _MISSING:
            raise WriterError('conflict check: container entry without Config.Labels')
        if labels is not None and not isinstance(labels, Mapping):
            raise WriterError('conflict check: malformed Config.Labels')
        if labels and labels.get(LABEL_GENERATION) == generation:
            raise WriterError('conflict: container with the same session generation exists')
        mounts = _get(item, 'Mounts')
        if mounts is _MISSING or (mounts is not None and not isinstance(mounts, list)):
            raise WriterError('conflict check: container entry without Mounts list')
        for mount in mounts or []:
            if not isinstance(mount, Mapping):
                raise WriterError('conflict check: malformed Mounts entry')
            src = mount.get('Source')
            if isinstance(src, str) and posixpath.normpath(src) == spec.repo_source \
                    and mount.get('RW') is not False:
                raise WriterError('conflict: repo_source is bound RW by another container')
        binds = _get(item, 'HostConfig', 'Binds')
        if isinstance(binds, list):
            for bind in binds:
                if not isinstance(bind, str):
                    continue
                parts = bind.split(':')
                opts = parts[2].split(',') if len(parts) > 2 else []
                if posixpath.normpath(parts[0]) == spec.repo_source and 'ro' not in opts:
                    raise WriterError(
                        'conflict: repo_source is bound RW by another container')


# --- Identity / stop verification ----------------------------------------------

@dataclasses.dataclass(frozen=True)
class WriterIdentity:
    """Identity of a started Writer, bound to a single boot."""

    container_id: str
    image_id: str
    started_at: str
    cgroup_inode: int
    boot_id: str


@dataclasses.dataclass(frozen=True)
class StopObservation:
    """Host-side observation; ``None`` means unknown (never success)."""

    cgroup_exists: bool | None
    writer_uid_pids: tuple[int, ...] | None
    rw_mount_holders: tuple[str, ...] | None
    boot_id: str | None


@dataclasses.dataclass(frozen=True)
class StopVerdict:
    """Result of Writer stop verification.

    ``STOPPED_VERIFIED`` is NOT a sufficient condition for Collection
    consistency or Git tree immutability (tree scans, Git transaction checks
    and Collector re-verification are a later Collector task).  This module
    never issues a Collection Digest.
    """

    status: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status == STATUS_STOPPED_VERIFIED:
            if self.reasons:
                raise WriterError('STOPPED_VERIFIED must not carry reasons')
        elif self.status == STATUS_GUEST_QUIESCENCE_UNVERIFIED:
            if not self.reasons:
                raise WriterError('GUEST_QUIESCENCE_UNVERIFIED requires reasons')
        else:
            raise WriterError('invalid stop verdict status')

    @property
    def verified(self) -> bool:
        return self.status == STATUS_STOPPED_VERIFIED


def _unverified(reasons: Sequence[str]) -> StopVerdict:
    return StopVerdict(STATUS_GUEST_QUIESCENCE_UNVERIFIED,
                       tuple(reasons) or ('unknown failure',))


class DockerRunner(Protocol):
    """Runs a docker argv; returns (returncode, stdout)."""

    def run(self, argv: Sequence[str], *, timeout: int) -> tuple[int, str]: ...


class HostProbe(Protocol):
    """Host-side probes (no real implementation in this task)."""

    def cgroup_inode(self, cid: str) -> int | None: ...

    def observe(self, identity: WriterIdentity) -> StopObservation: ...

    def boot_id(self) -> str | None: ...


def capture_identity(inspect: Mapping[str, Any], probe: HostProbe) -> WriterIdentity:
    """Capture WriterIdentity from a running inspect plus host probes."""
    if not isinstance(inspect, Mapping):
        raise WriterError('identity: inspect is not an object')
    cid = _get(inspect, 'Id')
    image_id = _get(inspect, 'Image')
    started_at = _get(inspect, 'State', 'StartedAt')
    if not isinstance(cid, str) or not _CONTAINER_ID_RE.match(cid):
        raise WriterError('identity: missing or invalid container id')
    if not isinstance(image_id, str) or not _IMAGE_ID_RE.match(image_id):
        raise WriterError('identity: missing or invalid image id')
    if not isinstance(started_at, str) or not started_at or started_at == _UNSET_TIME:
        raise WriterError('identity: missing StartedAt')
    try:
        inode = probe.cgroup_inode(cid)
        boot = probe.boot_id()
    except Exception as exc:  # probe failures fail closed
        raise WriterError('identity: host probe failed') from exc
    if isinstance(inode, bool) or not isinstance(inode, int) or inode <= 0:
        raise WriterError('identity: missing cgroup inode')
    if not isinstance(boot, str) or not boot.strip():
        raise WriterError('identity: missing boot id')
    return WriterIdentity(cid, image_id, started_at, inode, boot)


def _check_stopped_inspect(label: str, inspect: Any, before: WriterIdentity) -> list[str]:
    """Compare Docker inspect with the identity and required stopped state.

    Return one reason per missing or mismatched field. The list is empty only
    when all checks pass; unavailable or unknown fields do not prove absence.
    """
    if not isinstance(inspect, Mapping):
        return [f'{label}: inspect unavailable']
    reasons = []
    checks = (
        (('State', 'Status'), lambda v: v == 'exited', 'Status is not exited'),
        (('State', 'Running'), lambda v: v is False, 'Running is not false'),
        (('State', 'Pid'), lambda v: not isinstance(v, bool) and v == 0, 'Pid is not 0'),
        (('RestartCount',), lambda v: not isinstance(v, bool) and v == 0,
         'RestartCount is not 0'),
        (('HostConfig', 'RestartPolicy', 'Name'), lambda v: v == 'no',
         'RestartPolicy is not no'),
        (('Id',), lambda v: v == before.container_id, 'container Id changed'),
        (('State', 'StartedAt'), lambda v: v == before.started_at, 'StartedAt changed'),
        (('Image',), lambda v: v == before.image_id, 'Image id changed'),
    )
    for path, ok, what in checks:
        value = _get(inspect, *path)
        if value is _MISSING:
            reasons.append(f'{label}: missing ' + '.'.join(path))
        elif not ok(value):
            reasons.append(f'{label}: {what}')
    return reasons


def _check_observation(label: str, obs: Any, before: WriterIdentity) -> list[str]:
    """Return reasons an observation cannot prove quiescence.

    The list is empty only when every value is known and confirms the expected
    stopped state. Unknown values differ from affirmative absence and add a
    failure reason.
    """
    if not isinstance(obs, StopObservation):
        return [f'{label}: observation unavailable']
    reasons = []
    if obs.cgroup_exists is None:
        reasons.append(f'{label}: cgroup state unknown')
    elif obs.cgroup_exists is not False:
        reasons.append(f'{label}: writer cgroup still exists')
    if obs.writer_uid_pids is None:
        reasons.append(f'{label}: writer uid processes unknown')
    elif not isinstance(obs.writer_uid_pids, tuple) or obs.writer_uid_pids:
        reasons.append(f'{label}: writer uid processes remain')
    if obs.rw_mount_holders is None:
        reasons.append(f'{label}: rw mount holders unknown')
    elif not isinstance(obs.rw_mount_holders, tuple) or obs.rw_mount_holders:
        reasons.append(f'{label}: rw mount holders remain')
    if obs.boot_id is None:
        reasons.append(f'{label}: boot id unknown')
    elif obs.boot_id != before.boot_id:
        reasons.append(f'{label}: boot id changed')
    return reasons


def verify_writer_stopped(before: WriterIdentity,
                          inspect_now: Mapping[str, Any] | None,
                          inspect_after_wait: Mapping[str, Any] | None,
                          obs_now: StopObservation | None,
                          obs_after_wait: StopObservation | None) -> StopVerdict:
    """Return STOPPED_VERIFIED only if every stop condition holds.

    Any unknown (None), missing key or mismatch yields
    GUEST_QUIESCENCE_UNVERIFIED with reasons.  Never raises to signal
    success.  STOPPED_VERIFIED is NOT a sufficient condition for Collection
    consistency or Git tree immutability.
    """
    if not isinstance(before, WriterIdentity):
        return _unverified(['identity unavailable'])
    reasons: list[str] = []
    reasons += _check_stopped_inspect('post-stop', inspect_now, before)
    reasons += _check_stopped_inspect('after-wait', inspect_after_wait, before)
    reasons += _check_observation('post-stop', obs_now, before)
    reasons += _check_observation('after-wait', obs_after_wait, before)
    if reasons:
        return _unverified(reasons)
    return StopVerdict(STATUS_STOPPED_VERIFIED)


# --- Lifecycle ---------------------------------------------------------------------

def _real_sleep(seconds: float) -> None:  # pragma: no cover - injected in tests
    time.sleep(seconds)


class WriterLifecycle:
    """Trusted Supervisor side Writer launch / stop.

    There is deliberately no restart, start-existing or exec operation.
    """

    def __init__(self, runner: DockerRunner, probe: HostProbe,
                 sleep: Callable[[float], None] = _real_sleep) -> None:
        self._runner = runner
        self._probe = probe
        self._sleep = sleep

    # -- docker helpers (all failures surface as WriterError) --

    def _run(self, argv: Sequence[str], timeout: int = DOCKER_CMD_TIMEOUT_S) -> str:
        try:
            result = self._runner.run(list(argv), timeout=timeout)
        except Exception as exc:
            raise WriterError(f'docker {argv[1]} failed to run') from exc
        if not isinstance(result, tuple) or len(result) != 2:
            raise WriterError(f'docker {argv[1]} returned malformed result')
        rc, out = result
        if rc != 0:
            raise WriterError(f'docker {argv[1]} exited with code {rc}')
        if not isinstance(out, str):
            raise WriterError(f'docker {argv[1]} returned non-text output')
        return out

    def _inspect(self, cid: str) -> dict[str, Any]:
        return parse_inspect_output(self._run(build_inspect_argv(cid)))

    def _list_all(self) -> list[dict[str, Any]]:
        out = self._run(LIST_ALL_ARGV)
        result = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            result.append(self._inspect(validate_container_id(line)))
        return result

    def _confirmed(self, cid: str, started_at: str | None = None) -> bool:
        """Return True only if inspect confirms the same Id (and StartedAt)."""
        try:
            info = self._inspect(cid)
        except WriterError:
            return False
        if _get(info, 'Id') != cid:
            return False
        if started_at is not None and _get(info, 'State', 'StartedAt') != started_at:
            return False
        return True

    # -- launch --

    def launch(self, spec: WriterSpec) -> WriterIdentity:
        """Create, verify and start a new Writer; return its identity."""
        validate_writer_spec(spec)
        check_no_conflict(self._list_all(), spec)
        out = self._run(build_create_argv(spec))
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if len(lines) != 1 or not _CONTAINER_ID_RE.match(lines[0]):
            raise WriterError('docker create did not return a container id; '
                              'state is indeterminate; nothing was started')
        cid = lines[0]
        # Pre-start verification: failure => never start, never delete/kill.
        pre = self._inspect(cid)
        if _get(pre, 'Id') != cid:
            raise WriterError('pre-start inspect Id mismatch; not started')
        validate_writer_inspect(pre, spec)
        if _get(pre, 'State', 'Status') != 'created' or _get(pre, 'State', 'Running') \
                is not False:
            raise WriterError('pre-start state is not created; not started')
        try:
            self._run(build_start_argv(cid))
            post = self._inspect(cid)
            if _get(post, 'Id') != cid:
                raise WriterError('post-start inspect Id mismatch')
            validate_writer_inspect(post, spec)
            state_ok = (
                _get(post, 'State', 'Status') == 'running'
                and _get(post, 'State', 'Running') is True
                and isinstance(_get(post, 'State', 'Pid'), int)
                and not isinstance(_get(post, 'State', 'Pid'), bool)
                and _get(post, 'State', 'Pid') > 0
                and _get(post, 'RestartCount') == 0
            )
            if not state_ok:
                raise WriterError('post-start state is not running')
            return capture_identity(post, self._probe)
        except KeyboardInterrupt:
            try:
                self._abort_started(cid, 'interrupted')
            except KeyboardInterrupt:
                pass
            raise
        except WriterError as exc:
            raise self._abort_started(cid, str(exc)) from exc

    def _abort_started(self, cid: str, reason: str) -> WriterError:
        """Stop ``cid`` only if its Id is confirmed; never report it usable."""
        if not self._confirmed(cid):
            return WriterError(f'launch failed ({reason}); container identity not '
                               'confirmed; state is indeterminate; no destructive '
                               'action taken')
        try:
            self._run(build_stop_argv(cid), timeout=DOCKER_STOP_RUNNER_TIMEOUT_S)
            return WriterError(f'launch failed ({reason}); container stopped by id; '
                               'writer is not usable')
        except WriterError:
            return WriterError(f'launch failed ({reason}); stop by id failed; '
                               'state is indeterminate; writer is not usable')

    # -- stop --

    def stop(self, identity: WriterIdentity) -> StopVerdict:
        """Stop the Writer by ID and verify the stop (fail closed)."""
        try:
            return self._stop(identity)
        except Exception:  # never let an exception be mistaken for success
            return _unverified(['unexpected error during stop'])

    def _stop(self, identity: WriterIdentity) -> StopVerdict:
        if not isinstance(identity, WriterIdentity):
            return _unverified(['identity unavailable'])
        try:
            cid = validate_container_id(identity.container_id)
        except WriterError:
            return _unverified(['identity container id invalid'])
        reasons: list[str] = []
        try:
            info = self._inspect(cid)
        except WriterError:
            return _unverified(['pre-stop inspect failed; target not confirmed; '
                                'stop not issued'])
        if _get(info, 'Id') != cid or _get(info, 'State', 'StartedAt') != \
                identity.started_at:
            return _unverified(['pre-stop target identity mismatch; stop not issued'])
        try:
            self._run(build_stop_argv(cid), timeout=DOCKER_STOP_RUNNER_TIMEOUT_S)
        except WriterError:
            if not self._confirmed(cid, identity.started_at):
                return _unverified(['stop failed and target identity not confirmed; '
                                    'kill not issued'])
            try:
                self._run(build_kill_argv(cid))
            except WriterError:
                reasons.append('stop failed and kill failed')

        inspect_now = self._safe_inspect(cid, 'post-stop', reasons)
        obs_now = self._safe_observe(identity, 'post-stop', reasons)
        try:
            self._sleep(QUIESCE_OBSERVE_S)
        except Exception:
            reasons.append('quiescence wait failed')
        inspect_after = self._safe_inspect(cid, 'after-wait', reasons)
        obs_after = self._safe_observe(identity, 'after-wait', reasons)
        verdict = verify_writer_stopped(identity, inspect_now, inspect_after,
                                        obs_now, obs_after)
        if reasons:
            return _unverified(list(reasons) + list(verdict.reasons))
        return verdict

    def _safe_inspect(self, cid: str, label: str,
                      reasons: list[str]) -> dict[str, Any] | None:
        try:
            return self._inspect(cid)
        except WriterError:
            reasons.append(f'{label}: inspect failed')
            return None

    def _safe_observe(self, identity: WriterIdentity, label: str,
                      reasons: list[str]) -> StopObservation | None:
        try:
            obs = self._probe.observe(identity)
        except Exception:
            reasons.append(f'{label}: host probe failed')
            return None
        return obs if isinstance(obs, StopObservation) else None

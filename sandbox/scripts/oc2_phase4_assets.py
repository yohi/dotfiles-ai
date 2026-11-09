from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, TypeAlias

from oc2_native import parse_apm_native
from oc2_phase4_policy import PHASE4_POLICY_BY_ID
from oc2_phase4_selection import Phase4ArtifactPin, Phase4Plugin
from oc2_workspace import contains_credential_material

JsonValue: TypeAlias = str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']
MAX_ARTIFACT_BYTES: Final[int] = 16 * 1024 * 1024
MAX_ARTIFACT_FILES: Final[int] = 512
MAX_ARTIFACT_TOTAL: Final[int] = 8 * 1024 * 1024
MAX_RUNTIME_FILE: Final[int] = 4 * 1024 * 1024
MAX_BUNDLE_BYTES: Final[int] = 512 * 1024
ASSET_SCHEMA: Final[str] = 'dotfiles-ai/oc2-phase4-plugin-assets/v1'
IMPORT_SPECIFIER: Final[re.Pattern[str]] = re.compile(
    r'''(?:\bfrom\s*|\bimport\s*(?:\(\s*)?|\brequire\s*\(\s*)['"]([^'"]+)['"]''',
)


class Phase4AssetError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class VerifiedPluginArtifact:
    plugin: Phase4Plugin
    files: tuple[tuple[str, bytes], ...]


def _unique_json_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise Phase4AssetError('duplicate package.json key')
        result[key] = value
    return result


def _read_artifact(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise Phase4AssetError('plugin artifact must be a regular file within the size limit')
    current = path.absolute()
    while current != current.parent:
        if current.is_symlink():
            raise Phase4AssetError('plugin artifact path contains a symlink')
        current = current.parent
    return path.read_bytes()


def _package_entry(plugin: Phase4Plugin, pin: Phase4ArtifactPin, package: JsonValue) -> bytes:
    if not isinstance(package, dict):
        raise Phase4AssetError('plugin package metadata is invalid')
    if (package.get('name') != pin.package or package.get('version') != pin.version
            or package.get('type') != 'module'):
        raise Phase4AssetError('plugin package identity mismatch')
    policy = PHASE4_POLICY_BY_ID[plugin.value]
    for field, expected_pairs in (
        ('dependencies', policy.dependencies),
        ('optionalDependencies', policy.optional_dependencies),
        ('peerDependencies', policy.peer_dependencies),
    ):
        dependencies = package.get(field, {})
        if not isinstance(dependencies, dict) or dependencies != dict(expected_pairs):
            raise Phase4AssetError('plugin package dependencies are not allowlisted')
    exports = package.get('exports')
    if plugin is Phase4Plugin.AKANE:
        entrypoint = policy.entrypoint
        if (package.get('main') != './' + entrypoint or not isinstance(exports, dict)
                or exports.get('./server') != './' + entrypoint):
            raise Phase4AssetError('Akane server entrypoint is invalid')
        runtime_package = {
            'name': pin.package,
            'version': pin.version,
            'type': 'module',
            'main': './' + entrypoint,
            'exports': {'.': './' + entrypoint, './server': './' + entrypoint},
        }
    else:
        if not isinstance(exports, dict):
            raise Phase4AssetError('Sibyl TUI package export is invalid')
        root = exports.get('.')
        tui = exports.get('./tui')
        if (not isinstance(root, dict) or root.get('import') != './dist/index.js'
                or not isinstance(tui, dict) or tui.get('import') != './' + policy.entrypoint):
            raise Phase4AssetError('Sibyl TUI package export is invalid')
        runtime_package = {
            'name': pin.package,
            'version': pin.version,
            'type': 'module',
            'main': './' + policy.entrypoint,
            'exports': {
                '.': {'import': './' + policy.entrypoint},
                './tui': {'import': './' + policy.entrypoint},
            },
        }
    return (json.dumps(runtime_package, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def verify_plugin_artifact(
    raw: bytes,
    plugin: Phase4Plugin,
    pin: Phase4ArtifactPin,
) -> VerifiedPluginArtifact:
    """Validate an archive and retain only its pinned runtime entrypoints."""
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise Phase4AssetError('plugin artifact exceeds the size limit')
    if hashlib.sha512(raw).hexdigest() != pin.artifact_sha512:
        raise Phase4AssetError('plugin artifact SHA-512 mismatch')

    entrypoint = PHASE4_POLICY_BY_ID[plugin.value].entrypoint
    required = {'package/package.json', 'package/' + entrypoint}
    selected: dict[str, bytes] = {}
    seen: set[str] = set()
    total_bytes = 0
    try:
        archive = tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz')
        with archive:
            members = archive.getmembers()
            if not members or len(members) > MAX_ARTIFACT_FILES:
                raise Phase4AssetError('plugin artifact file count is invalid')
            for member in members:
                name = member.name
                relative = PurePosixPath(name)
                if (relative.is_absolute() or '\\' in name
                        or any(part in ('', '.', '..') for part in name.split('/'))):
                    raise Phase4AssetError('plugin artifact path is unsafe')
                if name in seen:
                    raise Phase4AssetError('plugin artifact has duplicate paths')
                seen.add(name)
                if member.isdir():
                    continue
                if not member.isfile() or member.size < 0 or member.size > MAX_RUNTIME_FILE:
                    raise Phase4AssetError('plugin artifact contains a non-regular or oversized file')
                total_bytes += member.size
                if total_bytes > MAX_ARTIFACT_TOTAL:
                    raise Phase4AssetError('plugin artifact exceeds uncompressed size limit')
                if name not in required:
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    raise Phase4AssetError('plugin artifact file could not be read')
                content = stream.read(MAX_RUNTIME_FILE + 1)
                if len(content) != member.size:
                    raise Phase4AssetError('plugin artifact file size mismatch')
                selected[name.removeprefix('package/')] = content
    except (EOFError, OSError, tarfile.TarError) as exc:
        raise Phase4AssetError('plugin artifact archive is invalid') from exc

    if set('package/' + path for path in selected) != required:
        raise Phase4AssetError('plugin artifact is missing its package metadata or entrypoint')
    try:
        package = json.loads(selected['package.json'], object_pairs_hook=_unique_json_object)
    except (ValueError, UnicodeError) as exc:
        raise Phase4AssetError('plugin package metadata is invalid') from exc
    selected['package.json'] = _package_entry(plugin, pin, package)
    if any(contains_credential_material(content) for content in selected.values()):
        raise Phase4AssetError('plugin artifact contains credential material')
    try:
        entrypoint = selected[PHASE4_POLICY_BY_ID[plugin.value].entrypoint].decode('utf-8')
    except UnicodeError as exc:
        raise Phase4AssetError('plugin entrypoint is not UTF-8') from exc
    imports = set(IMPORT_SPECIFIER.findall(entrypoint))
    allowed_imports = PHASE4_POLICY_BY_ID[plugin.value].external_imports
    if any(name.startswith(('./', '../')) or name not in allowed_imports for name in imports):
        raise Phase4AssetError('plugin entrypoint contains an unapproved dependency')
    return VerifiedPluginArtifact(plugin, tuple(sorted(selected.items())))


def build_phase4_plugin_bundle(
    repo: Path,
    artifact_paths: tuple[Path, Path],
    *,
    explicit_opt_in: bool,
) -> tuple[bytes, str]:
    """Build a deterministic, credential-free Phase 4 plugin asset bundle."""
    apm = repo / 'apm.yml'
    if apm.is_symlink() or not apm.is_file() or apm.stat().st_size > 2 * 1024 * 1024:
        raise Phase4AssetError('apm.yml is unavailable for Phase 4 artifact export')
    apm_bytes = apm.read_bytes()
    try:
        config = parse_apm_native(
            apm_bytes,
            require_oc2_assets=True,
            phase4_plugins=explicit_opt_in,
        )
    except ValueError as exc:
        raise Phase4AssetError('Phase 4 APM selection is invalid') from exc
    if not explicit_opt_in or not config.phase4_plugins.enabled:
        raise Phase4AssetError('Phase 4 export requires explicit Phase 4 opt-in')

    artifact_by_plugin = dict(zip((Phase4Plugin.AKANE, Phase4Plugin.SIBYL), artifact_paths, strict=True))
    files: dict[str, str] = {}
    plugin_rows: list[dict[str, JsonValue]] = []
    hashes: dict[str, str] = {}
    for pin in config.phase4_plugins.artifacts:
        artifact = verify_plugin_artifact(_read_artifact(artifact_by_plugin[pin.plugin]), pin.plugin, pin)
        paths: list[str] = []
        for relative, content in artifact.files:
            target = f'plugins/{pin.plugin.value}/{relative}'
            files[target] = base64.b64encode(content).decode('ascii')
            hashes[target] = hashlib.sha256(content).hexdigest()
            paths.append(relative)
        row: dict[str, JsonValue] = {
            'id': pin.plugin.value,
            'package': pin.package,
            'version': pin.version,
            'repository': pin.repository,
            'commit': pin.source_commit,
            'acquisition': pin.acquisition.value,
            'artifact_sha512': pin.artifact_sha512,
            'entrypoint': PHASE4_POLICY_BY_ID[pin.plugin.value].entrypoint,
            'files': paths,
        }
        if pin.build_tool is not None and pin.lock_sha256 is not None:
            row['build_tool'] = pin.build_tool
            row['lock_sha256'] = pin.lock_sha256
        plugin_rows.append(row)
    payload: dict[str, JsonValue] = {
        'schema': ASSET_SCHEMA,
        'source_sha256': hashlib.sha256(apm_bytes).hexdigest(),
        'selection': [plugin.value for plugin in config.phase4_plugins.allowlist],
        'plugins': plugin_rows,
        'files': files,
        'sha256': hashes,
    }
    raw = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode()
    if len(raw) > MAX_BUNDLE_BYTES:
        raise Phase4AssetError('Phase 4 plugin bundle exceeds the size limit')
    return raw, hashlib.sha256(raw).hexdigest()

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from yaml.nodes import Node
from oc2_phase4_policy import PHASE4_POLICY_BY_ID


class Phase4Plugin(StrEnum):
    AKANE = 'akane'
    SIBYL = 'sibyl'


class ArtifactAcquisition(StrEnum):
    GITHUB_PACKAGE = 'github-package'
    SOURCE_BUILD = 'source-build'


@dataclass(frozen=True, slots=True)
class Phase4ArtifactPin:
    plugin: Phase4Plugin
    package: str
    version: str
    repository: str
    source_commit: str
    acquisition: ArtifactAcquisition
    artifact_sha512: str
    build_tool: str | None = None
    lock_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class Phase4PluginSelection:
    enabled: bool
    allowlist: tuple[Phase4Plugin, ...]
    artifacts: tuple[Phase4ArtifactPin, ...]


PHASE4_PLUGIN_ORDER: Final[tuple[Phase4Plugin, ...]] = (
    Phase4Plugin.AKANE,
    Phase4Plugin.SIBYL,
)


def parse_phase4_selection(
    node: Node | None,
    *,
    explicit_opt_in: bool,
) -> Phase4PluginSelection:
    """Parse the fixed Phase 4 plugin candidate list and runtime opt-in."""
    from oc2_native import NativeConfigError, _boolean, _mapping, _sequence, _string

    disabled = Phase4PluginSelection(enabled=False, allowlist=(), artifacts=())
    if node is None:
        if explicit_opt_in:
            raise NativeConfigError('Phase 4 plugin selection is missing from APM')
        return disabled

    fields = _mapping(node, 'x-oc2-phase4')
    if set(fields) != {'enabled', 'allowlist', 'artifacts'}:
        raise NativeConfigError('x-oc2-phase4 fields are invalid')

    gate_enabled = _boolean(fields['enabled'], 'x-oc2-phase4.enabled')
    raw_selected = tuple(
        _string(item, 'x-oc2-phase4.allowlist entry')
        for item in _sequence(fields['allowlist'], 'x-oc2-phase4.allowlist')
    )
    allowed = {plugin.value for plugin in Phase4Plugin}
    if any(value not in allowed for value in raw_selected):
        raise NativeConfigError('unapproved Phase 4 plugin')
    selected = tuple(Phase4Plugin(value) for value in raw_selected)
    if selected != PHASE4_PLUGIN_ORDER:
        raise NativeConfigError('x-oc2-phase4 must use the fixed Phase 4 plugin order')
    artifact_pins = _parse_artifacts(fields['artifacts'])
    if explicit_opt_in and not gate_enabled:
        raise NativeConfigError('Phase 4 is disabled in APM')
    if not explicit_opt_in:
        return disabled
    return Phase4PluginSelection(enabled=True, allowlist=selected, artifacts=artifact_pins)


def _parse_artifacts(node: Node) -> tuple[Phase4ArtifactPin, ...]:
    from oc2_native import NativeConfigError, _mapping, _string

    artifact_nodes = _mapping(node, 'x-oc2-phase4.artifacts')
    if set(artifact_nodes) != {plugin.value for plugin in PHASE4_PLUGIN_ORDER}:
        raise NativeConfigError('Phase 4 artifact set is not allowlisted')

    pins: list[Phase4ArtifactPin] = []
    for plugin in PHASE4_PLUGIN_ORDER:
        entry = _mapping(artifact_nodes[plugin.value], 'Phase 4 artifact ' + plugin.value)
        policy = PHASE4_POLICY_BY_ID[plugin.value]
        expected_fields = {'package', 'version', 'repository', 'commit', 'acquisition', 'sha512'}
        if policy.build_tool is not None:
            expected_fields.update({'build_tool', 'lock_sha256'})
        if set(entry) != expected_fields:
            raise NativeConfigError('Phase 4 artifact fields are invalid: ' + plugin.value)
        selected_identity = (
            _string(entry['package'], 'Phase 4 package'),
            _string(entry['version'], 'Phase 4 version'),
            _string(entry['repository'], 'Phase 4 repository'),
            _string(entry['commit'], 'Phase 4 commit'),
            _string(entry['acquisition'], 'Phase 4 acquisition'),
        )
        expected_identity = (
            policy.package,
            policy.version,
            policy.repository,
            policy.source_commit,
            policy.acquisition,
        )
        if selected_identity != expected_identity:
            raise NativeConfigError('Phase 4 source identity is not allowlisted: ' + plugin.value)
        digest = _string(entry['sha512'], 'Phase 4 artifact SHA-512')
        if re.fullmatch(r'[0-9a-f]{128}', digest) is None:
            raise NativeConfigError('Phase 4 artifact SHA-512 is invalid')
        build_tool: str | None = None
        lock_sha256: str | None = None
        if policy.build_tool is not None:
            build_tool = _string(entry['build_tool'], 'Sibyl build tool')
            lock_sha256 = _string(entry['lock_sha256'], 'Sibyl lock SHA-256')
            if (build_tool != policy.build_tool or lock_sha256 != policy.lock_sha256):
                raise NativeConfigError('Sibyl build inputs are not allowlisted')
        pins.append(Phase4ArtifactPin(
            plugin, policy.package, policy.version, policy.repository,
            policy.source_commit, ArtifactAcquisition(policy.acquisition),
            digest, build_tool, lock_sha256,
        ))
    return tuple(pins)

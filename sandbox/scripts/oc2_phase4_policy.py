from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class PluginPolicy:
    plugin_id: str
    package: str
    version: str
    repository: str
    source_commit: str
    acquisition: str
    entrypoint: str
    external_imports: frozenset[str]
    dependencies: tuple[tuple[str, str], ...]
    optional_dependencies: tuple[tuple[str, str], ...]
    peer_dependencies: tuple[tuple[str, str], ...]
    build_tool: str | None = None
    lock_sha256: str | None = None


AKANE_POLICY: Final[PluginPolicy] = PluginPolicy(
    plugin_id='akane',
    package='@yohi/akane',
    version='3.0.1',
    repository='yohi/akane',
    source_commit='b30772082e92cf148d5d8714266f326bad27f86a',
    acquisition='github-package',
    entrypoint='dist/index.js',
    external_imports=frozenset({'@opencode/plugin', 'node:fs', 'node:path'}),
    dependencies=(('@opencode/plugin', '2.1.4'),),
    optional_dependencies=(),
    peer_dependencies=(('effect', '^4.0.1'),),
)

SIBYL_POLICY: Final[PluginPolicy] = PluginPolicy(
    plugin_id='sibyl',
    package='@yohi/sibyl',
    version='3.0.1',
    repository='yohi/sibyl',
    source_commit='e0249482701159bcd5a556fe06faae11dd41f66e',
    acquisition='source-build',
    entrypoint='dist/tui.js',
    external_imports=frozenset({
        '@opencode/plugin/tui', '@opentui/core', '@opentui/solid',
        '@opentui/solid/jsx-runtime', 'node:fs', 'node:os', 'node:path', 'solid-js',
    }),
    dependencies=(('@babel/core', '^7.23.3'),),
    optional_dependencies=(('node-pty', '^1.1.0'),),
    peer_dependencies=(
        ('@opencode/plugin', '>=2.1.4 <3'),
        ('@opentui/core', '>=0.6.8 <1'),
        ('@opentui/keymap', '>=0.6.8 <1'),
        ('@opentui/solid', '>=0.6.8 <1'),
        ('solid-js', '>=1.9.0 <2'),
    ),
    build_tool='bun@1.4.2',
    lock_sha256='71c0d8e7cd1267e0973066d01045a47e266907733d043d79f6ad899043f6e8b7',
)

PHASE4_PLUGIN_POLICIES: Final[tuple[PluginPolicy, ...]] = (AKANE_POLICY, SIBYL_POLICY)
PHASE4_POLICY_BY_ID: Final[dict[str, PluginPolicy]] = {
    policy.plugin_id: policy for policy in PHASE4_PLUGIN_POLICIES
}

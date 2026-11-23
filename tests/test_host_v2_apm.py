"""Offline contract tests; no real Microsoft APM and no network access."""
from __future__ import annotations

import json
import hashlib
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / 'host/opencode2/sync_apm.py'
MOCK_APM = '''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
if args == ['--version']:
    print(os.environ.get('FAKE_APM_VERSION', 'apm 0.37.0'))
    sys.exit()
if os.environ.get('FAKE_APM_FAIL') == args[0]:
    sys.exit(25)
root = pathlib.Path(args[args.index('--root')+1])
# --root does not control manifest discovery; cwd must be a private stage.
if root != pathlib.Path.cwd() or not (root / 'apm.yml').is_file():
    sys.exit(42)
manifest = (root / 'apm.yml').read_text()
if 'x-variants:' in manifest or '&gpt_variants' in manifest or 'provider:' in manifest:
    sys.exit(43)
if 'dependencies:' not in manifest or 'targets:' not in manifest:
    sys.exit(44)
for required in ['greptileai/skills/skills/check-pr', 'greptileai/skills/skills/greploop']:
    if required not in manifest:
        sys.exit(46)
for forbidden in ['greptileai/skills//check-pr', 'greptileai/skills//greploop',
                  'anthropics/claude-code//plugins/code-review']:
    if forbidden in manifest:
        sys.exit(47)
if not (root / '.apm/instructions').is_dir():
    sys.exit(45)
if args[0] == 'install':
    (root / '.agents/skills/test-skill').mkdir(parents=True)
    (root / '.agents/skills/test-skill/SKILL.md').write_text('skill')
    (root / '.opencode/commands').mkdir(parents=True, exist_ok=True)
    (root / '.opencode/commands/test.md').write_text('command')
    (root / 'opencode.json').write_text(json.dumps({'mcp':{'servers':{
        'example':{'type':'remote', 'url':'https://example.invalid/mcp', 'disabled':False},
        'codegraph':{'type':'local', 'command':['_scripts/codegraph-bootstrap.sh','serve','--mcp'],
                     'cwd':'.', 'disabled':True}}}}))
if args[0] == 'compile':
    (root / 'AGENTS.md').write_text('instructions')
'''


class APMHostV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir()
        self.global_v1 = self.home / '.config/opencode/opencode.json'
        self.global_v1.parent.mkdir(parents=True)
        self.global_v1.write_text('sentinel-v1')
        self.config = self.home / '.config/opencode-v2/opencode/opencode.json'
        self.config.parent.mkdir(parents=True)
        self.config.write_text(json.dumps({'update':'disable','plugins':[], 'mcp':{'servers':{}}}))
        self.mock = Path(self.tmp.name) / 'fake-apm'
        self.mock.write_text(MOCK_APM)
        self.mock.chmod(0o755)
        self.env = {**os.environ, 'HOME':str(self.home), 'HOST_V2_APM_BIN':str(self.mock)}

    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable,str(SCRIPT),*args], env=env or self.env, text=True, capture_output=True)

    def test_check_is_no_write(self):
        before = self.config.read_bytes()
        result = self.run_cli('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.home / '.local').exists())

    def test_initial_apply_disables_mcp_and_preserves_v1(self):
        result = self.run_cli('--apply')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.global_v1.read_text(),'sentinel-v1')
        obj = json.loads(self.config.read_text())
        self.assertTrue(obj['mcp']['servers']['example']['disabled'])
        self.assertEqual(obj['update'], 'disable')
        for name in ['AGENTS.md','skills','commands']:
            self.assertTrue((self.config.parent / name).is_symlink())
        self.assertEqual((self.config.parent/'AGENTS.md').read_text(), 'instructions')

    def test_apm_manifest_normalized_and_source_unchanged(self):
        original = (SCRIPT.parents[2] / 'apm.yml').read_bytes()
        result = self.run_cli('--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((SCRIPT.parents[2] / 'apm.yml').read_bytes(), original)
        snapshots = self.home / '.local/share/opencode-v2/apm-host-snapshots'
        stages = list(snapshots.glob('snapshot-*'))
        self.assertEqual(len(stages), 1)
        reduced = (stages[0] / 'apm.yml').read_text()
        self.assertIn('dependencies:', reduced)
        self.assertIn('opencode', reduced)
        self.assertNotIn('&gpt_variants', reduced)
        self.assertNotIn('x-variants:', reduced)
        self.assertNotIn('provider:', reduced)
        original_deps = yaml.safe_load(original)['dependencies']['apm']
        staged_deps = yaml.safe_load(reduced)['dependencies']['apm']
        rewrites = {
            'greptileai/skills//check-pr': 'greptileai/skills/skills/check-pr',
            'greptileai/skills//greploop': 'greptileai/skills/skills/greploop',
        }
        excluded = 'anthropics/claude-code//plugins/code-review'
        self.assertEqual(
            staged_deps,
            [rewrites.get(dep, dep) for dep in original_deps if dep != excluded],
        )
        self.assertEqual(len(staged_deps), len(original_deps) - 1)
        self.assertEqual(yaml.safe_load(reduced)['dependencies']['mcp'],
                         yaml.safe_load(original)['dependencies']['mcp'])

    def test_check_logs_only_explicit_host_dependency_changes(self):
        result = self.run_cli('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('22 packages, 12 MCP entries', result.stdout)
        self.assertEqual(result.stderr.count('APM_HOST_V2_REWRITE:'), 2)
        self.assertEqual(result.stderr.count('APM_HOST_V2_EXCLUDE:'), 1)
        self.assertIn('greptileai/skills/skills/check-pr', result.stderr)
        self.assertIn('greptileai/skills/skills/greploop', result.stderr)
        self.assertIn('anthropics/claude-code//plugins/code-review', result.stderr)
        self.assertFalse((self.home / '.local').exists())

    def test_check_parses_real_apm_yaml_without_deployment(self):
        result = self.run_cli('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('APM-only manifest valid', result.stdout)
        self.assertFalse((self.home / '.local').exists())

    def test_repeat_apply_safe(self):
        self.assertEqual(self.run_cli('--apply').returncode,0)
        result = self.run_cli('--apply')
        self.assertEqual(result.returncode,0,result.stderr)

    def test_resync_preserves_confirmed_enabled_mcp(self):
        self.assertEqual(self.run_cli('--apply').returncode, 0)
        obj = json.loads(self.config.read_text())
        obj['mcp']['servers']['example']['disabled'] = False
        self.config.write_text(json.dumps(obj))
        state_path = self.config.parent / 'apm-host-sync-state.json'
        state = json.loads(state_path.read_text())
        state['mcp_sha256'] = hashlib.sha256(json.dumps(
            obj['mcp']['servers'], sort_keys=True, separators=(',', ':')
        ).encode()).hexdigest()
        state_path.write_text(json.dumps(state))
        result = self.run_cli('--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(self.config.read_text())
        self.assertFalse(updated['mcp']['servers']['example']['disabled'])
        self.assertTrue(updated['mcp']['servers']['codegraph']['disabled'])
        self.assertEqual(self.global_v1.read_text(), 'sentinel-v1')

    def test_modified_mcp_is_rejected(self):
        self.assertEqual(self.run_cli('--apply').returncode,0)
        obj = json.loads(self.config.read_text())
        obj['mcp']['servers']['example']['disabled'] = False
        self.config.write_text(json.dumps(obj))
        result=self.run_cli('--apply')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('changed',result.stderr)
        self.assertEqual(self.global_v1.read_text(),'sentinel-v1')

    def test_unmanaged_adapter_is_rejected(self):
        dest=self.config.parent/'skills'
        dest.mkdir()
        result=self.run_cli('--apply')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('unmanaged',result.stderr)

    def test_codegraph_ssot_is_official_direct_cli(self):
        source = yaml.safe_load((SCRIPT.parents[2] / 'apm.yml').read_text())
        servers = [x for x in source['dependencies']['mcp']
                   if isinstance(x, dict) and x.get('name') == 'codegraph']
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]['command'], 'codegraph')
        self.assertEqual(servers[0]['args'], ['serve', '--mcp'])
        self.assertNotIn('cwd', servers[0])

    def test_refresh_codegraph_updates_only_command_and_receipt(self):
        self.assertEqual(self.run_cli('--apply').returncode, 0)
        original = json.loads(self.config.read_text())
        state_file = self.config.parent / 'apm-host-sync-state.json'
        old_state = json.loads(state_file.read_text())
        # Simulate manually enabled MCPs recorded through manage_mcp.py.
        original['mcp']['servers']['codegraph']['disabled'] = False
        original['mcp']['servers']['example']['disabled'] = True
        original['model'] = 'openai/gpt-6-luna'
        self.config.write_text(json.dumps(original))
        old_state['mcp_sha256'] = hashlib.sha256(json.dumps(
            original['mcp']['servers'], sort_keys=True, separators=(',', ':')
        ).encode()).hexdigest()
        state_file.write_text(json.dumps(old_state))
        result = self.run_cli('--refresh-codegraph', env={
            **self.env, 'HOST_V2_APM_BIN': '/not/installed/apm'
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        changed = json.loads(self.config.read_text())
        self.assertEqual(changed['model'], original['model'])
        self.assertEqual(changed['mcp']['servers']['example'],
                         original['mcp']['servers']['example'])
        entry = changed['mcp']['servers']['codegraph']
        self.assertEqual(entry['command'], ['codegraph', 'serve', '--mcp'])
        self.assertNotIn('cwd', entry)
        self.assertFalse(entry['disabled'])
        self.assertEqual(self.global_v1.read_text(), 'sentinel-v1')
        state = json.loads(state_file.read_text())
        self.assertEqual(state['snapshot'], old_state['snapshot'])
        self.assertEqual(state['mcp_sha256'], hashlib.sha256(json.dumps(
            changed['mcp']['servers'], sort_keys=True, separators=(',', ':')
        ).encode()).hexdigest())
        self.assertEqual(self.run_cli('--refresh-codegraph').returncode, 0)

    def test_refresh_codegraph_rejects_unowned_config_without_write(self):
        self.assertEqual(self.run_cli('--apply').returncode, 0)
        obj = json.loads(self.config.read_text())
        obj['mcp']['servers']['codegraph']['disabled'] = False
        self.config.write_text(json.dumps(obj))
        before = self.config.read_bytes()
        result = self.run_cli('--refresh-codegraph')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('changed', result.stderr)
        self.assertEqual(self.config.read_bytes(), before)

    def test_refresh_codegraph_rejects_unknown_command_without_write(self):
        self.assertEqual(self.run_cli('--apply').returncode, 0)
        obj = json.loads(self.config.read_text())
        obj['mcp']['servers']['codegraph']['command'] = ['other-tool', 'serve', '--mcp']
        self.config.write_text(json.dumps(obj))
        state_file = self.config.parent / 'apm-host-sync-state.json'
        state = json.loads(state_file.read_text())
        state['mcp_sha256'] = hashlib.sha256(json.dumps(
            obj['mcp']['servers'], sort_keys=True, separators=(',', ':')
        ).encode()).hexdigest()
        state_file.write_text(json.dumps(state))
        before = self.config.read_bytes()
        result = self.run_cli('--refresh-codegraph')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not on the known', result.stderr)
        self.assertEqual(self.config.read_bytes(), before)

    def test_old_apm_is_rejected(self):
        result = self.run_cli('--apply',env={**self.env,'FAKE_APM_VERSION':'apm 0.31.0'})
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.home/'.local').exists())

    def test_apm_failure_does_not_touch_v2(self):
        before=self.config.read_bytes()
        result=self.run_cli('--apply',env={**self.env,'FAKE_APM_FAIL':'install'})
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(before,self.config.read_bytes())
        self.assertFalse((self.config.parent/'skills').exists())

    def test_unmanaged_mcp_stops(self):
        obj=json.loads(self.config.read_text()); obj['mcp']['servers']['mine']={}
        self.config.write_text(json.dumps(obj))
        result=self.run_cli('--apply')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('unmanaged',result.stderr)


if __name__=='__main__':unittest.main()

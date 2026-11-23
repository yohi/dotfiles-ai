"""Offline contract tests for the explicit host-wide APM sync orchestrator."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import contextlib
import io

SCRIPT = Path(__file__).resolve().parents[1] / '_scripts/sync_apm_all.py'
spec = importlib.util.spec_from_file_location('sync_apm_all', SCRIPT)
mod = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class SyncAPMAllTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir()
        self.original_repo = mod.REPO
        mod.REPO = self.repo
        self.addCleanup(setattr, mod, 'REPO', self.original_repo)
        (self.repo / 'Makefile').write_text('all:\n\t@true\n')
        self.write_manifest(['opencode','codex'])

    def write_manifest(self, targets):
        (self.repo / 'apm.yml').write_text(
            'name: dotfiles-ai\ntargets:\n' + ''.join('  - '+x+'\n' for x in targets)
            + 'dependencies:\n  apm: [example]\n  mcp: [example]\n'
        )

    def test_standard_plan_is_non_destructive_and_explicit(self):
        targets=mod.source_targets()
        steps, skipped=mod.build_steps(targets,self.home)
        commands=[x.command for x in steps]
        self.assertEqual(commands.count(('apm','install')),1)
        self.assertEqual(commands.count(('apm','compile')),1)
        self.assertIn(('make','--no-print-directory','setup-opencode'),commands)
        self.assertIn(('make','--no-print-directory','sync-codex'),commands)
        self.assertNotIn(('make','--no-print-directory','sync-agents-core'),commands)
        self.assertNotIn(('make','--no-print-directory','setup'),commands)
        self.assertNotIn(('make','--no-print-directory','sync-mcp'),commands)
        self.assertIn('Claude Code',skipped)
        self.assertIn('Gemini CLI',skipped)
        self.assertIn('Antigravity',skipped)

    def test_host_v2_plan_includes_models_and_apm(self):
        conf=self.home/'.config/opencode-v2/opencode/opencode.json'
        conf.parent.mkdir(parents=True)
        conf.write_text('{}')
        steps,_=mod.build_steps(mod.source_targets(),self.home)
        names=[x.name for x in steps]
        self.assertIn('Host V2: sync model and providers',names)
        self.assertIn('Host V2: sync APM/MCP/skills',names)

    def test_non_activated_targets_are_not_installed(self):
        (self.home/'.claude').mkdir()
        (self.home/'.gemini').mkdir()
        (self.home/'.gemini/antigravity-cli').mkdir()
        steps, skipped=mod.build_steps(mod.source_targets(),self.home)
        names=[x.name for x in steps]
        self.assertTrue(any('Claude' in name for name in names))
        self.assertTrue(any('Antigravity' in name for name in names))
        self.assertFalse(any('Gemini' in name for name in names))
        self.assertIn('Gemini CLI', skipped)

    def test_explicit_target_addition_activates_only_existing(self):
        self.write_manifest(['opencode','codex','claude','gemini','antigravity'])
        (self.home/'.claude').mkdir()
        (self.home/'.gemini/antigravity-cli').mkdir(parents=True)
        steps, skipped=mod.build_steps(mod.source_targets(),self.home)
        names=[x.name for x in steps]
        self.assertTrue(any('Claude Code' in x for x in names))
        self.assertTrue(any('Gemini CLI' in x for x in names))
        self.assertTrue(any('Antigravity' in x for x in names))
        self.assertNotIn('Claude Code',skipped)

    def test_rejects_unexpected_new_target(self):
        self.write_manifest(['opencode','made-up-provider'])
        with self.assertRaisesRegex(mod.SyncStopped,'unsupported target'):
            mod.source_targets()

    def test_rejects_duplicate_targets(self):
        self.write_manifest(['opencode','opencode'])
        with self.assertRaisesRegex(mod.SyncStopped,'unique'):
            mod.source_targets()

    def test_rejects_symlinked_manifest(self):
        original=self.repo/'apm.yml'
        moved=self.repo/'elsewhere.yml'
        original.rename(moved)
        original.symlink_to(moved)
        with self.assertRaisesRegex(mod.SyncStopped,'unsafe'):
            mod.source_targets()

    def test_check_no_commands_execute(self):
        env={'HOME':str(self.home)}
        with mock.patch.object(mod,'protect_tracked_generated') as guard, \
             mock.patch.object(mod.shutil,'which',return_value='/usr/bin/mock'), \
             mock.patch.object(mod.subprocess,'run') as run, \
             mock.patch.dict(mod.os.environ,env),contextlib.redirect_stdout(io.StringIO()) as out:
            result=mod.main(['--check'])
        self.assertEqual(result,0)
        run.assert_not_called()
        guard.assert_called_once()
        self.assertIn('CHECK_PASS:',out.getvalue())

    def test_apply_stops_at_first_failure_and_reports_partial(self):
        env={'HOME':str(self.home)}
        executed=[]
        def runner(command,**kw):
            executed.append(tuple(command))
            class Result: returncode=12 if len(executed)==3 else 0
            return Result()
        with mock.patch.object(mod,'protect_tracked_generated'), \
             mock.patch.object(mod.shutil,'which',return_value='/usr/bin/mock'), \
             mock.patch.object(mod.subprocess,'run',side_effect=runner), \
             mock.patch.dict(mod.os.environ,env), \
             contextlib.redirect_stderr(io.StringIO()) as err,contextlib.redirect_stdout(io.StringIO()):
            result=mod.main(['--apply'])
        self.assertEqual(result,1)
        self.assertEqual(len(executed),3)
        self.assertIn('PARTIAL: 2 completed',err.getvalue())

    def test_apply_does_not_fetch_git_or_upgrade_binaries(self):
        steps,_=mod.build_steps(mod.source_targets(),self.home)
        for s in steps:
            self.assertNotIn(s.command[0],('git','curl','npm','docker','sudo'))
            self.assertNotIn('upgrade',' '.join(s.command))
            self.assertNotIn('uninstall',' '.join(s.command))

    def test_sandbox_is_never_modified(self):
        self.write_manifest(['opencode','codex'])
        steps,skipped=mod.build_steps(mod.source_targets(),self.home)
        self.assertIn('OC2 Sandbox live runtime',skipped)
        self.assertFalse(any('sandbox/' in ' '.join(x.command) or 'sbx' in ' '.join(x.command) for x in steps))

    def test_model_and_mcp_scripts_checked_before_host_writes(self):
        conf=self.home/'.config/opencode-v2/opencode/opencode.json'
        conf.parent.mkdir(parents=True)
        conf.write_text('{}')
        for name in ('sync_models.py','sync_apm.py'):
            path=self.repo/'host/opencode2'/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('')
        executed=[]
        def fake_run(command,**kwargs):
            executed.append(tuple(command))
            class Result:
                returncode=0
                stderr=''
                stdout=''
            return Result()
        with mock.patch.object(mod,'protect_tracked_generated'), \
             mock.patch.object(mod.shutil,'which',return_value='/usr/bin/mock'), \
             mock.patch.object(mod.subprocess,'run',side_effect=fake_run):
            mod.preflight(mod.source_targets(),mod.build_steps(mod.source_targets(),self.home)[0],self.home,'apm')
        self.assertEqual(len(executed),2)
        self.assertTrue(all(x[-1]=='--check' for x in executed))

if __name__=='__main__':
    unittest.main()

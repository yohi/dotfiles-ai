"""Offline tests: no real sbx process, network, or OpenCode configuration writes."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage_opencode_v2.py"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPT.parent))
import stage_opencode_v2 as stage  # noqa: E402
import prepare_opencode_v2 as exporter  # noqa: E402


class StageTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.root.mkdir()
        self.bundle = Path(temporary.name) / "sbx-config-0123456789abcdef-0123456789ab"
        self.bundle.mkdir()
        self.apm = self.root / "apm.yml"
        self.apm.write_text("shell: bash\nsnapshot: true\n", encoding="utf-8")
        server = {
            "$schema": "https://opencode.ai/config.json", "shell": "bash",
            "snapshot": True, "plugins": [], "mcp": {},
        }
        tui = {"$schema": "https://opencode.ai/v2/cli.json", "plugins": []}
        for name, value in (("opencode.jsonc", server), ("cli.json", tui)):
            (self.bundle / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
        manifest = {
            "schema": "dotfiles-ai/sandbox-export/v0",
            "generator": "v0.2", "source": "apm.yml",
            "config_format": "legacy-minimal",
            "source_sha256": hashlib.sha256(self.apm.read_bytes()).hexdigest(),
        "opencode_version": "2.2.5", "plugins_exported": 0,
            "mcp_entries_exported": 0,
            "artifacts_sha256": {
                name: hashlib.sha256((self.bundle / name).read_bytes()).hexdigest()
                for name in ("opencode.jsonc", "cli.json")
            },
        }
        (self.bundle / "export-manifest.json").write_text(json.dumps(manifest) + "\n")

    def test_guest_verify_valid_bundle(self) -> None:
        """Verify the fixed Guest bundle directory beneath its separate trusted root."""
        digest = stage.verify_bundle(self.bundle, trusted_root=stage.BUNDLE_ROOT)
        self.assertEqual(
            digest,
            hashlib.sha256((self.bundle / "export-manifest.json").read_bytes()).hexdigest(),
        )
    def test_guest_cli_only_accepts_the_fixed_staging_path(self) -> None:
        """Distinguish the Guest staging path from the trusted root used for validation."""
        staged = self.root / "sbx-config-0123456789abcdef-aabbccddeeff"
        staged.mkdir()
        for entry in self.bundle.iterdir():
            (staged / entry.name).write_bytes(entry.read_bytes())

        with patch.object(stage, "REMOTE_PARENT", str(self.root)):
            self.assertEqual(stage.main(["--verify-bundle", staged.name]), 0)
            self.assertEqual(stage.main(["--verify-bundle", self.bundle.name]), 1)

    def test_guest_verifier_imports_without_site_packages_or_repository(self) -> None:
        """Verify the isolated Guest script and its sibling helper validate a bundle."""
        with tempfile.TemporaryDirectory() as temporary:
            guest_root = Path(temporary)
            guest_script = guest_root / 'stage_guest.py'
            guest_script.write_bytes(SCRIPT.read_bytes())
            Path(str(guest_script) + '.native.py').write_bytes(
                SCRIPT.with_name('oc2_agent_native.py').read_bytes(),
            )
            bundle_name = 'sbx-config-0123456789abcdef-0123456789ab'
            staged = guest_root / bundle_name
            staged.mkdir()
            for entry in self.bundle.iterdir():
                (staged / entry.name).write_bytes(entry.read_bytes())
            guest_code = (
                'import importlib.util, pathlib, sys; '
                'path = pathlib.Path(sys.argv[1]); '
                'spec = importlib.util.spec_from_file_location("guest_stage", path); '
                'module = importlib.util.module_from_spec(spec); '
                'spec.loader.exec_module(module); '
                'module.REMOTE_PARENT = sys.argv[2]; '
                'raise SystemExit(module.main(["--verify-bundle", sys.argv[3]]))'
            )
            result = subprocess.run(
                [sys.executable, '-S', '-c', guest_code,
                 str(guest_script), str(guest_root), bundle_name],
                capture_output=True, text=True, check=False, cwd=guest_root, env={'PATH': ''},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('VERIFY_OK:', result.stdout)
            self.assertEqual(result.stderr, '')

    def test_guest_verifier_refuses_unverified_repository_helper_without_sidecar(self) -> None:
        """Reject an ambient Native helper when the staged SHA-verified sidecar is absent."""
        with tempfile.TemporaryDirectory() as temporary:
            guest_root = Path(temporary)
            scripts = guest_root / 'sandbox' / 'scripts'
            scripts.mkdir(parents=True)
            guest_script = scripts / 'stage_guest.py'
            guest_script.write_bytes(SCRIPT.read_bytes())
            (scripts / 'oc2_agent_native.py').write_text(
                'unverified_ambient_helper = True\n', encoding='utf-8',
            )
            import_code = (
                'import importlib.util, pathlib, sys; '
                'path = pathlib.Path(sys.argv[1]); '
                'spec = importlib.util.spec_from_file_location("guest_stage", path); '
                'module = importlib.util.module_from_spec(spec); '
                'spec.loader.exec_module(module)'
            )
            result = subprocess.run(
                [sys.executable, '-S', '-c', import_code, str(guest_script)],
                capture_output=True, text=True, check=False, cwd=guest_root, env={'PATH': ''},
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SHA-verified Native Agent policy sidecar is missing', result.stderr)

    def test_guest_verify_rejects_path_in_cli_argument(self) -> None:
        """Reject a caller-selected Guest bundle path outside the fixed staging location."""
        with patch.object(stage, "REMOTE_PARENT", str(self.bundle.parent)):
            status = stage.main(["--verify-bundle", str(self.bundle)])
        self.assertEqual(status, 1)

    def test_host_stage_resolves_bundle_identifier_under_temp_root(self) -> None:
        """Resolve a generated bundle name beneath the Host temporary trusted root."""
        bundle_name = "opencode-v2-export-20261111"
        bundle = self.root.parent / bundle_name
        bundle.mkdir(mode=0o700)
        output = io.StringIO()
        with patch.object(stage, "BUNDLE_ROOT", self.root.parent, create=True), \
                patch.object(stage, "stage") as stage_bundle, \
                contextlib.redirect_stdout(output):
            status = stage.main(["--bundle", bundle_name, "--repo-root", str(self.root)])

        self.assertEqual(status, 0, output.getvalue())
        self.assertEqual(stage_bundle.call_args.args[0], bundle)

    def test_host_stage_rejects_path_in_bundle_argument(self) -> None:
        """Reject path syntax where the CLI contract accepts only a generated bundle name."""
        with patch.object(stage, "stage") as stage_bundle:
            status = stage.main(["--bundle", str(self.bundle), "--repo-root", str(self.root)])

        self.assertEqual(status, 1)
        stage_bundle.assert_not_called()

    def test_verifier_accepts_unified_manifest_with_provider_and_agents(self) -> None:
        apm = exporter._read_apm_source(REPO)
        generated = exporter._build_files(
            apm.shell, apm.snapshot, apm.source_sha256, apm.v2_config,
            unified_runtime=apm.unified_runtime,
        )
        for name, content in generated.items():
            (self.bundle / name).write_bytes(content)

        digest = stage.verify_bundle(self.bundle, trusted_root=stage.BUNDLE_ROOT)

        manifest = json.loads((self.bundle / "export-manifest.json").read_text())
        self.assertEqual(manifest["config_format"], "opencode-v2-unified")
        self.assertEqual(digest, hashlib.sha256(generated["export-manifest.json"]).hexdigest())

    def _make_v2_bundle(self) -> Path:
        self.apm.write_text(
            "provider:\n"
            "  openai:\n"
            "    whitelist: [gpt-6-luna]\n"
            "  cloudflare-ai-gateway-custom:\n"
            "    npm: '@ai-sdk/openai-compatible'\n"
            "    name: Cloudflare AI Gateway Custom\n"
            "    options:\n"
            "      baseURL: 'https://gateway.ai.cloudflare.com/v1/${env:OC_CF_ACCOUNT_ID}/${env:OC_CF_GATEWAY_ID}/compat'\n"
            "      apiKey: ''\n"
            "      headers:\n"
            "        cf-aig-authorization: 'Bearer ${env:OC_CF_API_TOKEN}'\n"
            "    models:\n"
            "      custom-ollama-cloud/kimi-k2.7-code:\n"
            "        name: Kimi K2.7 Code\n"
            "opencode_v2:\n"
            "  default_model: openai/gpt-6-luna\n"
            "  deny_provider_fallback: true\n"
            "  deny_guest_auth: true\n"
            "  providers:\n"
            "    openai:\n"
            "      enabled: true\n"
            "      auth_method: docker_openai_oauth\n"
            "    cloudflare-ai-gateway-custom:\n"
            "      enabled: true\n"
            "      auth_method: docker_custom_secret\n",
            encoding="utf-8",
        )
        bundle = self.root.parent / "v2-bundle"
        process = subprocess.run(
            [sys.executable, str(SCRIPT.parent / "prepare_opencode_v2.py"),
             "--repo-root", str(self.root), "--out", str(bundle)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        return bundle

    def test_verification_bundle_is_minimal_and_bound_to_apm_mode(self) -> None:
        """Verify the verification config_format and exact APM-derived bundle output."""
        self.apm.write_text(
            "shell: bash\nsnapshot: true\n"
            "x-oc2-assets: [global-rules/AGENTS.global.md]\n"
            "x-oc2-agents: {}\n"
            "x-oc2-plugins: {enabled: false, allowlist: [superpowers]}\n"
            "x-oc2-mcp: {enabled: false, servers: [oc2-status]}\n",
            encoding="utf-8",
        )
        bundle = self.root.parent / 'verification-bundle'
        process = subprocess.run(
            [sys.executable, str(SCRIPT.parent / 'prepare_opencode_v2.py'),
             '--repo-root', str(self.root), '--out', str(bundle), '--verification-only'],
            capture_output=True, text=True, check=False,
        )

        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(stage.verify_bundle(bundle, trusted_root=bundle.parent), hashlib.sha256(
            (bundle / 'export-manifest.json').read_bytes(),
        ).hexdigest())
        self.assertEqual(json.loads((bundle / 'export-manifest.json').read_text())[
            'config_format'], 'oc2-verification')
        self.assertEqual(json.loads((bundle / 'opencode.jsonc').read_text())['plugins'], [])
        stage._check_source(self.root, bundle)

    def test_v2_multi_provider_bundle_passes_stage_validation(self) -> None:
        bundle = self._make_v2_bundle()
        self.assertEqual(
            stage.verify_bundle(bundle, trusted_root=stage.BUNDLE_ROOT),
            hashlib.sha256((bundle / "export-manifest.json").read_bytes()).hexdigest(),
        )
        stage._check_source(self.root, bundle)

    def test_v2_multi_provider_bundle_rejects_extra_provider(self) -> None:
        bundle = self._make_v2_bundle()
        config_path = bundle / "opencode.jsonc"
        config = json.loads(config_path.read_text())
        config["providers"]["unapproved"] = {
            "models": {"model": {"modelID": "model", "name": "Unapproved"}},
        }
        config_path.write_text(json.dumps(config) + "\n", encoding="utf-8")
        manifest_path = bundle / "export-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["artifacts_sha256"]["opencode.jsonc"] = hashlib.sha256(
            config_path.read_bytes(),
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

        with self.assertRaises(stage.StageError):
            stage.verify_bundle(bundle, trusted_root=stage.BUNDLE_ROOT)

    def test_rejects_changed_config_and_extra_files(self) -> None:
        config = self.bundle / "cli.json"
        config.write_text("{}\n")
        with self.assertRaises(stage.StageError):
            stage.verify_bundle(self.bundle, trusted_root=stage.BUNDLE_ROOT)
        config.unlink()
        (self.bundle / "extra.txt").write_text("unknown")
        with self.assertRaises(stage.StageError):
            stage.verify_bundle(self.bundle, trusted_root=stage.BUNDLE_ROOT)

    def test_verify_bundle_rejects_paths_outside_temporary_staging(self) -> None:
        """Reject Host bundle paths outside the configured trusted staging root."""
        with self.assertRaisesRegex(stage.StageError, "outside the approved staging root"):
            stage.verify_bundle(Path("/etc"), trusted_root=stage.BUNDLE_ROOT)

    def test_rejects_symlinked_member(self) -> None:
        member = self.bundle / "cli.json"
        member.unlink()
        member.symlink_to(self.apm)
        with self.assertRaises(stage.StageError):
            stage.verify_bundle(self.bundle, trusted_root=stage.BUNDLE_ROOT)

    def test_regular_bytes_rejects_paths_outside_the_bundle_allowlist(self) -> None:
        outside = self.root / "opencode.jsonc"
        outside.write_text("must not be read", encoding="utf-8")

        with self.assertRaises(stage.StageError):
            stage._read_bundle_files(self.root, ["../opencode.jsonc"])

    def test_bundle_verifier_rejects_symlinked_parent(self) -> None:
        """Reject a bundle whose parent path traverses a symlink within the trusted root."""
        alias = self.root.parent / "parent-alias"
        alias.symlink_to(self.bundle.parent, target_is_directory=True)

        with self.assertRaises(stage.StageError):
            stage.verify_bundle(alias / self.bundle.name, trusted_root=stage.BUNDLE_ROOT)

    def test_bundle_verifier_rejects_path_traversal(self) -> None:
        """Reject a Guest bundle path that traverses outside the approved Guest workspace root."""
        with self.assertRaises(stage.StageError):
            stage.verify_bundle(self.bundle.parent / ".." / self.bundle.name,
                                trusted_root=stage.BUNDLE_ROOT)

    def test_rejects_plugin_or_mcp_config_even_with_updated_hash(self) -> None:
        manifest_file = self.bundle / "export-manifest.json"
        config_file = self.bundle / "opencode.jsonc"
        payload = json.loads(config_file.read_text())
        payload["plugins"] = ["unsafe"]
        config_file.write_text(json.dumps(payload))
        manifest = json.loads(manifest_file.read_text())
        manifest["artifacts_sha256"]["opencode.jsonc"] = hashlib.sha256(config_file.read_bytes()).hexdigest()
        manifest_file.write_text(json.dumps(manifest))
        with self.assertRaises(stage.StageError):
            stage.verify_bundle(self.bundle, trusted_root=stage.BUNDLE_ROOT)

    def test_dry_run_does_not_invoke_sbx(self) -> None:
        with patch.object(stage, "_check_source"), patch.object(stage, "_run") as run:
            stage.stage(self.bundle, self.root, sandbox=None, apply=False)
            run.assert_not_called()

    def test_host_provenance_failure_refuses_transfer(self) -> None:
        with patch.object(stage, "_check_source", side_effect=stage.StageError("bad source")), \
             patch.object(stage, "_run") as run:
            with self.assertRaises(stage.StageError):
                stage.stage(self.bundle, self.root, "oc-v2-poc", apply=True)
            run.assert_not_called()

    def test_apply_stages_and_verifies_without_activation(self) -> None:
        commands = []
        def capture(argv: list[str]) -> bytes:
            commands.append(argv)
            if argv[1] == "cp":
                self.assertTrue(Path(argv[2]).exists())
            if argv[1:4] == ["exec", "oc-v2-poc", "sha256sum"]:
                helper_sha = hashlib.sha256(
                    SCRIPT.with_name('oc2_agent_native.py').read_bytes(),
                ).hexdigest()
                return helper_sha.encode('ascii') + b'  helper.py\n'
            return b''
        with patch.object(stage, "_check_source"), \
             patch.object(stage.shutil, "which", return_value="/usr/bin/sbx"), \
             patch.object(stage, "_run", side_effect=capture):
            stage.stage(self.bundle, self.root, sandbox="oc-v2-poc", apply=True)
        self.assertEqual(len(commands), 6)
        self.assertEqual(
            [command[1] for command in commands],
            ["exec", "cp", "cp", "cp", "exec", "exec"],
        )
        remote = stage.REMOTE_PARENT + "/" + commands[-1][-1]
        self.assertTrue(remote.startswith(stage.REMOTE_PARENT + "/sbx-config-"))
        self.assertNotIn(".config/opencode", repr(commands))
        self.assertNotIn("--privileged", repr(commands))
        self.assertNotIn("-u", [argument for command in commands for argument in command])
        self.assertEqual(commands[-1][3], "python3")
        self.assertEqual(commands[2][-1], "oc-v2-poc:" + commands[-1][4])
        self.assertEqual(
            commands[3][-1],
            commands[2][-1] + '.native.py',
        )
        self.assertEqual(commands[4][1:4], ["exec", "oc-v2-poc", "sha256sum"])
        self.assertEqual(commands[4][-1], commands[3][-1].split(':', 1)[1])
        self.assertFalse(commands[-1][4].startswith(remote + "/"))
        self.assertEqual(commands[0][-2], commands[-1][4])
        self.assertEqual(commands[0][-1], commands[3][-1].split(':', 1)[1])

    def test_apply_requires_valid_sandbox_name(self) -> None:
        with patch.object(stage, "_check_source"), patch.object(stage, "_run") as run:
            for bad in (None, "../host", "bad:name", "", "-bad"):
                with self.subTest(bad=bad), self.assertRaises(stage.StageError):
                    stage.stage(self.bundle, self.root, bad, apply=True)
            run.assert_not_called()

    def test_source_check_refuses_missing_apm_source(self) -> None:
        with self.assertRaises(stage.StageError):
            stage._check_source(self.root, self.bundle)

    def test_source_check_verifies_snapshot_without_executing_a_process(self) -> None:
        shell, snapshot, source_hash = exporter._read_apm(self.root)
        generated = exporter._build_files(shell, snapshot, source_hash)
        for name, content in generated.items():
            (self.bundle / name).write_bytes(content)
        with patch.object(stage.subprocess, "run", side_effect=AssertionError("unexpected process")):
            stage._check_source(self.root, self.bundle)

    def test_no_live_host_paths_are_written(self) -> None:
        with patch.object(stage, "_check_source"), patch.object(stage, "_run"):
            stage.stage(self.bundle, self.root, None, False)
        self.assertFalse((self.root / ".config").exists())


if __name__ == "__main__":
    unittest.main()

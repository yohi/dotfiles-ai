import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).parent.parent
    / ".claude/skills/apm-updater/scripts/check_updates.py"
)
SPEC = importlib.util.spec_from_file_location("check_updates", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError("could not load check_updates")
check_updates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_updates)


class TestCheckUpdates(unittest.TestCase):
    def write_apm(self, content: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        apm_path = Path(temp_dir.name) / "apm.yml"
        apm_path.write_text(content, encoding="utf-8")
        return apm_path

    def test_validate_duplicates_normalizes_quoted_model_names(self):
        apm_path = self.write_apm(
            """provider:
  openai:
    whitelist:
      - openai/gpt-5
      - 'openai/gpt-5'
"""
        )

        with contextlib.redirect_stdout(io.StringIO()):
            result = check_updates.validate_duplicates(apm_path)

        self.assertEqual(result, 1)

    def test_validate_duplicates_keeps_provider_at_direct_child_indent(self):
        apm_path = self.write_apm(
            """provider:
  openai:
    options:
      name: OpenAI
    whitelist:
      - gpt-5
      - gpt-5
"""
        )

        with contextlib.redirect_stdout(io.StringIO()):
            result = check_updates.validate_duplicates(apm_path)

        self.assertEqual(result, 1)

    def test_validate_models_keeps_provider_at_direct_child_indent(self):
        apm_path = self.write_apm(
            """provider:
  openai:
    options:
      name: OpenAI
    whitelist:
      - missing-model
"""
        )

        with patch.object(
            check_updates,
            "fetch_model_schema",
            return_value={"$defs": {"Model": {"enum": []}}},
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                result = check_updates.validate_apm_models(apm_path)

        self.assertEqual(result, 1)

import unittest
import json
import io
import os
from typing import Any, Dict
from unittest.mock import patch
from skillport_stats import parse_input, get_env_status, print_stats

class TestSkillportStats(unittest.TestCase):
    def test_get_env_status(self):
        with patch.dict(os.environ, {
            "MCP_GATEWAY_STATUS": "active",
            "SKILLPORT_MCP_VERSION": "1.1.0",
            "SKILLPORT_MCP_STATUS": "active (Gateway)"
        }):
            gw, ver, status = get_env_status()
            self.assertEqual(gw, "active")
            self.assertEqual(ver, "1.1.0")
            self.assertEqual(status, "active (Gateway)")

    def test_parse_input_valid(self):
        test_data = {
            "skills": [
                {"id": "test/skill1"},
                {"id": "skill2"}
            ],
            "total": 2
        }
        with patch('sys.stdin', io.StringIO(json.dumps(test_data))):
            skills, total = parse_input()
            self.assertEqual(len(skills), 2)
            self.assertEqual(total, 2)
            self.assertEqual(skills[0]["id"], "test/skill1")

    def test_parse_input_invalid_missing_field(self):
        test_data: Dict[str, Any] = {"skills": []} # 'total' is missing
        with patch('sys.stdin', io.StringIO(json.dumps(test_data))):
            with self.assertRaises(ValueError) as cm:
                parse_input()
            self.assertIn("Missing required field 'total'", str(cm.exception))

    def test_print_stats_content(self):
        # 実際の出力内容を検証
        skills = [{"id": "test/skill1"}, {"id": "root-skill"}]
        total = 2
        with patch('sys.stdout', new=io.StringIO()) as fake_out:
            print_stats(skills, total, "active (Gateway)", "1.1.0", "active")
            output = fake_out.getvalue()
            
            self.assertIn("Total Skills: 2", output)
            self.assertIn("1.1.0", output)
            self.assertIn("active (Gateway)", output)
            self.assertIn("test", output) # Namespace
            self.assertIn("root-skill", output) # Root skill ID

if __name__ == '__main__':
    unittest.main()

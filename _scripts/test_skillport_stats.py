import unittest
import json
import io
import os
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

    def test_print_stats_no_error(self):
        # 実際に標準出力に書き出すが、エラーが出ないことを確認
        skills = [{"id": "ns/s1"}, {"id": "root1"}]
        total = 2
        with patch('sys.stdout', new=io.StringIO()):
            try:
                print_stats(skills, total, "active", "1.0.0", "active")
            except Exception as e:
                self.fail(f"print_stats raised {type(e).__name__} unexpectedly!")

if __name__ == '__main__':
    unittest.main()

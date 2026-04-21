import unittest
import os
import re
import json

def strip_jsonc_comments(text):
    """Remove // and /* */ comments from JSONC text, preserving layout with spaces and newlines."""
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            # Replace non-newline characters with spaces to maintain layout
            return re.sub(r'[^\r\n]', ' ', s)
        else:
            return s
    
    # Match strings, block comments, or line comments
    # 1. Strings: "(?:\\.|[^\\"])*"
    # 2. Block comments: /\*.*?\*/
    # 3. Line comments: //[^\r\n]*
    pattern = r'("(?:\\.|[^\\"])*")|(/\*.*?\*/)|(//[^\r\n]*)'
    return re.sub(pattern, replacer, text, flags=re.DOTALL)

class TestConfigIntegrity(unittest.TestCase):
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    HOME_PATH = os.path.expanduser('~')

    def test_agents_global_md_integrity(self):
        """Verify that AGENTS.global.md has required sections and follows mandates."""
        path = os.path.join(self.PROJECT_ROOT, 'global-rules', 'AGENTS.global.md')
        self.assertTrue(os.path.exists(path), f"File not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Required Headers (Check titles only, ignoring numeric prefixes)
        required_titles = [
            "User Global Instructions (System Wide)",
            "Identity & Core Philosophy",
            "Language Policy (CRITICAL)",
            "Universal Mandates (CRITICAL)",
            "Universal Coding Standards",
            "Workflow & Context Awareness",
            "SkillPort Skills",
            "Agent-Specific Contexts (Unified)",
            "BEGIN Superpowers Workflow",
            "ChronosGraph Memory System (Autonomous)"
        ]
        
        # Parse headers: remove leading markdown (###) and numeric prefix (1.)
        parsed_headers = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('#'):
                # Strip #s and initial numbering like "## 4."
                title = re.sub(r'^#+\s*(\d+\.)?\s*', '', line).strip()
                parsed_headers.append(title)
        
        for title in required_titles:
            self.assertTrue(any(title in h for h in parsed_headers), f"Missing required section title: {title}")

        # Mandate specific checks
        self.assertIn("- **No Absolute Paths**:", content)
        self.assertIn("- **Credential Protection**:", content)

        # Ensure no personal paths (Dynamic check for current HOME)
        self.assertNotIn(self.HOME_PATH, content, f"Personal absolute path ({self.HOME_PATH}) detected in AGENTS.global.md")

    def test_no_hardcoded_personal_paths_in_repo(self):
        """Scan for current HOME path in critical files tracked by Git."""
        import subprocess
        
        try:
            # Get list of files tracked by Git
            result = subprocess.run(['git', 'ls-files'], capture_output=True, text=True, check=True)
            tracked_files = result.stdout.splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to manual walk if not in a git repo or git is missing
            tracked_files = []
            for root, dirs, files in os.walk(self.PROJECT_ROOT):
                for file in files:
                    tracked_files.append(os.path.relpath(os.path.join(root, file), self.PROJECT_ROOT))

        extensions_to_check = ('.md', '.json', '.jsonc', '.template', '.sh', '.py', '.mk')
        
        found_paths = []
        read_errors = []
        for rel_path in tracked_files:
            if rel_path.endswith(extensions_to_check):
                full_path = os.path.join(self.PROJECT_ROOT, rel_path)
                # Skip the test file itself
                if os.path.abspath(full_path) == os.path.abspath(__file__):
                    continue
                
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if self.HOME_PATH in content:
                            found_paths.append(rel_path)
                except (UnicodeDecodeError, FileNotFoundError, OSError) as e:
                    read_errors.append(f"{rel_path}: {str(e)}")

        if read_errors:
            # Report errors but don't fail immediately unless found_paths also has issues
            # Or should we fail on read errors? Usually yes.
            pass

        msg = f"Hardcoded personal paths ({self.HOME_PATH}) found in tracked files: {found_paths}"
        if read_errors:
            msg += f"\nRead errors encountered: {read_errors}"
        
        self.assertEqual(found_paths, [], msg)
        self.assertEqual(read_errors, [], msg)

    def test_json_templates_validity(self):
        """Verify that .template files are valid JSON/JSONC."""
        # Only check tracked template files
        import subprocess
        try:
            result = subprocess.run(['git', 'ls-files', '*.template', '*.jsonc'], capture_output=True, text=True, check=True)
            template_files = [os.path.join(self.PROJECT_ROOT, f) for f in result.stdout.splitlines()]
        except (subprocess.CalledProcessError, FileNotFoundError):
            template_files = []

        for path in template_files:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            try:
                # Strip comments and try parsing
                stripped = strip_jsonc_comments(content)
                # Remove trailing commas (a common JSONC feature)
                stripped = re.sub(r',\s*([\]}])', r'\1', stripped, flags=re.MULTILINE)
                if stripped.strip():
                    # Use strict=False to allow control characters in strings
                    json.loads(stripped, strict=False)
            except json.JSONDecodeError as e:
                self.fail(f"Invalid JSON/JSONC syntax in {path}: {e}")

if __name__ == '__main__':
    unittest.main()

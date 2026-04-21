import unittest
import os
import re
import json
import subprocess
import shutil

def strip_jsonc_comments(text):
    """Remove // and /* */ comments from JSONC text, preserving layout."""
    def replacer(match):
        s = match.group(0)
        return re.sub(r'[^\r\n]', ' ', s) if s.startswith('/') else s
    pattern = r'("(?:\\.|[^\\"])*")|(/\*.*?\*/)|(//[^\r\n]*)'
    return re.sub(pattern, replacer, text, flags=re.DOTALL)

def remove_trailing_commas_safe(text):
    """Remove trailing commas in JSON-like structures while ignoring strings and comments."""
    result = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        char = text[i]
        if in_string:
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                in_string = False
            result.append(char)
        else:
            if char == '"':
                in_string = True
                result.append(char)
            elif char == ',':
                j = i + 1
                while j < len(text) and text[j].isspace():
                    j += 1
                if j < len(text) and text[j] in (']', '}'):
                    i = j - 1 
                else:
                    result.append(char)
            else:
                result.append(char)
        i += 1
    return "".join(result)

class TestConfigIntegrity(unittest.TestCase):
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    def setUp(self):
        # Build a set of candidate home path patterns for cross-OS detection
        self.home_candidates = {
            os.path.expanduser('~'),
            os.path.normpath(os.path.expanduser('~')),
        }
        # Common OS home prefixes to detect other users' paths
        current_user = os.environ.get('USER') or os.environ.get('USERNAME') or 'user'
        for p in ['/home/', '/Users/', 'C:\\Users\\']:
            # Current user's potential cross-OS paths
            self.home_candidates.add(os.path.normpath(os.path.join(p, current_user)))
        
        # Regex to catch general home directory patterns (e.g., /home/anyone/...)
        # We look for home-like prefixes followed by a user-like segment.
        # We exclude common placeholders and container system users.
        self.home_regex = re.compile(
            r'(?:/home/|/Users/|C:\\Users\\)(?!username|user|<[^>]+>|skillport)[^/\s"\'\\]+'
        )
        
        # Resolve git binary once to satisfy security scanners
        self.git_bin = shutil.which('git') or 'git'

    def _get_tracked_files(self, pattern=None):
        """Get list of files tracked by Git, with fallback to manual walk."""
        try:
            cmd = [self.git_bin, 'ls-files']
            if pattern:
                cmd.append(pattern)
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError):
            files_list = []
            for root, _dirs, files in os.walk(self.PROJECT_ROOT):
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), self.PROJECT_ROOT)
                    if pattern and not rel_path.endswith(pattern.replace('*', '')):
                        continue
                    files_list.append(rel_path)
            return files_list

    def test_agents_global_md_integrity(self):
        """Verify that AGENTS.global.md has required sections and follows mandates."""
        path = os.path.join(self.PROJECT_ROOT, 'global-rules', 'AGENTS.global.md')
        self.assertTrue(os.path.exists(path), f"File not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Required Headers
        required_titles = [
            "User Global Instructions", "Identity & Core Philosophy", "Language Policy",
            "Universal Mandates", "Universal Coding Standards", "Workflow & Context Awareness",
            "SkillPort Skills", "Agent-Specific Contexts", "BEGIN Superpowers Workflow",
            "ChronosGraph Memory System"
        ]
        
        parsed_headers = [re.sub(r'^#+\s*(\d+\.)?\s*', '', line).strip() 
                          for line in content.splitlines() if line.strip().startswith('#')]
        
        for title in required_titles:
            self.assertTrue(any(title in h for h in parsed_headers), f"Missing required section: {title}")

        # Personal Path Check (Explicit candidates + Regex)
        for home in self.home_candidates:
            self.assertNotIn(home, content, f"Personal path leak ({home}) detected in AGENTS.global.md")
        
        # Ignore false positives like variable placeholders
        clean_content = content.replace('${HOME}', '').replace('__HOME__', '')
        match = self.home_regex.search(clean_content)
        if match:
            self.fail(f"Potential absolute path leak detected in AGENTS.global.md: {match.group(0)}")

    def test_no_hardcoded_personal_paths_in_repo(self):
        """Scan for absolute personal paths in critical files tracked by Git."""
        tracked_files = self._get_tracked_files()
        extensions = ('.md', '.json', '.jsonc', '.template', '.sh', '.py', '.mk')
        
        found_paths = []
        read_errors = []
        for rel_path in tracked_files:
            if not rel_path.endswith(extensions):
                continue
            full_path = os.path.join(self.PROJECT_ROOT, rel_path)
            if os.path.abspath(full_path) == os.path.abspath(__file__):
                continue
            
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 1. Check known candidates
                    for home in self.home_candidates:
                        if home in content:
                            found_paths.append(f"{rel_path} ({home})")
                            break
                    # 2. Check general pattern (excluding placeholders)
                    clean_content = content.replace('${HOME}', '').replace('__HOME__', '')
                    match = self.home_regex.search(clean_content)
                    if match and rel_path not in [f.split(' ')[0] for f in found_paths]:
                        found_paths.append(f"{rel_path} (Pattern: {match.group(0)})")
            except FileNotFoundError:
                continue
            except (UnicodeDecodeError, OSError) as e:
                read_errors.append(f"{rel_path}: {str(e)}")

        msg = f"Personal paths detected: {found_paths}"
        if read_errors:
            msg += f"\nRead errors: {read_errors}"
        self.assertEqual(found_paths, [], msg)
        self.assertEqual(read_errors, [], msg)

    def test_json_templates_validity(self):
        """Verify that .template and .jsonc files are valid JSON/JSONC."""
        files = self._get_tracked_files('*.template') + self._get_tracked_files('*.jsonc')

        for rel_path in files:
            path = os.path.join(self.PROJECT_ROOT, rel_path)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            try:
                stripped = strip_jsonc_comments(content)
                cleaned = remove_trailing_commas_safe(stripped)
                if cleaned.strip():
                    json.loads(cleaned, strict=False)
            except json.JSONDecodeError as e:
                self.fail(f"Invalid JSON/JSONC in {rel_path}: {e}")

if __name__ == '__main__':
    unittest.main()

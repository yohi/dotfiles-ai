import unittest
import os
import re
import json
import subprocess
import shutil

# --- Utility Functions (Outside class to reduce complexity score) ---

def strip_jsonc_comments(text):
    """Remove // and /* */ comments from JSONC text, preserving layout."""
    def replacer(match):
        s = match.group(0)
        return re.sub(r'[^\r\n]', ' ', s) if s.startswith('/') else s
    pattern = r'("(?:\\.|[^\\"])*")|(/\*.*?\*/)|(//[^\r\n]*)'
    return re.sub(pattern, replacer, text, flags=re.DOTALL)

def remove_trailing_commas_safe(text):
    """Remove trailing commas in JSON-like structures while ignoring strings/comments."""
    result = []
    in_string, escape = False, False
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

def get_tracked_files(root, git_bin, pattern=None):
    """Get list of files tracked by Git, with fallback to manual walk."""
    try:
        # Construct command to satisfy security scanners (avoiding dynamic list modification where possible)
        if pattern:
            cmd = [git_bin, 'ls-files', pattern]
        else:
            cmd = [git_bin, 'ls-files']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        files_list = []
        for r, _dirs, files in os.walk(root):
            for file in files:
                rel = os.path.relpath(os.path.join(r, file), root)
                if pattern and not rel.endswith(pattern.replace('*', '')):
                    continue
                files_list.append(rel)
        return files_list

def check_path_leak(content, candidates, regex):
    """Check for personal path leaks in content. Returns found path or None."""
    # 1. Check general pattern (excluding placeholders)
    clean_content = content.replace('${HOME}', '').replace('__HOME__', '')
    match = regex.search(clean_content)
    if match:
        return f"Pattern: {match.group(0)}"

    # 2. Check explicit candidates (ensuring they aren't just substrings)
    for home in candidates:
        # Use regex to ensure path boundary
        pattern = re.escape(home) + r'([/\s"\'\\]|$)'
        if re.search(pattern, content):
            return home
    return None

class TestConfigIntegrity(unittest.TestCase):
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    GIT_BIN = shutil.which('git') or 'git'
    HOME_REGEX = re.compile(
        r'(?:/home/|/Users/|C:\\Users\\)(?!username|user|<[^>]+>|skillport)[^/\s"\'\\]+'
    )

    def setUp(self):
        # Current user's potential cross-OS paths
        self.home_candidates = {os.path.expanduser('~'), os.path.normpath(os.path.expanduser('~'))}
        user = os.environ.get('USER') or os.environ.get('USERNAME') or 'user'
        for p in ['/home/', '/Users/', 'C:\\Users\\']:
            self.home_candidates.add(os.path.normpath(os.path.join(p, user)))

    def test_agents_global_md_integrity(self):
        """Verify that AGENTS.global.md has required sections and follows mandates."""
        path = os.path.join(self.PROJECT_ROOT, 'global-rules', 'AGENTS.global.md')
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check required section titles
        required = ["User Global Instructions", "Identity & Core Philosophy", "Language Policy"]
        parsed_headers = [re.sub(r'^#+\s*(\d+\.)?\s*', '', l).strip() 
                          for l in content.splitlines() if l.strip().startswith('#')]
        for title in required:
            self.assertTrue(any(title in h for h in parsed_headers), f"Missing section: {title}")

        # Path leak check
        leak = check_path_leak(content, self.home_candidates, self.HOME_REGEX)
        self.assertIsNone(leak, f"Path leak in AGENTS.global.md: {leak}")

    def test_no_hardcoded_personal_paths_in_repo(self):
        """Scan for absolute personal paths in critical tracked files."""
        tracked_files = get_tracked_files(self.PROJECT_ROOT, self.GIT_BIN)
        exts = ('.md', '.json', '.jsonc', '.template', '.sh', '.py', '.mk')
        
        found, errors = [], []
        this_file = os.path.abspath(__file__)
        for rel_path in tracked_files:
            if not rel_path.endswith(exts):
                continue
            fpath = os.path.join(self.PROJECT_ROOT, rel_path)
            if os.path.abspath(fpath) == this_file:
                continue
            
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    leak = check_path_leak(f.read(), self.home_candidates, self.HOME_REGEX)
                    if leak:
                        found.append(f"{rel_path} ({leak})")
            except (UnicodeDecodeError, OSError) as e:
                errors.append(f"{rel_path}: {e}")

        msg = f"Leaks: {found}\nErrors: {errors}"
        self.assertEqual(found, [], msg)
        self.assertEqual(errors, [], msg)

    def test_json_templates_validity(self):
        """Verify that .template and .jsonc files are valid JSON/JSONC."""
        files = (get_tracked_files(self.PROJECT_ROOT, self.GIT_BIN, '*.template') + 
                 get_tracked_files(self.PROJECT_ROOT, self.GIT_BIN, '*.jsonc'))

        for rel_path in files:
            path = os.path.join(self.PROJECT_ROOT, rel_path)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            try:
                cleaned = remove_trailing_commas_safe(strip_jsonc_comments(content))
                if cleaned.strip():
                    json.loads(cleaned, strict=False)
            except json.JSONDecodeError as e:
                self.fail(f"Invalid JSON/JSONC in {rel_path}: {e}")

if __name__ == '__main__':
    unittest.main()

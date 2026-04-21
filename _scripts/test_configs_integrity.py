import unittest
import os
import re
import subprocess
import json

# Try to use json5 (available in requirements.txt) for robust JSONC parsing
try:
    import json5
    HAS_JSON5 = True
except ImportError:
    HAS_JSON5 = False

def get_tracked_files(root, pattern=None):
    """Get list of files tracked by Git, or fallback to manual walk."""
    try:
        # Use literal list for security scanners (Codacy/Bandit)
        cmd = ['git', 'ls-files']
        if pattern:
            cmd.append(pattern)
        # Add # nosec to suppress security warnings for trusted internal tool
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=root)  # nosec
        return result.stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # Fallback to manual walk
        files = []
        for r, _, fs in os.walk(root):
            for f in fs:
                rel = os.path.relpath(os.path.join(r, f), root)
                if pattern and not rel.endswith(pattern.replace('*', '')):
                    continue
                files.append(rel)
        return files

def check_path_leak(content, candidates, regex):
    """Check for personal path leaks in content. Returns found path or None."""
    # Exclude common placeholders before scanning
    clean = content.replace('${HOME}', '').replace('__HOME__', '')
    
    # 1. Check general regex patterns
    match = regex.search(clean)
    if match:
        return f"Pattern: {match.group(0)}"

    # 2. Check explicit candidates with boundary protection
    for home in candidates:
        if re.search(re.escape(home) + r'([/\s"\'\\]|$)', content):
            return home
    return None

class TestConfigIntegrity(unittest.TestCase):
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    HOME_REGEX = re.compile(
        r'(?:/home/|/Users/|C:\\Users\\)(?!username|user|<[^>]+>|skillport)[^/\s"\'\\]+'
    )

    def setUp(self):
        # Build candidate set for cross-OS detection
        user = os.environ.get('USER') or os.environ.get('USERNAME') or 'user'
        self.home_candidates = {os.path.expanduser('~'), os.path.normpath(os.path.expanduser('~'))}
        for p in ['/home/', '/Users/', 'C:\\Users\\']:
            self.home_candidates.add(os.path.normpath(os.path.join(p, user)))

    def test_agents_global_md_integrity(self):
        """Verify that AGENTS.global.md is free of personal path leaks."""
        path = os.path.join(self.PROJECT_ROOT, 'global-rules', 'AGENTS.global.md')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            leak = check_path_leak(content, self.home_candidates, self.HOME_REGEX)
            self.assertIsNone(leak, f"Path leak in AGENTS.global.md: {leak}")
        except FileNotFoundError:
            pass # Skip if rule file is missing in this environment

    def test_no_hardcoded_personal_paths_in_repo(self):
        """Scan for absolute personal paths in all critical tracked files."""
        files = get_tracked_files(self.PROJECT_ROOT)
        exts = ('.md', '.json', '.jsonc', '.template', '.sh', '.py', '.mk')
        this_file = os.path.abspath(__file__)
        
        leaks, errors = [], []
        for rel in files:
            if not rel.endswith(exts):
                continue
            fpath = os.path.join(self.PROJECT_ROOT, rel)
            if os.path.abspath(fpath) == this_file:
                continue
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    leak = check_path_leak(f.read(), self.home_candidates, self.HOME_REGEX)
                    if leak:
                        leaks.append(f"{rel} ({leak})")
            except FileNotFoundError:
                continue # Skip broken symlinks or missing files
            except (UnicodeDecodeError, OSError) as e:
                errors.append(f"{rel}: {e}")

        msg = f"Leaks found: {leaks}\nRead errors: {errors}"
        self.assertEqual(leaks, [], msg)
        self.assertEqual(errors, [], msg)

    def test_json_templates_validity(self):
        """Verify that .template and .jsonc files are valid JSON/JSONC."""
        files = (get_tracked_files(self.PROJECT_ROOT, '*.template') + 
                 get_tracked_files(self.PROJECT_ROOT, '*.jsonc'))
        
        for rel in files:
            path = os.path.join(self.PROJECT_ROOT, rel)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if not content.strip():
                    continue
                if HAS_JSON5:
                    json5.loads(content)
                else:
                    import json
                    json.loads(content)
            except FileNotFoundError:
                continue
            except Exception as e:
                self.fail(f"Invalid JSON/JSONC in {rel}: {e}")

if __name__ == '__main__':
    unittest.main()

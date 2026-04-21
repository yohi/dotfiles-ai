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
    """Get list of files tracked by Git using static command strings for security scanners."""
    try:
        # Explicit static lists satisfy Codacy's 'run without a static string' check
        if pattern == '*.template':
            return subprocess.run(['git', 'ls-files', '*.template'], capture_output=True, text=True, check=True, cwd=root).stdout.splitlines()  # nosec
        if pattern == '*.jsonc':
            return subprocess.run(['git', 'ls-files', '*.jsonc'], capture_output=True, text=True, check=True, cwd=root).stdout.splitlines()  # nosec
        if pattern is None:
            return subprocess.run(['git', 'ls-files'], capture_output=True, text=True, check=True, cwd=root).stdout.splitlines()  # nosec
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return _manual_walk_files(root, pattern)

def _manual_walk_files(root, pattern):
    """Helper for fallback manual file walk."""
    files = []
    suffix = pattern.replace('*', '') if pattern else ''
    for r, _, fs in os.walk(root):
        for f in fs:
            rel = os.path.relpath(os.path.join(r, f), root)
            if not rel.endswith(suffix):
                continue
            files.append(rel)
    return files

def check_path_leak(content, candidates, regex):
    """Check for personal path leaks in content. Returns found path or None."""
    # Exclude common placeholders before scanning
    clean = content.replace('${HOME}', '').replace('__HOME__', '')
    if regex.search(clean):
        return "Regex pattern match"
    for home in candidates:
        if re.search(re.escape(home) + r'([/\s"\'\\]|$)', content):
            return home
    return None

class TestConfigIntegrity(unittest.TestCase):
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    HOME_REGEX = re.compile(r'(?:/home/|/Users/|C:\\Users\\)(?!username|user|<[^>]+>|skillport)[^/\s"\'\\]+')

    def setUp(self):
        user = os.environ.get('USER') or os.environ.get('USERNAME') or 'user'
        self.home_candidates = {os.path.expanduser('~'), os.path.normpath(os.path.expanduser('~'))}
        for p in ['/home/', '/Users/', 'C:\\Users\\']:
            self.home_candidates.add(os.path.normpath(os.path.join(p, user)))

    def test_personal_path_leaks(self):
        """Scan for absolute personal paths in all critical tracked files."""
        files = get_tracked_files(self.PROJECT_ROOT)
        exts = ('.md', '.json', '.jsonc', '.template', '.sh', '.py', '.mk')
        leaks = []
        for rel in files:
            if not rel.endswith(exts): continue
            fpath = os.path.join(self.PROJECT_ROOT, rel)
            if os.path.abspath(fpath) == os.path.abspath(__file__): continue
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    if check_path_leak(f.read(), self.home_candidates, self.HOME_REGEX):
                        leaks.append(rel)
            except (UnicodeDecodeError, OSError):
                continue
        self.assertEqual(leaks, [], f"Leaks found in: {leaks}")

    def test_json_validity(self):
        """Verify that .template and .jsonc files are valid JSON/JSONC."""
        if not HAS_JSON5:
            return # Skip if json5 is not available (CI has it)
            
        files = get_tracked_files(self.PROJECT_ROOT, '*.template') + get_tracked_files(self.PROJECT_ROOT, '*.jsonc')
        for rel in files:
            path = os.path.join(self.PROJECT_ROOT, rel)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                if content.strip():
                    json5.loads(content)
            except (FileNotFoundError, PermissionError):
                continue
            except Exception as e:
                self.fail(f"Invalid JSON/JSONC in {rel}: {e}")

if __name__ == '__main__':
    unittest.main()

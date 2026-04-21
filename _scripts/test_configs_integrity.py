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

def strip_jsonc_comments(content):
    """Simple regex-based JSONC comment stripper for environments without json5."""
    # Remove block comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    # Remove single line comments
    content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
    return content

def get_tracked_files(root, pattern=None):
    """Get list of files tracked by Git, or fallback to manual walk."""
    try:
        # Use explicit list for security scanners (Codacy/Bandit)
        # shell=False is default but explicitly provided for clarity
        if pattern:
            cmd = ['git', 'ls-files', pattern]
        else:
            cmd = ['git', 'ls-files']
            
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=root, shell=False)  # nosec
        return result.stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # Fallback to manual walk
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
        if not os.path.exists(path):
            return
            
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        leak = check_path_leak(content, self.home_candidates, self.HOME_REGEX)
        self.assertIsNone(leak, f"Path leak in AGENTS.global.md: {leak}")

    def _scan_file_for_leaks(self, rel_path, exts):
        """Helper to scan a single file for leaks. Returns (leak_info, error_info)."""
        if not rel_path.endswith(exts):
            return None, None
            
        fpath = os.path.join(self.PROJECT_ROOT, rel_path)
        # Skip this script itself
        if os.path.abspath(fpath) == os.path.abspath(__file__):
            return None, None
            
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                leak = check_path_leak(f.read(), self.home_candidates, self.HOME_REGEX)
                if leak:
                    return f"{rel_path} ({leak})", None
        except FileNotFoundError:
            return None, None
        except (UnicodeDecodeError, OSError) as e:
            return None, f"{rel_path}: {e}"
        return None, None

    def test_no_hardcoded_personal_paths_in_repo(self):
        """Scan for absolute personal paths in all critical tracked files."""
        files = get_tracked_files(self.PROJECT_ROOT)
        exts = ('.md', '.json', '.jsonc', '.template', '.sh', '.py', '.mk')
        
        leaks, errors = [], []
        for rel in files:
            leak, error = self._scan_file_for_leaks(rel, exts)
            if leak:
                leaks.append(leak)
            if error:
                errors.append(error)

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
                    # Fallback for environments without json5
                    json.loads(strip_jsonc_comments(content))
            except (FileNotFoundError, PermissionError):
                continue
            except Exception as e:
                self.fail(f"Invalid JSON/JSONC in {rel}: {e}")

if __name__ == '__main__':
    unittest.main()

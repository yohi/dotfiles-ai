import unittest
import os
import re
import subprocess  # nosec
import shutil
from types import ModuleType

import yaml

# Try to use json5 (available in requirements.txt) for robust JSONC parsing
json5: ModuleType | None
try:
    import json5 as json5_module

    json5 = json5_module
except ImportError:
    json5 = None


def get_tracked_files(root, pattern=None):
    """Get list of files tracked by Git using static command strings."""
    git_path = shutil.which("git")
    if not git_path:
        return _manual_walk_files(root, pattern)

    try:
        # Static strings satisfy Codacy/Bandit (B603).
        # S607 is mitigated by the shutil.which check above.
        if pattern == "*.template":
            return subprocess.run(
                ["git", "ls-files", "--", "*.template"],
                capture_output=True,
                text=True,
                check=True,
                cwd=root,
            ).stdout.splitlines()  # nosec B603 B607
        if pattern == "*.jsonc":
            return subprocess.run(
                ["git", "ls-files", "--", "*.jsonc"],
                capture_output=True,
                text=True,
                check=True,
                cwd=root,
            ).stdout.splitlines()  # nosec B603 B607
        if pattern is None:
            return subprocess.run(
                ["git", "ls-files"],
                capture_output=True,
                text=True,
                check=True,
                cwd=root,
            ).stdout.splitlines()  # nosec B603 B607
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return _manual_walk_files(root, pattern)


def _manual_walk_files(root, pattern):
    """Helper for fallback manual file walk."""
    files = []
    suffix = pattern.replace("*", "") if pattern else ""
    for r, _, fs in os.walk(root):
        for f in fs:
            rel = os.path.relpath(os.path.join(r, f), root)
            if rel.endswith(suffix):
                files.append(rel)
    return files


def check_path_leak(content: str, candidates: set[str], regex: re.Pattern) -> bool:
    """Check for personal path leaks in file content.

    Scans the given content for absolute home-directory paths that could
    expose the user's personal username or machine name. First, strips
    placeholder tokens like ${HOME} or __HOME__, then applies the regex
    and falls back to literal candidate checks.

    Args:
        content: The text to scan, typically a whole file read as a string.
        candidates: A set of literal home-directory paths (e.g., {'/home/alice'}).
        regex: A compiled re.Pattern that matches known home-directory prefixes.

    Returns:
        True if a personal path leak is detected, False otherwise.
    """
    clean = content.replace("${HOME}", "").replace("__HOME__", "")
    if regex.search(clean):
        return True
    for home in candidates:
        if re.search(re.escape(home) + r'([/\s"\'\\]|$)', content):
            return True
    return False


class TestConfigIntegrity(unittest.TestCase):
    PROJECT_ROOT: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    HOME_REGEX: re.Pattern[str] = re.compile(
        r'(?:/home/|/Users/|C:\\Users\\)(?!(?:username|user|<[^>]+>|skillport)(?:[/\s"\'\\`,.:;()]|$))[^/\s"\'\\`,.:;()]+'
    )
    home_candidates: set[str]

    def setUp(self):
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
        self.home_candidates = {
            os.path.expanduser("~"),
            os.path.normpath(os.path.expanduser("~")),
        }
        for p in ["/home/", "/Users/", "C:\\Users\\"]:
            self.home_candidates.add(os.path.normpath(os.path.join(p, user)))

    def test_personal_path_leaks(self):
        """Scan for absolute personal paths in tracked files."""
        files = get_tracked_files(self.PROJECT_ROOT)
        exts = (".md", ".json", ".jsonc", ".template", ".sh", ".py", ".mk")
        leaks = []
        read_errors = []
        for rel in files:
            if not rel.endswith(exts):
                continue
            fpath = os.path.join(self.PROJECT_ROOT, rel)
            if os.path.abspath(fpath) == os.path.abspath(__file__):
                continue
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    if check_path_leak(f.read(), self.home_candidates, self.HOME_REGEX):
                        leaks.append(rel)
            except (UnicodeDecodeError, OSError) as e:
                if not isinstance(e, FileNotFoundError):
                    read_errors.append(f"{rel}: {e}")
                continue
        self.assertEqual(leaks, [], f"Leaks found in: {leaks}")
        self.assertEqual(read_errors, [], f"Read errors encountered: {read_errors}")

    def test_json_validity(self):
        if json5 is None:
            self.fail(
                "json5 (json5>=0.9.22) is required for JSONC parsing. Please install it via pip or uv."
            )
        files = get_tracked_files(self.PROJECT_ROOT, "*.template") + get_tracked_files(
            self.PROJECT_ROOT, "*.jsonc"
        )
        for rel in files:
            path = os.path.join(self.PROJECT_ROOT, rel)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if content.strip():
                    if rel.endswith((".yaml.template", ".yml.template")):
                        content = re.sub(r"__[A-Za-z0-9_]+__", "placeholder", content)
                        content = re.sub(r"\$\{[A-Za-z0-9_]+\}", "placeholder", content)
                        yaml.safe_load(content)
                    else:
                        content = re.sub(r"\$\{[A-Za-z0-9_]+\}", "true", content)
                        json5.loads(content)
            except FileNotFoundError:
                continue
            except (UnicodeDecodeError, OSError, yaml.YAMLError) as e:
                self.fail(f"Invalid config in {rel}: {e}")
            except Exception as e:
                # Only swallow parsing errors from the json5 module; propagate
                # unexpected programming errors so they are not masked.
                if (
                    json5 is not None
                    and hasattr(json5, "Json5Exception")
                    and isinstance(e, json5.Json5Exception)
                ):
                    self.fail(f"Invalid config in {rel}: {e}")
                raise


if __name__ == "__main__":
    unittest.main()

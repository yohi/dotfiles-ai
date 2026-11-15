"""Fixed offline Writer fixture; no Host apply, network, hooks or user scripts."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import subprocess

FIXTURE_NAME = 'oc2-slice-b-fixture.txt'
FIXTURE_BYTES = b'OC2 Slice B offline fixture PASS\n'
FIXTURE_MESSAGE = 'test(oc2): verify offline writer fixture'
FIXTURE_USER = 'OC2 Slice B Fixture'
FIXTURE_EMAIL = 'oc2-slice-b-fixture@example.invalid'
FIXTURE_DATE = '2000-01-01T00:00:00 +0000'


class SliceBFixtureError(RuntimeError):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> bytes:
    env = {
        'HOME':'/nonexistent','PATH':'/usr/bin:/bin','LC_ALL':'C',
        'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_SYSTEM':'/dev/null',
        'GIT_CONFIG_NOSYSTEM':'1','GIT_NO_REPLACE_OBJECTS':'1',
        'GIT_TERMINAL_PROMPT':'0','GIT_OPTIONAL_LOCKS':'0',
        'GIT_AUTHOR_NAME':FIXTURE_USER,'GIT_AUTHOR_EMAIL':FIXTURE_EMAIL,
        'GIT_COMMITTER_NAME':FIXTURE_USER,'GIT_COMMITTER_EMAIL':FIXTURE_EMAIL,
        'GIT_AUTHOR_DATE':FIXTURE_DATE,'GIT_COMMITTER_DATE':FIXTURE_DATE,
        'GIT_CONFIG_COUNT':'3',
        'GIT_CONFIG_KEY_0':'core.hooksPath','GIT_CONFIG_VALUE_0':'/dev/null',
        'GIT_CONFIG_KEY_1':'commit.gpgSign','GIT_CONFIG_VALUE_1':'false',
        'GIT_CONFIG_KEY_2':'core.fsmonitor','GIT_CONFIG_VALUE_2':'false',
    }
    try:
        p = subprocess.run(['git',*args],cwd=repo,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,timeout=10)
    except (OSError,subprocess.TimeoutExpired) as e:
        raise SliceBFixtureError('bounded Git unavailable') from e
    if p.returncode and check:
        raise SliceBFixtureError('fixed Git operation failed; preserve state')
    if len(p.stdout)>2*1024*1024:
        raise SliceBFixtureError('Git observation exceeded bound')
    return p.stdout


def _snapshot(repo:Path):
    # Capture non-fixture Index entries, including staged blobs and modes;
    # capture all existing non-fixture working files without writing them.
    staged = _git(repo,'ls-files','--stage','-z').split(b'\0')
    index = tuple(x for x in staged if x and not x.endswith(b'\t'+FIXTURE_NAME.encode()))
    files = []
    for path in sorted(repo.iterdir()):
        if path.name in ('.git',FIXTURE_NAME):
            continue
        if path.is_symlink():
            raise SliceBFixtureError('unsafe path in working tree')
        if path.is_file():
            files.append((path.name,hashlib.sha256(path.read_bytes()).hexdigest()))
        elif path.is_dir():
            for f in sorted(path.rglob('*')):
                if f.is_symlink(): raise SliceBFixtureError('unsafe worktree symlink')
                if f.is_file(): files.append((str(f.relative_to(repo)),hashlib.sha256(f.read_bytes()).hexdigest()))
    return index,tuple(files)


def _verify_git_config(repo:Path):
    keys = _git(repo,'config','--local','--no-includes','--name-only','--list','-z')
    allowed = {'core.repositoryformatversion','core.filemode','core.bare','core.logallrefupdates','core.ignorecase','user.name','user.email'}
    for key in keys.split(b'\0'):
        if key and key.decode('ascii') not in allowed:
            raise SliceBFixtureError('unsafe Git config')
    if (repo/'.gitattributes').exists() or (repo/'.gitmodules').exists():
        raise SliceBFixtureError('untrusted repository attributes')


def run_offline_fixture(repo:Path, baseline_head:str, baseline_ref:str) -> str:
    repo = repo.resolve(strict=True)
    if not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', baseline_head) or not re.fullmatch(r'refs/heads/[A-Za-z0-9][A-Za-z0-9/_-]{0,180}', baseline_ref):
        raise SliceBFixtureError('invalid expected baseline')
    _verify_git_config(repo)
    if _git(repo,'rev-parse','--verify','HEAD').strip().decode() != baseline_head or _git(repo,'symbolic-ref','HEAD').strip().decode() != baseline_ref:
        raise SliceBFixtureError('Guest baseline diverged')
    fixture = repo/FIXTURE_NAME
    if fixture.exists() or fixture.is_symlink():
        raise SliceBFixtureError('fixture exists; never overwrite')
    before = _snapshot(repo)
    try:
        with fixture.open('xb') as f:
            f.write(FIXTURE_BYTES)
            f.flush()
            os.fsync(f.fileno())
        if fixture.read_bytes() != FIXTURE_BYTES:
            raise SliceBFixtureError('offline fixture assertion failed')
        _git(repo,'add','-N','--',FIXTURE_NAME)
        _git(repo,'commit','--only','--no-verify','--no-gpg-sign','-m',FIXTURE_MESSAGE,'--',FIXTURE_NAME)
    except (OSError,SliceBFixtureError) as e:
        # As-is preservation: no reset, clean, checkout, re-stage or retry.
        raise SliceBFixtureError('fixture failed; Guest left as-is') from e
    if _snapshot(repo) != before:
        raise SliceBFixtureError('unrelated Index/Working Tree changed')
    commit = _git(repo,'rev-parse','--verify','HEAD').strip().decode('ascii')
    parents = _git(repo,'rev-list','--parents','-n','1','HEAD').strip().decode().split()
    if parents != [commit,baseline_head]:
        raise SliceBFixtureError('fixture parent mismatch')
    changed=_git(repo,'diff-tree','--no-commit-id','--name-only','-r','HEAD').strip().decode()
    if changed != FIXTURE_NAME:
        raise SliceBFixtureError('fixture-only tree diff mismatch')
    return commit

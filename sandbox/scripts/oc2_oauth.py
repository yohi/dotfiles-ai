from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from enum import Enum
from oc2_oauth_bootstrap import BootstrapConfigError, ACCESS, REFRESH
from oc2_oauth_bootstrap import capture_import_stderr, cleanup as cleanup_bootstrap_config
from oc2_oauth_bootstrap import create as create_bootstrap_config
from oc2_oauth_bootstrap import record_from_auth, validate_db

class Stage(Enum):
    INITIAL_DB_CHECK = 'INITIAL_DB_CHECK'
    SENTINEL_VALIDATE = 'SENTINEL_VALIDATE'
    DB_PATH_VERIFY = 'DB_PATH_VERIFY'
    EXPORT_BEFORE = 'EXPORT_BEFORE'
    STATE_CLASSIFY = 'STATE_CLASSIFY'
    BOOTSTRAP_CONFIG = 'BOOTSTRAP_CONFIG'
    IMPORT = 'IMPORT'
    BOOTSTRAP_CLEANUP = 'BOOTSTRAP_CLEANUP'
    EXPORT_AFTER = 'EXPORT_AFTER'
    POST_FAILURE_EXPORT = 'POST_FAILURE_EXPORT'
    READBACK_VERIFY = 'READBACK_VERIFY'


class Progress:
    def __init__(self):
        self.stage = None
        self.completed = True

    def start(self, stage):
        if self.stage is not None and not self.completed:
            self.emit('PASS')
        self.stage = stage
        self.completed = False
        self.emit('START')

    def emit(self, outcome, stage=None):
        current = self.stage if stage is None else stage
        print(f'OC2_OAUTH {current.value} {outcome}', file=sys.stderr, flush=True)
        if current is self.stage and outcome in ('PASS', 'FAIL'):
            self.completed = True


def _credential_partitions(entries):
    managed = [entry for entry in entries if entry.get('id') == 'sbx-openai']
    openai = [entry for entry in entries if entry.get('integrationID') == 'openai']
    others = [entry for entry in entries if entry.get('integrationID') != 'openai'
              and entry.get('id') != 'sbx-openai']
    return managed, openai, others


def _report_credential_state(prefix, entries):
    managed, openai, others = _credential_partitions(entries)
    print(f'{prefix}_CREDENTIAL_COUNT={len(entries)}', file=sys.stderr, flush=True)
    print(f'{prefix}_OPENAI_COUNT={len(openai)}', file=sys.stderr, flush=True)
    print(f'{prefix}_MANAGED_COUNT={len(managed)}', file=sys.stderr, flush=True)
    print(f'{prefix}_OTHER_PROVIDER_COUNT={len(others)}', file=sys.stderr, flush=True)
    if len(managed) == 1:
        entry = managed[0]
        value = entry.get('value') if isinstance(entry.get('value'), dict) else {}
        print(f'{prefix}_ACTIVE={str(entry.get("active") is True).lower()}',
              file=sys.stderr, flush=True)
        print(f'{prefix}_METHOD_MATCH={str(value.get("methodID") == "chatgpt-browser").lower()}',
              file=sys.stderr, flush=True)
        print(f'{prefix}_SENTINELS_MATCH={str(value.get("access") == ACCESS and value.get("refresh") == REFRESH).lower()}',
              file=sys.stderr, flush=True)
    return managed, openai, others


def _canonical(entries):
    return sorted(json.dumps(item, sort_keys=True, separators=(',', ':')) for item in entries)


def synchronize(cli, source_path, db_path):
    progress = Progress()
    try:
        _synchronize(cli, source_path, db_path, progress)
    except Exception:
        if progress.stage is not None and not progress.completed:
            progress.emit('FAIL')
        raise
    else:
        progress.emit('PASS')


def _synchronize(cli, source_path, db_path, progress):
    progress.start(Stage.INITIAL_DB_CHECK)
    validate_db(db_path)
    original = (db_path.stat().st_dev, db_path.stat().st_ino) if db_path.exists() else None
    progress.start(Stage.SENTINEL_VALIDATE)
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError('OAuth source unavailable')
    expected = record_from_auth(json.loads(source_path.read_text(encoding='utf-8')))

    def command(args, payload=None, config_dir=None):
        def report_import_failure(
            code: str, exit_code: int | str, stderr: bytes | str,
        ) -> None:
            if isinstance(stderr, str):
                stderr = stderr.encode('utf-8', errors='replace')
            captured = capture_import_stderr(db_path, stderr)
            print(f'OC2_OAUTH {code}', file=sys.stderr, flush=True)
            print(f'IMPORT_EXIT_CODE={exit_code}', file=sys.stderr, flush=True)
            print(f'IMPORT_STDERR_CAPTURED={str(captured is not None).lower()}',
                  file=sys.stderr, flush=True)
            print(f'IMPORT_STDERR_BYTES={len(stderr)}', file=sys.stderr, flush=True)
            if captured is not None:
                print(f'IMPORT_STDERR_PATH={captured}', file=sys.stderr, flush=True)

        try:
            command_environment = None
            if config_dir is not None:
                command_environment = os.environ.copy()
                command_environment['OPENCODE_CONFIG_DIR'] = str(config_dir)
            result = subprocess.run([cli, *args],
                                    input=payload.encode('utf-8') if payload is not None else None,
                                    capture_output=True, timeout=30, check=False,
                                    env=command_environment)
        except subprocess.TimeoutExpired as error:
            if args == ['auth', 'import', '--standalone']:
                report_import_failure('IMPORT_TIMEOUT', 'TIMEOUT', error.stderr or b'')
            raise
        except Exception:
            if args == ['auth', 'import', '--standalone']:
                report_import_failure('IMPORT_UNKNOWN', 'UNKNOWN', b'')
            raise
        if result.returncode:
            if args == ['auth', 'import', '--standalone']:
                input_error = b'Pipe auth export output into stdin or pass a file to import'
                code = 'IMPORT_INPUT_INVALID' if result.stderr.strip() == input_error else 'IMPORT_NONZERO'
                report_import_failure(code, result.returncode, result.stderr)
            raise ValueError('OAuth command failed')
        return result.stdout.decode('utf-8')

    progress.start(Stage.DB_PATH_VERIFY)
    if command(['debug', 'paths', 'db']).strip() != str(db_path):
        raise ValueError('database identity mismatch')
    progress.start(Stage.EXPORT_BEFORE)
    before = json.loads(command(['auth', 'export', '--standalone']))
    validate_db(db_path)
    if not db_path.is_file():
        raise ValueError('database unavailable')
    if original is not None and (not db_path.exists() or
            (db_path.stat().st_dev, db_path.stat().st_ino) != original):
        raise ValueError('database identity changed')
    if not isinstance(before, list) or any(not isinstance(item, dict) for item in before):
        raise ValueError('invalid credential export')
    managed_before, openai_before, others_before = _report_credential_state('PRE_IMPORT', before)
    progress.start(Stage.STATE_CLASSIFY)
    managed = [item for item in before if item.get('integrationID') == 'openai'
               or item.get('id') == 'sbx-openai']
    if managed_before or openai_before:
        if managed != [expected]:
            raise ValueError('conflicting OpenAI credentials')
        return
    inode = (db_path.stat().st_dev, db_path.stat().st_ino) if db_path.exists() else None
    progress.start(Stage.BOOTSTRAP_CONFIG)
    runtime_dir = db_path.parents[4]
    base_config = pathlib.Path(os.environ['XDG_CONFIG_HOME']) / 'opencode/opencode.jsonc'
    bootstrap_dir = create_bootstrap_config(base_config, runtime_dir)
    progress.start(Stage.IMPORT)
    import_succeeded = False
    import_error = None
    try:
        command(['auth', 'import', '--standalone'], json.dumps([expected]), bootstrap_dir)
        import_succeeded = True
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        import_error = error
    finally:
        if import_succeeded:
            progress.start(Stage.BOOTSTRAP_CLEANUP)
            cleanup_bootstrap_config(bootstrap_dir, runtime_dir)
            progress.emit('PASS')
        else:
            progress.emit('START', Stage.BOOTSTRAP_CLEANUP)
            try:
                cleanup_bootstrap_config(bootstrap_dir, runtime_dir)
            except BootstrapConfigError:
                progress.emit('FAIL', Stage.BOOTSTRAP_CLEANUP)
                raise
            progress.emit('PASS', Stage.BOOTSTRAP_CLEANUP)
    if import_error is not None:
        progress.emit('START', Stage.POST_FAILURE_EXPORT)
        try:
            after_failure = json.loads(command(['auth', 'export', '--standalone']))
            if not isinstance(after_failure, list) or any(
                    not isinstance(item, dict) for item in after_failure):
                raise ValueError('invalid post-failure export')
        except (OSError, ValueError, TypeError, KeyError, IndexError, subprocess.SubprocessError):
            progress.emit('FAIL', Stage.POST_FAILURE_EXPORT)
            print('POST_FAILURE_STATE=UNAVAILABLE', file=sys.stderr, flush=True)
        else:
            try:
                validate_db(db_path)
                db_identity_matches = inode is None or (
                    db_path.exists() and (db_path.stat().st_dev, db_path.stat().st_ino) == inode
                )
            except (OSError, ValueError):
                db_identity_matches = False
            print(f'POST_FAILURE_DB_IDENTITY_MATCH={str(db_identity_matches).lower()}',
                  file=sys.stderr, flush=True)
            progress.emit('PASS', Stage.POST_FAILURE_EXPORT)
            _, _, others_after = _report_credential_state('AFTER_FAILURE', after_failure)
            print(
                'OTHER_CREDENTIALS_UNCHANGED=' + str(
                    _canonical(others_after) == _canonical(others_before)
                ).lower(),
                file=sys.stderr, flush=True,
            )
        raise import_error
    progress.start(Stage.EXPORT_AFTER)
    after = json.loads(command(['auth', 'export', '--standalone']))
    progress.start(Stage.READBACK_VERIFY)
    validate_db(db_path)
    if inode is not None and (not db_path.exists() or
            (db_path.stat().st_dev, db_path.stat().st_ino) != inode):
        raise ValueError('database identity changed')
    if not isinstance(after, list) or any(not isinstance(item, dict) for item in after):
        raise ValueError('invalid credential readback')
    imported = [item for item in after if item.get('integrationID') == 'openai'
                or item.get('id') == 'sbx-openai']
    others = [item for item in after if item.get('integrationID') != 'openai'
              and item.get('id') != 'sbx-openai']
    if imported != [expected] or _canonical(others) != _canonical(others_before):
        raise ValueError('credential readback mismatch')
    _report_credential_state('AFTER_IMPORT', after)
    print('OTHER_CREDENTIALS_UNCHANGED=true', file=sys.stderr, flush=True)


if __name__ == '__main__':
    try:
        synchronize(sys.argv[1], pathlib.Path('/home/agent/.local/share/opencode/auth.json'),
                    pathlib.Path(os.environ['OPENCODE_DB']))
    except (OSError, ValueError, TypeError, KeyError, IndexError, subprocess.SubprocessError):
        print('OC2_OAUTH_STOP', file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('OC2_OAUTH_STOP UNKNOWN', file=sys.stderr)
        sys.exit(1)

from __future__ import annotations

import pathlib
import re


class OAuthBundleError(ValueError):
    pass


def inline_python_module(module_name: str, source: str) -> str:
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', module_name) is None:
        raise OAuthBundleError('invalid embedded module name')
    return (
        'import sys as _oc2_sys\n'
        'import types as _oc2_types\n'
        f'_oc2_module = _oc2_types.ModuleType({module_name!r})\n'
        f'_oc2_module.__file__ = {module_name + ".py"!r}\n'
        f'_oc2_module_source = {source!r}\n'
        f'_oc2_sys.modules[{module_name!r}] = _oc2_module\n'
        'exec(compile(_oc2_module_source, _oc2_module.__file__, "exec"), '
        '_oc2_module.__dict__)\n'
        'del _oc2_module, _oc2_module_source, _oc2_sys, _oc2_types\n'
    )


def oauth_helper_source(scripts: pathlib.Path) -> str:
    future_import = 'from __future__ import annotations\n'
    bootstrap_path = scripts / 'oc2_oauth_bootstrap.py'
    helper_path = scripts / 'oc2_oauth.py'
    for path in (bootstrap_path, helper_path):
        if path.is_symlink() or not path.is_file():
            raise OAuthBundleError('OAuth helper source is missing or unsafe')
    helper_source = helper_path.read_text(encoding='utf-8')
    if not helper_source.startswith(future_import):
        raise OAuthBundleError('OAuth helper source format is invalid')
    bootstrap_source = bootstrap_path.read_text(encoding='utf-8')
    return (
        future_import
        + inline_python_module('oc2_oauth_bootstrap', bootstrap_source)
        + helper_source[len(future_import):]
    )

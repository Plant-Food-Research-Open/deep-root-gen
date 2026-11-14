"""Self-contained public checkpoint references for exact subprocess regressions.

Only changed package modules are restored. Both sides use the same inherited
installed runtime. No network, external source tree, git checkout or index is
needed; a checked-in text patch is applied to a disposable package copy.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys

FIXTURES = Path(__file__).parent / 'fixtures/public_checkpoint_references'
FORMAT = 'deeprootgen-public-checkpoint-reference-v1'


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _module_path(root, name):
    path = PurePosixPath(name)
    if (path.is_absolute() or '..' in path.parts or '\\' in name
            or not path.parts or path.parts[0] != 'deeprootgen' or path.suffix != '.py'):
        raise AssertionError(f'Non-public-package path in reference fixture: {name!r}')
    return root.joinpath(*path.parts)


def _verify_modules(root, hashes):
    for name, expected in hashes.items():
        path = _module_path(root, name)
        if expected is None:
            if path.exists():
                raise AssertionError(f'Expected absent reference module: {name}')
        elif not path.is_file() or _sha256(path) != expected:
            raise AssertionError(f'Public reference module hash mismatch: {name}')


def materialize_reference(current_root, tmp_path, name):
    """Restore hash-bound public reference modules without depending on git refs."""
    current_root = Path(current_root).resolve()
    manifest = json.loads((FIXTURES / 'manifest.json').read_text())
    if manifest.get('format') != FORMAT or name not in manifest.get('references', {}):
        raise AssertionError(f'Unknown public checkpoint reference: {name!r}')
    record = manifest['references'][name]
    patch_name = record['patch']
    if Path(patch_name).name != patch_name or not patch_name.endswith('.patch'):
        raise AssertionError('Reference patch must be a local fixture filename')
    patch = FIXTURES / patch_name
    if _sha256(patch) != record['patch_sha256']:
        raise AssertionError(f'Public reference patch hash mismatch: {name}')
    before, after = record['baseline_modules_sha256'], record['reference_modules_sha256']
    if set(before) != set(after):
        raise AssertionError('Reference before/after module manifests disagree')
    touched = set()
    for line in patch.read_text().splitlines():
        if line.startswith('diff --git '):
            fields = line.split()
            if len(fields) != 4 or fields[2] != 'a/' + fields[3][2:] or not fields[3].startswith('b/'):
                raise AssertionError('Unsupported path/rename in public reference patch')
            path = fields[3][2:]
            _module_path(current_root, path)
            touched.add(path)
    if touched != set(before):
        raise AssertionError('Reference patch touches unexpected modules')
    _verify_modules(current_root, before)
    target = Path(tmp_path) / ('public-reference-' + name)
    target.mkdir()
    shutil.copytree(current_root / 'deeprootgen', target / 'deeprootgen',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
    # Never discover a containing checkout or use its index/configuration.
    environment = {key: value for key, value in os.environ.items()
                   if key not in {'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'}}
    environment.update(GIT_CEILING_DIRECTORIES=str(target.parent.resolve()),
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_OPTIONAL_LOCKS='0')
    command = ['git', '-c', 'core.autocrlf=false', 'apply', '--whitespace=nowarn']
    for args in ([*command, '--check', str(patch.resolve())], [*command, str(patch.resolve())]):
        result = subprocess.run(args, cwd=target, env=environment, text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError(f'Cannot reconstruct public reference {name}: {result.stderr}')
    _verify_modules(target, after)
    return target


def subprocess_environment(source_root):
    """Pin selected package first, retaining arbitrary installed parent paths.

    Do not infer dependency locations or require a virtualenv/overlay basename.
    Preserve symlink spellings: they are valid installed-runtime paths too.
    """
    paths = [str(Path(source_root).resolve())]
    for path in sys.path:
        absolute = os.path.abspath(path or os.getcwd())
        if absolute not in paths:
            paths.append(absolute)
    return {**os.environ, 'PYTHONPATH': os.pathsep.join(paths), 'PYTHONDONTWRITEBYTECODE': '1'}

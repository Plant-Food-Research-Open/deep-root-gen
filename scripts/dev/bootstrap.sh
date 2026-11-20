#!/usr/bin/env bash
# Qualify the existing lock in a private environment; never replace system Python.
set -euo pipefail
repo=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$repo"
drg_python=${1:?Usage: bash scripts/dev/bootstrap.sh /absolute/path/to/python3.10}
"$drg_python" -c 'import sys; assert sys.version_info[:2] == (3, 10), "Python 3.10 required"'
drg_tools="$repo/.runtime/tools/poetry-1.8.3"
drg_environment=${DRG_RUNTIME_DIR:-$repo/.runtime/envs/py310-qualification}
if [[ -e "$drg_tools" && ! -x "$drg_tools/bin/python" ]]; then
  echo "Refusing to overwrite existing non-environment: $drg_tools" >&2; exit 1
fi
if [[ ! -e "$drg_tools" ]]; then
  "$drg_python" -m venv "$drg_tools"
  PIP_CONFIG_FILE=/dev/null PIP_INDEX_URL=https://pypi.org/simple \
    "$drg_tools/bin/python" -m pip install poetry==1.8.3
fi
"$drg_tools/bin/python" -c 'import importlib.metadata as m; assert m.version("poetry") == "1.8.3"'
if [[ -e "$drg_environment" && ! -x "$drg_environment/bin/python" ]]; then
  echo "Refusing to overwrite existing non-environment: $drg_environment" >&2; exit 1
fi
if [[ ! -e "$drg_environment" ]]; then
  "$drg_python" -m venv "$drg_environment"
fi
source "$drg_environment/bin/activate"
export POETRY_CACHE_DIR="$repo/.runtime/cache/poetry"
export POETRY_INSTALLER_MAX_WORKERS=4
actual=$("$drg_tools/bin/poetry" env info --path)
[[ $(realpath "$actual") == $(realpath "$drg_environment") ]] || {
  echo "Poetry selected an unexpected environment; stopping" >&2; exit 1;
}
"$drg_tools/bin/poetry" check --lock
"$drg_tools/bin/poetry" install --with dev,torch --no-interaction
python -m pip check
python -c 'from deeprootgen.model import RootSystemSimulation; print("Model import OK")'
printf 'Activate with: source %q/bin/activate\n' "$drg_environment"

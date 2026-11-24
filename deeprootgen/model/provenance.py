"""Run-start fingerprints and explicit replay status, without drawing randomness."""

import hashlib
import importlib.metadata
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source_fingerprint():
    digest = hashlib.sha256()
    for path in sorted((ROOT / "deeprootgen").rglob("*.py")):
        digest.update(str(path.relative_to(ROOT / "deeprootgen")).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


# Taken when the model package is first imported, before its simulation modules.
# A notebook must restart after editing source; rehashing disk alone cannot
# authenticate code that Python has already imported.
IMPORT_SOURCE_SHA256 = source_fingerprint()


def loaded_code_fingerprint():
    """Fingerprint loaded Python functions separately from source files.

    Preload only the offline model/schema/math modules, so the fingerprint is
    stable across notebook runs with different lazy-import histories. This is
    an audit fingerprint, not a claim to authenticate arbitrary mutable globals
    or third-party native code.
    """
    import importlib
    import inspect
    import json
    import types

    def constant(value):
        if isinstance(value, types.CodeType):
            return code(value)
        if isinstance(value, (tuple, frozenset)):
            return [type(value).__name__, [constant(v) for v in sorted(value, key=repr)] if isinstance(value, frozenset)
                    else [constant(v) for v in value]]
        if isinstance(value, bytes):
            return ["bytes", value.hex()]
        return [type(value).__name__, repr(value)]

    def code(value):
        # marshal's reference/intern flags can change after first execution.
        # Serialize numerical code content instead of its object-sharing layout.
        return dict(bytecode=value.co_code.hex(), constants=[constant(v) for v in value.co_consts],
                    names=value.co_names, varnames=value.co_varnames, freevars=value.co_freevars,
                    cellvars=value.co_cellvars, flags=value.co_flags, argcount=value.co_argcount,
                    posonly=value.co_posonlyargcount, kwonly=value.co_kwonlyargcount)

    digest = hashlib.sha256()
    packages = ("model", "data_model", "utils", "spatial")
    for package in packages:
        for path in sorted((ROOT / "deeprootgen" / package).glob("*.py")):
            module = importlib.import_module(f"deeprootgen.{package}.{path.stem}")
            for name, value in sorted(vars(module).items()):
                candidates = vars(value).items() if inspect.isclass(value) and value.__module__ == module.__name__ else [("", value)]
                for member, function in sorted(candidates):
                    if isinstance(function, (staticmethod, classmethod)):
                        function = function.__func__
                    if isinstance(function, property):
                        function = function.fget
                    function = inspect.unwrap(function)
                    if not isinstance(function, types.FunctionType):
                        continue
                    digest.update(f"{module.__name__}.{name}.{member}".encode() + b"\0")
                    digest.update(json.dumps(code(function.__code__), sort_keys=True).encode())
    return digest.hexdigest()


def run_start(simulation):
    import copy

    source = source_fingerprint()
    if source != IMPORT_SOURCE_SHA256:
        raise ValueError("Generator source changed since model import; restart Python before running")
    packages = {}
    for name in ("deeprootgen", "numpy", "pandas", "scipy", "pydantic", "torch", "torch-geometric"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    lock = ROOT / "poetry.lock"
    return dict(
        source_sha256=source,
        loaded_source_checkpoint_sha256=IMPORT_SOURCE_SHA256,
        loaded_python_code_sha256=loaded_code_fingerprint(),
        loaded_code_policy="source unchanged since model import; loaded Python functions fingerprinted; restart after source edits; mutable globals and native code unauthenticated",
        lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None,
        environment=dict(python=platform.python_version(), packages=packages),
        initial_native_rng_state=copy.deepcopy(simulation.rng.bit_generator.state),
        replayable=simulation.random_seed is not None,
        replay_policy="explicit_seed" if simulation.random_seed is not None else "unseeded_non_replayable",
    )

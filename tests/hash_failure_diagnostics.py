"""Failure-only evidence for named, invented public regression fixtures.

Do not call for observations or arbitrary user payloads. No environment dump,
credentials, hostname, user paths or data files are collected. CI opts in with a
fresh dedicated directory; normal runs produce no files. Assertions stay with
callers, so evidence collection cannot turn a regression into a pass.
"""

import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import tempfile
import warnings


def canonical_bytes(payload):
    return json.dumps(
        payload, sort_keys=True, allow_nan=False, separators=(",", ":")
    ).encode()


def record_failure(case, payloads, expected):
    """Write exact canonical bytes and bounded runtime metadata after failure."""
    root = os.environ.get("DRG_SYNTHETIC_FAILURE_DIR")
    if not root:
        return
    try:
        if case not in {"physical-cap", "inactive-primary-design"}:
            raise ValueError("Only public synthetic regression cases are allowed")
        if set(payloads) - {"actual", "omitted", "explicit_none", "reference"}:
            raise ValueError("Unexpected synthetic payload role")
        directory = Path(root)
        directory.mkdir(parents=True, exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix=case + "-", dir=directory))
        payload_info = {}
        for name, payload in payloads.items():
            data = canonical_bytes(payload)
            (target / (name + ".json")).write_bytes(data)
            payload_info[name] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        packages = {}
        for name in (
            "numpy",
            "pandas",
            "scipy",
            "pydantic",
            "pydantic-core",
            "networkx",
            "pytest",
        ):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                packages[name] = "NOT_INSTALLED"
        cpu = {}
        try:
            import numpy as np

            cpu = dict(np.core._multiarray_umath.__cpu_features__)
        except (ImportError, AttributeError):
            pass
        metadata = {
            "case": case,
            "expected_sha256": expected,
            "payloads": payload_info,
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "machine": platform.machine(),
            "libc": platform.libc_ver(),
            "packages": packages,
            "numpy_cpu_features": cpu,
            "scope": "INVENTED_PUBLIC_FIXTURE_ONLY",
        }
        (target / "metadata.json").write_bytes(canonical_bytes(metadata))
    except Exception as exc:
        # Preserve the original assertion even if diagnostics cannot be written.
        warnings.warn("Synthetic failure evidence unavailable: " + type(exc).__name__)

"""Execute authenticated historical synthetic payloads on this same runtime."""

import json
from pathlib import Path
import subprocess
import sys

from tests.public_checkpoint_reference import (
    materialize_reference,
    subprocess_environment,
)

ROOT = Path(__file__).resolve().parents[1]


def historical_payload(tmp_path, name, case):
    Path(tmp_path).mkdir(parents=True, exist_ok=True)
    reference = materialize_reference(ROOT, tmp_path, name)
    script = r"""
import importlib, json, pathlib, sys
import deeprootgen
assert pathlib.Path(deeprootgen.__file__).resolve().is_relative_to(pathlib.Path(sys.argv[1]))
case = json.loads(sys.argv[2])
modules = ['deeprootgen.research.physical_step_replay'] if case[0] == 'physical' else [
    'deeprootgen.research.so4_controlled', 'deeprootgen.model.root',
    'deeprootgen.data_model.simulation_data_models']
for name in modules:
    module = importlib.import_module(name)
    expected = pathlib.Path(sys.argv[1]).joinpath(*name.split('.')).with_suffix('.py')
    assert pathlib.Path(module.__file__).resolve() == expected.resolve(), name
if case[0] == 'physical':
    from tests.test_physical_step_replay import invented_initial, physical
    saved, settings = invented_initial(case[1])
    result = physical.replay_physical_steps(saved, settings, orders=tuple(case[2]), max_step_cm=case[3], direction_seed=case[4])
    payload = {k:v.to_dict('records') if hasattr(v,'to_dict') else v for k,v in result.items()}
else:
    from tests.test_root_origin_initialization import values
    from deeprootgen.data_model import RootSimulationModel
    from deeprootgen.research.so4_controlled import construct_skeleton
    spec = values(min_primary_length=5., max_primary_length=6., segments_per_root=3, root_vary=2., interbranch_distance=.5)
    payload = construct_skeleton(RootSimulationModel(**spec),42).payload
print(json.dumps(payload,sort_keys=True,allow_nan=False,separators=(',',':')))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(reference), json.dumps(case)],
        cwd=reference,
        env=subprocess_environment(reference),
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)

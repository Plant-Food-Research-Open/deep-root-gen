"""Exercise the candidate runtime using two mounted, invented input files."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import dash

from app import server
from deeprootgen.form.core_comparison import compare_core_csv
from deeprootgen.research.architecture_search import run_architecture_search


def main():
    fixtures = Path(__file__).resolve().parent
    configuration = fixtures / "synthetic_minimal.json"
    client = server.test_client()
    pages = {page["path"] for page in dash.page_registry.values()}
    for route in ("/architecture-search", "/core-comparison"):
        assert route in pages
        assert client.get(route).status_code == 200
    assert client.get("/_dash-layout").is_json

    contents = (fixtures / "core_comparison_synthetic.csv").read_text()
    candidates, train_tubes, held_tubes = compare_core_csv(contents)
    assert (train_tubes, held_tubes) == (1, 1)
    assert candidates[0]["candidate"] == "exact"
    assert candidates[0]["loss"] == 0
    assert candidates[1]["miss"] == 1

    with TemporaryDirectory() as temporary:
        outdir = Path(temporary)
        simulation = outdir / "simulation"
        subprocess.run(
            [sys.executable, "-m", "deeprootgen", "simulate",
             "--config", str(configuration), "--outdir", str(simulation)],
            check=True,
        )
        for name in ("nodes.csv", "edges.csv", "run_manifest.json"):
            assert (simulation / name).stat().st_size > 0

        base = json.loads(configuration.read_text())
        for method in ("tpe", "latin_hypercube"):
            directory = outdir / method
            result = run_architecture_search(
                {
                    "base": base,
                    "ranges": [{"control": "primary_root_count", "lower": 2, "upper": 4}],
                    "targets": [{"statistic_name": "root_number", "statistic_value": 3}],
                    "metric": "mae",
                    "trials": 5,
                    "startup": 2,
                    "seeds": [0, 1],
                    "method": method,
                },
                directory,
            )
            assert result["completed_trials"] == 5
            assert result["best_loss"] == 0
            assert (directory / "best-configuration.json").stat().st_size > 0

    print("Candidate passed schema-4 simulation, Dash routes, core scoring, TPE and Latin hypercube.")


if __name__ == "__main__":
    main()

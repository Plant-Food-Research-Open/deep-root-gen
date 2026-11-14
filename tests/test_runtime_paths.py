"""Output-path regression for the browser run-history export."""

import importlib
from pathlib import Path


def test_run_history_uses_configured_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPROOTGEN_OUTPUT_DIR", str(tmp_path / "artifacts"))
    import deeprootgen.pipeline.experiment as experiment

    experiment = importlib.reload(experiment)
    output = Path(experiment.get_outdir())
    monkeypatch.chdir(tmp_path)
    file_name, download_name = experiment.save_simulation_runs([{"tag": "synthetic"}])
    assert Path(file_name).parent == output
    assert Path(file_name).name == download_name
    assert "synthetic" in Path(file_name).read_text()

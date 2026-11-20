from pathlib import Path

import pytest

from deeprootgen.form.core_comparison import compare_core_csv


CSV = (Path(__file__).resolve().parents[1] / "examples/research/core_comparison_synthetic.csv").read_text()


def test_core_comparison_uses_one_training_scale_and_ranks_the_exact_candidate_first():
    rows, training, held = compare_core_csv(CSV)
    assert (training, held) == (1, 1)
    assert rows[0]["candidate"] == "exact" and rows[0]["loss"] == 0
    assert rows[1]["candidate"] == "miss" and rows[1]["miss"] == 1
    assert rows[1]["nmae"] == pytest.approx(.5)
    assert rows[1]["joint_tv"] == rows[1]["depth_tv"] == 1


def test_core_comparison_disallows_a_tube_split_or_different_sampled_volumes():
    with pytest.raises(ValueError, match="Hold out entire tubes"):
        compare_core_csv(CSV.replace("train,,training,", "train,,held,"))
    with pytest.raises(ValueError, match="same held tubes"):
        compare_core_csv(CSV.replace("held,miss,held,-10,0,74.22", "held,miss,held,-10,0,70"))


def test_presence_threshold_preserves_the_spatial_score():
    original, _, _ = compare_core_csv(CSV)
    threshold, _, _ = compare_core_csv(CSV, threshold_rld=.1)
    assert [r["loss"] for r in original] == [r["loss"] for r in threshold]
    assert all(r["miss"] is None for r in threshold)

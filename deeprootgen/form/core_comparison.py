"""Prepare a comparable physical-core score table from supplied projected RLD."""
from io import StringIO

import numpy as np
import pandas as pd

from ..research.core_placement_cost import _tube_weights, score_core_placement
from ..research.core_presence import core_presence


KEY = ["core_id", "z_lower_cm", "z_upper_cm"]
GEOMETRY = ["core_volume_cm3", "rld_est"]
COLUMNS = {"split", "candidate", "predicted_rld", *KEY, *GEOMETRY}


def compare_core_csv(contents, *, threshold_rld=0.0):
    """Use one training field and an identical held observation field per candidate."""
    if len(contents.encode("utf-8")) > 1_500_000:
        raise ValueError("Supply a core-comparison CSV under 1.5 MB.")
    data = pd.read_csv(StringIO(contents), dtype={"core_id": str, "candidate": str})
    if not COLUMNS <= set(data) or set(data.split) != {"train", "held"}:
        raise ValueError("Supply the required columns and both train and held rows.")
    train = data.loc[data.split == "train"]
    held = data.loc[data.split == "held"]
    if set(train.core_id) & set(held.core_id):
        raise ValueError("Hold out entire tubes. A core_id occurs in both splits.")
    if held.candidate.isna().any() or held.candidate.nunique() > 60:
        raise ValueError("Provide a name for each held candidate, up to 60.")
    result = []
    expected = None
    for name, candidate in held.groupby("candidate", sort=False):
        candidate = candidate.sort_values(KEY, ignore_index=True)
        comparison = candidate[KEY + GEOMETRY]
        if expected is None:
            expected = comparison
        elif not comparison.equals(expected):
            raise ValueError("Every candidate must use the same held tubes, sections, volumes and observations.")
        predicted = candidate.predicted_rld
        score = score_core_placement(train, candidate, predicted)
        hit = core_presence(candidate, predicted, threshold_rld=threshold_rld)
        error = predicted - candidate.rld_est
        weight = _tube_weights(candidate, 1.0) / score["training_mean_rld"]
        result.append(dict(candidate=name, loss=score["loss"], nmae=score["normalized_mae"],
                           joint_tv=score["joint_tv"], depth_tv=score["depth_tv"],
                           under=float(weight @ np.maximum(-error, 0)),
                           over=float(weight @ np.maximum(error, 0)),
                           miss=hit["miss_rate_given_observed_hit"],
                           false_hit=hit["false_hit_rate_given_observed_empty"]))
    return sorted(result, key=lambda row: (row["loss"], row["candidate"])), train.core_id.nunique(), held.core_id.nunique()

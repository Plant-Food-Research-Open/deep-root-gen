import pandas as pd
import pytest

from deeprootgen.research.core_presence import core_presence


def test_presence_is_weighted_and_computed_before_realization_mean():
    section = pd.DataFrame(dict(core_id=["one", "one", "two"], z_lower_cm=[-10, -20, -10],
                                z_upper_cm=[0, -10, 0], core_volume_cm3=[1, 3, 1],
                                rld_est=[1, 0, 1]))
    result = core_presence(section, [[0, 1, 1], [1, 0, 1]])
    assert result["miss_rate_given_observed_hit"] == pytest.approx(.1)
    assert result["false_hit_rate_given_observed_empty"] == pytest.approx(.5)
    assert result["predicted_empty"] == pytest.approx(.25)
    assert core_presence(section, [[0, 1, 1], [1, 0, 1]], threshold_rld=1)["miss_rate_given_observed_hit"] is None

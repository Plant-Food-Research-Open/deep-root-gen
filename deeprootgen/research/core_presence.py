"""Hit and miss diagnostics for matched physical core sections."""
import numpy as np

from .core_placement_cost import _rld_vector, _tube_weights


def core_presence(comparison, predictions, *, threshold_rld=0.0):
    """Measure occupancy per realization and section, then average.

    Predictions end with one entry per comparison row. Earlier axes may index
    paired vines, reflections or other repeated observations with equal weight.
    RLD strictly greater than the same threshold on either side counts as a hit.
    Weights give each tube equal total weight. Within a tube they follow volume.
    Rates are fractions. A conditional rate is None if its class has no support.
    """
    observed = _rld_vector(comparison["rld_est"], len(comparison))
    weights = _tube_weights(comparison, 1.0)
    pred = np.asarray(predictions, dtype=float)
    if not pred.ndim or pred.shape[-1] != len(observed) or pred.size == 0:
        raise ValueError("Predictions must end in the corresponding core sections")
    if not (np.isfinite(pred).all() and (pred >= 0).all()):
        raise ValueError("Predictions must be finite nonnegative RLD")
    if not np.isfinite(threshold_rld) or threshold_rld < 0:
        raise ValueError("The presence threshold must be finite and nonnegative")

    field_hit = observed > threshold_rld
    hit_probability = (pred.reshape(-1, len(observed)) > threshold_rld).mean(axis=0)
    missed = float(weights @ ((1 - hit_probability) * field_hit))
    false = float(weights @ (hit_probability * ~field_hit))
    observed_hit = float(weights @ field_hit)
    observed_empty = float(weights @ ~field_hit)
    empty = float(weights @ (1 - hit_probability))
    return {
        "observed_hit": observed_hit,
        "predicted_empty": empty,
        "hit_rate_given_observed_hit": 1 - missed / observed_hit if observed_hit else None,
        "miss_rate_given_observed_hit": missed / observed_hit if observed_hit else None,
        "false_hit_rate_given_observed_empty": false / observed_empty if observed_empty else None,
        "missed_weight": missed,
        "false_hit_weight": false,
    }

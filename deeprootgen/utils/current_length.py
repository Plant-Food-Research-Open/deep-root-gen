"""Opt-in discrete CURRENT organ lengths, independent of parent subdivision."""

import hashlib
import json

import numpy as np

STREAM_VERSION = "drg-current-length-v1"


def validate_current_length_cdf(lengths_cm, cumulative_probabilities):
    """Validate an explicit normalized step CDF without interpolation or repair."""
    lengths = np.asarray(lengths_cm, dtype=float)
    cumulative = np.asarray(cumulative_probabilities, dtype=float)
    if (
        lengths.ndim != 1
        or cumulative.ndim != 1
        or not len(lengths)
        or len(lengths) != len(cumulative)
    ):
        raise ValueError("Current-length CDF requires matching nonempty 1-D arrays")
    if (
        not np.isfinite(lengths).all()
        or np.any(lengths <= 0)
        or np.any(np.diff(lengths) <= 0)
    ):
        raise ValueError(
            "Current-length support must be finite, positive and strictly increasing in cm"
        )
    if (
        not np.isfinite(cumulative).all()
        or np.any(cumulative <= 0)
        or np.any(cumulative > 1)
        or np.any(np.diff(cumulative) <= 0)
        or cumulative[-1] != 1.0
    ):
        raise ValueError(
            "Cumulative probabilities must be finite, positive, strictly increasing and end exactly at 1"
        )
    return lengths, cumulative


def _cdf_arrays(cdf):
    if isinstance(cdf, dict):
        return validate_current_length_cdf(
            cdf["lengths_cm"], cdf["cumulative_probabilities"]
        )
    return validate_current_length_cdf(cdf.lengths_cm, cdf.cumulative_probabilities)


def select_current_length(cdf, quantile):
    """Select the first CDF value strictly greater than u in [0,1)."""
    lengths, cumulative = _cdf_arrays(cdf)
    if not np.isfinite(quantile) or not 0 <= quantile < 1:
        raise ValueError("Current-length quantile must be finite and in [0,1)")
    index = int(np.searchsorted(cumulative, quantile, side="right"))
    return float(lengths[index]), index


def _stream(seed, organ_id, order, purpose):
    key = hashlib.sha256(
        f"{STREAM_VERSION}:{seed}:{order}:{organ_id}:{purpose}".encode()
    ).digest()
    return np.random.default_rng(
        np.random.SeedSequence(np.frombuffer(key, dtype="<u4"))
    )


def sample_current_lengths(cdf, segments_per_root, seed, organ_id, order):
    """Return keyed positive segment lengths and auditable sampling diagnostics.

    CDF identity is recorded but excluded from the random keys. This function
    never accesses the simulation's shared Generator.
    """
    for name, value, minimum in (
        ("seed", seed, 0),
        ("organ_id", organ_id, 1),
        ("segments_per_root", segments_per_root, 1),
    ):
        if (
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))
            or value < minimum
        ):
            raise ValueError(f"{name} must be an integer >= {minimum}")
    if (
        isinstance(order, (bool, np.bool_))
        or not isinstance(order, (int, np.integer))
        or order not in (2, 3, 4, 5)
    ):
        raise ValueError("Current-length CDF supports selected orders 2 through 5")
    support, cumulative = _cdf_arrays(cdf)
    quantile = float(_stream(seed, organ_id, order, "current_length").random())
    sampled, index = select_current_length(cdf, quantile)
    weights = np.sort(
        1.0
        - _stream(seed, organ_id, order, "segment_weights").random(segments_per_root)
    )[::-1]
    normalized = weights / weights.sum()
    lengths = sampled * normalized
    if not np.isfinite(lengths).all() or np.any(lengths <= 1e-12):
        raise ValueError(
            "Current-length draw cannot produce finite segments above the existing 1e-12 cm cutoff"
        )
    if not np.isclose(lengths.sum(), sampled, rtol=0, atol=1e-8):
        raise ValueError("Current organ length conservation exceeds 1e-8 cm")
    identity = json.dumps(
        dict(lengths_cm=support.tolist(), cumulative_probabilities=cumulative.tolist()),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    diagnostics = dict(
        stream_version=STREAM_VERSION,
        seed=int(seed),
        order=int(order),
        expected_organ_id=int(organ_id),
        cdf_sha256=hashlib.sha256(identity.encode()).hexdigest(),
        quantile=quantile,
        support_index=index,
        sampled_current_length_cm=sampled,
        requested_segment_count=int(segments_per_root),
        normalized_weights=normalized.tolist(),
        pre_subdivision_length_cm=float(lengths.sum()),
    )
    return lengths, diagnostics

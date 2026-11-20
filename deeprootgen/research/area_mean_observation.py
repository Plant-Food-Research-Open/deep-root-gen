"""Explicit virtual simulation windows and sampled-volume area-mean proxies.

No measured geometry, model defaults, observations or objectives are modified.
All support geometry is cm. Quantities passed to pooling must be caller-declared
additive length, root volume or mass, never an already normalized density.

Observed pooling always uses actual sampled known volumes. Virtual predictions
are first divided by their own physical window volumes, then averaged with the
SAME actual observation-volume weights. This is an area-mean/smoothing assumption,
not the length or mass in a union of virtual cylinders. Overlapping virtual
windows are correlated views, not extra observations. One call describes one
physical coordinate frame; independently located replicate frames need separate
calls. Groups must not reuse physical observed cylinders.
"""

from collections.abc import Mapping
import math
from numbers import Real

import numpy as np
import pandas as pd

from .core_observation import _CORE_FIELDS, _validate_cores

VERSION = "explicit-volume-area-mean-proxy-v1"
MATCHED = "matched_support"
VIRTUAL = "observed_volume_weighted_virtual_density"
GEOMETRY = ("x_cm", "y_cm", "z_lower_cm", "z_upper_cm", "radius_cm")


def _real(value, name, *, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite nonbool number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be finite") from error
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(
            f"{name} must be finite" + (" and positive" if positive else "")
        )
    return result


def _overlap_pairs(records):
    """Positive cylinder-volume overlap; shared faces/tangencies are disjoint."""
    pairs = []
    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            dz = min(left["z_upper_cm"], right["z_upper_cm"]) - max(
                left["z_lower_cm"], right["z_lower_cm"]
            )
            if dz <= 0:
                continue
            distance = np.hypot(
                np.longdouble(left["x_cm"]) - right["x_cm"],
                np.longdouble(left["y_cm"]) - right["y_cm"],
            )
            if distance < np.longdouble(left["radius_cm"]) + right["radius_cm"]:
                pairs.append((left["core_id"], right["core_id"]))
    return pairs


def make_virtual_cores(cores, radius_cm, depth_band_cm=None):
    """Return ``(virtual_cores, mapping, diagnostics)`` for simulation ONLY.

    IDs, x/y and strict sampled flags are retained. ``depth_band_cm=None`` keeps
    each original z interval. Otherwise supply a shared explicit ``(lower,upper)``
    pair in the same z frame; scalar heights/implicit centering are rejected.
    The virtual known volume is exactly pi*r²*(upper-lower). Measured additive
    quantities are NOT copied into the virtual support table. Input tables and
    their recorded geometry/volumes remain unchanged, including missing samples.
    """
    radius = _real(radius_cm, "radius_cm", positive=True)
    band = None
    if depth_band_cm is not None:
        if not isinstance(depth_band_cm, (tuple, list)) or len(depth_band_cm) != 2:
            raise ValueError("depth_band_cm must be explicit (lower_z_cm, upper_z_cm)")
        band = tuple(_real(value, "depth_band_cm") for value in depth_band_cm)
        if band[0] >= band[1]:
            raise ValueError("depth_band_cm requires lower < upper")
    originals = _validate_cores(cores)
    virtual, mappings = [], []
    for old in originals:
        new = {key: old[key] for key in _CORE_FIELDS}
        new["radius_cm"] = radius
        if band is not None:
            new["z_lower_cm"], new["z_upper_cm"] = band
        with np.errstate(over="ignore", invalid="ignore"):
            volume = float(
                np.pi * np.square(radius) * (new["z_upper_cm"] - new["z_lower_cm"])
            )
        if not np.isfinite(volume) or volume <= 0:
            raise ValueError(
                "Virtual support volume must be representable, finite and positive"
            )
        new["known_volume_cm3"] = volume
        virtual.append(new)
        mapping = dict(
            core_id=old["core_id"],
            sampled=bool(old["sampled"]),
            original_known_volume_cm3=old["known_volume_cm3"],
            original_physical_volume_cm3=old["core_volume_cm3"],
            virtual_known_volume_cm3=volume,
            virtual_physical_volume_cm3=volume,
            support_kind="virtual_simulation_only",
        )
        mapping.update({f"original_{key}": old[key] for key in GEOMETRY})
        mapping.update({f"virtual_{key}": new[key] for key in GEOMETRY})
        mappings.append(mapping)
    table = pd.DataFrame(virtual, columns=[*_CORE_FIELDS, "known_volume_cm3"])
    table.attrs["support_kind"] = "virtual_simulation_only"
    table.attrs["version"] = VERSION
    mapping_columns = [
        "core_id",
        "sampled",
        "original_known_volume_cm3",
        "original_physical_volume_cm3",
        "virtual_known_volume_cm3",
        "virtual_physical_volume_cm3",
        "support_kind",
        *(f"original_{key}" for key in GEOMETRY),
        *(f"virtual_{key}" for key in GEOMETRY),
    ]
    mapping = pd.DataFrame(mappings, columns=mapping_columns)
    diagnostics = dict(
        version=VERSION,
        support_kind="virtual_simulation_only",
        measured_geometry_modified=False,
        observed_values_transferred=False,
        core_count=len(table),
        sampled_core_count=sum(bool(row["sampled"]) for row in originals),
        depth_band_policy=(
            "preserve_original_intervals"
            if band is None
            else "explicit_shared_z_interval"
        ),
        virtual_overlap_pairs=_overlap_pairs(virtual),
        overlap_interpretation="correlated_simulation_windows_not_new_observations_or_union_volume",
    )
    return table, mapping, diagnostics


def _quantity_table(table, quantities, label):
    if not isinstance(table, pd.DataFrame) or not set(quantities).issubset(table):
        raise ValueError(
            f"{label} must be a DataFrame with all declared additive quantities"
        )
    records = _validate_cores(table)
    indexed = table.set_index("core_id")
    result = {}
    for record in records:
        if record["sampled"]:
            volume = _real(
                record["known_volume_cm3"], f"{label} known_volume_cm3", positive=True
            )
            values = {}
            for quantity in quantities:
                value = _real(
                    indexed.loc[record["core_id"], quantity], f"{label} {quantity}"
                )
                if value < 0:
                    raise ValueError("Additive root quantities must be nonnegative")
                values[quantity] = value
        else:
            # Unobserved entries never contribute even if a caller stored zero.
            volume, values = None, {quantity: None for quantity in quantities}
        result[record["core_id"]] = dict(
            record,
            sampled=bool(record["sampled"]),
            sampled_volume_cm3=volume,
            quantities=values,
        )
    return result


def _groups(groups, identifiers):
    if not isinstance(groups, Mapping) or not groups:
        raise ValueError("groups must be a nonempty mapping group_id -> core_id list")
    used, parsed = set(), []
    for label, ids in groups.items():
        if not isinstance(label, str) or not label.strip():
            raise ValueError("group_id labels must be nonempty strings")
        if not isinstance(ids, (list, tuple)) or not ids:
            raise ValueError("Each group needs a nonempty explicit core_id list")
        if len(set(ids)) != len(ids) or any(core not in identifiers for core in ids):
            raise ValueError("Group core IDs must be unique and present in both tables")
        if used.intersection(ids):
            raise ValueError("Groups must be nonoverlapping; core IDs cannot be reused")
        used.update(ids)
        parsed.append((label, list(ids)))
    return parsed, used


def _finite_sum(values, name):
    try:
        total = math.fsum(values)
    except OverflowError as error:
        raise ValueError(f"Nonfinite {name} arithmetic") from error
    if not math.isfinite(total):
        raise ValueError(f"Nonfinite {name} arithmetic")
    return total


def _finite_ratio(numerator, denominator, name):
    try:
        value = numerator / denominator
    except OverflowError as error:
        raise ValueError(f"Nonfinite {name} arithmetic") from error
    if not math.isfinite(value):
        raise ValueError(f"Nonfinite {name} arithmetic")
    return value


def pool_area_mean_observations(
    observed, predicted, groups, *, quantity_columns, prediction_mode=MATCHED
):
    """Return ``(long_pooled_table, diagnostics)`` using exact same sample masks.

    Both tables need core_observation support columns, explicit known volumes for
    sampled rows, and the same caller-declared additive quantity columns. Row
    order may differ; core ID sets and sampled flags must match EXACTLY. Known
    volumes must agree with each table's cylinder geometry. Groups may select a
    subset, but cannot reuse IDs or overlapping sampled physical observed cores
    within this shared coordinate frame. Unsampled rows contribute neither a
    zero nor volume. Empty-sample groups have missing quantities/densities.

    ``matched_support`` requires identical per-ID physical geometry/known volume;
    its predicted total is physically additive. The explicit virtual mode first
    normalizes each prediction by its OWN physical support volume, then weights
    those densities by actual observed sampled volumes. Its reported equivalent
    on observed volume is only a proxy; ``predicted_additive_total`` is missing.
    The summed virtual window volumes are audit values, NEVER union volume or
    observed support. Overlaps are allowed/reported only for virtual predictions.
    """
    if prediction_mode not in (MATCHED, VIRTUAL):
        raise ValueError(
            "Unsupported prediction_mode; virtual density pooling requires explicit opt-in"
        )
    if (
        not isinstance(quantity_columns, (list, tuple))
        or not quantity_columns
        or any(not isinstance(value, str) or not value for value in quantity_columns)
        or len(set(quantity_columns)) != len(quantity_columns)
    ):
        raise ValueError(
            "quantity_columns must be unique explicit additive column names"
        )
    if getattr(observed, "attrs", {}).get("support_kind") == "virtual_simulation_only":
        raise ValueError(
            "Virtual simulation volumes cannot be supplied as observed support"
        )
    obs = _quantity_table(observed, quantity_columns, "observed")
    pred = _quantity_table(predicted, quantity_columns, "predicted")
    if set(obs) != set(pred):
        raise ValueError("Observed/predicted core IDs must match exactly")
    for cid in obs:
        if obs[cid]["sampled"] != pred[cid]["sampled"]:
            raise ValueError("Observed/predicted sampled masks must match exactly")
        if prediction_mode == MATCHED:
            if any(obs[cid][key] != pred[cid][key] for key in GEOMETRY):
                raise ValueError(
                    "matched_support requires identical geometry; use explicit virtual-density mode"
                )
            if obs[cid]["sampled_volume_cm3"] != pred[cid]["sampled_volume_cm3"]:
                raise ValueError(
                    "matched_support requires identical known sampled volume weights"
                )
    parsed, selected = _groups(groups, set(obs))
    selected_sampled = [
        obs[cid] for _, ids in parsed for cid in ids if obs[cid]["sampled"]
    ]
    observed_overlaps = _overlap_pairs(selected_sampled)
    if observed_overlaps:
        raise ValueError(
            "Overlapping observed cylinders cannot be additively pooled; explicit union integration is unsupported"
        )
    prediction_overlaps = _overlap_pairs(
        [pred[row["core_id"]] for row in selected_sampled]
    )
    if prediction_mode == MATCHED and prediction_overlaps:
        raise ValueError("Overlapping matched predictions cannot be additively pooled")
    output, group_audit = [], []
    for label, ids in parsed:
        sampled = [cid for cid in ids if obs[cid]["sampled"]]
        actual_volume = _finite_sum(
            (obs[cid]["sampled_volume_cm3"] for cid in sampled), "observed volume"
        )
        window_volume = _finite_sum(
            (pred[cid]["core_volume_cm3"] for cid in sampled), "predicted window volume"
        )
        group_audit.append(
            dict(
                group_id=label,
                core_ids=ids,
                sampled_core_ids=sampled,
                excluded_missing_core_ids=[
                    cid for cid in ids if not obs[cid]["sampled"]
                ],
                observed_known_volumes_cm3=[
                    obs[cid]["sampled_volume_cm3"] for cid in sampled
                ],
                observed_physical_volumes_cm3=[
                    obs[cid]["core_volume_cm3"] for cid in sampled
                ],
                predicted_physical_volumes_cm3=[
                    pred[cid]["core_volume_cm3"] for cid in sampled
                ],
                predicted_known_volumes_cm3=[
                    pred[cid]["sampled_volume_cm3"] for cid in sampled
                ],
            )
        )
        for quantity in quantity_columns:
            observed_total = predicted_density = equivalent = (
                physical_predicted_total
            ) = np.nan
            if sampled:
                observed_total = _finite_sum(
                    (obs[cid]["quantities"][quantity] for cid in sampled),
                    "observed additive total",
                )
                if prediction_mode == MATCHED:
                    physical_predicted_total = _finite_sum(
                        (pred[cid]["quantities"][quantity] for cid in sampled),
                        "predicted additive total",
                    )
                    predicted_density = _finite_ratio(
                        physical_predicted_total,
                        actual_volume,
                        "pooled predicted density",
                    )
                    equivalent = physical_predicted_total
                else:
                    # Virtual known volumes were constructed as exact physical pi*r²*h.
                    # Normalize by physical volume rather than silently reusing V_obs.
                    weighted = _finite_sum(
                        (
                            pred[cid]["quantities"][quantity]
                            / pred[cid]["core_volume_cm3"]
                            * obs[cid]["sampled_volume_cm3"]
                            for cid in sampled
                        ),
                        "weighted predicted density",
                    )
                    predicted_density = _finite_ratio(
                        weighted, actual_volume, "pooled predicted density"
                    )
                    equivalent = weighted
            output.append(
                dict(
                    group_id=label,
                    quantity=quantity,
                    sampled=bool(sampled),
                    selected_core_count=len(ids),
                    sampled_core_count=len(sampled),
                    observed_sampled_volume_cm3=actual_volume,
                    summed_prediction_window_volume_cm3=window_volume,
                    observed_additive_total=observed_total,
                    observed_density_per_cm3=(
                        _finite_ratio(
                            observed_total, actual_volume, "pooled observed density"
                        )
                        if sampled
                        else np.nan
                    ),
                    predicted_density_per_cm3=predicted_density,
                    predicted_equivalent_on_observed_volume=equivalent,
                    predicted_additive_total=physical_predicted_total,
                )
            )
    pooled = pd.DataFrame(output)
    diagnostics = dict(
        version=VERSION,
        prediction_mode=prediction_mode,
        qualification="EXPLICIT_AREA_MEAN_PROXY_ASSUMPTION_NOT_UNION_INTEGRATION",
        same_core_ids_and_sample_masks=True,
        observed_geometry_modified=False,
        observed_weights="actual sampled known_volume_cm3 only",
        missing_policy="exclude_on_identical_explicit_sampled_mask_never_impute_zero",
        groups=group_audit,
        support_mapping=[
            dict(
                core_id=cid,
                sampled=obs[cid]["sampled"],
                observed_geometry_cm={key: obs[cid][key] for key in GEOMETRY},
                predicted_geometry_cm={key: pred[cid][key] for key in GEOMETRY},
                observed_known_volume_cm3=obs[cid]["sampled_volume_cm3"],
                observed_physical_volume_cm3=obs[cid]["core_volume_cm3"],
                predicted_known_volume_cm3=pred[cid]["sampled_volume_cm3"],
                predicted_physical_volume_cm3=pred[cid]["core_volume_cm3"],
            )
            for _, ids in parsed
            for cid in ids
        ],
        ungrouped_core_ids=[cid for cid in obs if cid not in selected],
        observed_overlap_pairs=observed_overlaps,
        predicted_window_overlap_pairs=prediction_overlaps,
        virtual_union_volume_supported=False,
        virtual_union_additive_totals_supported=False,
        summed_prediction_window_volume_interpretation="audit_sum_of_windows_not_union_or_observed_volume",
        equivalent_interpretation=(
            "virtual density proxy times observed sampled volume; not virtual union mass/length"
            if prediction_mode == VIRTUAL
            else "physical matched-support additive total"
        ),
    )
    return pooled, diagnostics

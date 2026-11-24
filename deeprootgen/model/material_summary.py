"""Length and dry mass of valid root material by order and diameter class."""

import numpy as np

from .cohort_geometry import equivalent_diameter, material_cuts, taper_diameter
from .point_taper import exponential_profile_integral, point_diameter, profile_cuts


def _taper_pieces(lengths, density, profile, threshold):
    """Split at density changes, taper bends and the physical cutoff crossing."""
    ends = np.cumsum(lengths)
    if "rate_per_cm" in profile:
        total = float(ends[-1])
        cuts = np.unique(np.r_[0., ends, profile_cuts(total, profile, threshold)])
        starts, stops = cuts[:-1], cuts[1:]
        fine = point_diameter((starts + stops) / 2., total, profile) <= threshold
        rtd = density[np.searchsorted(ends, stops)]
        volume = np.pi / 4 * exponential_profile_integral(starts, stops, total, profile)
        return stops - starts, volume * rtd, fine
    base, tip, midpoint = (profile[k] for k in ("base", "tip", "midpoint"))
    cuts = material_cuts(
        float(ends[-1]),
        ends,
        [],
        base,
        tip,
        threshold,
        midpoint,
        minimum_interval_cm=0.0,
    )
    d = taper_diameter(cuts, float(ends[-1]), base, tip, midpoint)
    # Cut positions are independent of the graph's exported equivalent diameters.
    # A piece ending exactly on the threshold belongs to the side of its interior.
    fine = (d[:-1] + d[1:]) / 2 <= threshold
    intervals = np.diff(cuts)
    rtd = density[np.searchsorted(ends, cuts[1:])]
    areas = np.pi / 4 * equivalent_diameter(d[:-1], d[1:]) ** 2
    return intervals, intervals * areas * rtd, fine


def _organ_pieces(organ, threshold, profile):
    data = [n.node_data for n in organ.segments]
    xyz = [(p.x, p.y, p.z) for p in [organ.parent_node.node_data, *data]]
    lengths = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
    density = np.asarray([p.root_tissue_density for p in data], dtype=float)
    if not np.isfinite(lengths).all() or (lengths <= 0).any():
        raise ValueError(
            "Root material summary requires positive finite physical segment lengths"
        )
    if not np.isfinite(density).all() or (density <= 0).any():
        raise ValueError(
            "Root material summary requires positive finite dry tissue density"
        )
    if profile is not None:
        return _taper_pieces(lengths, density, profile, threshold)
    diameters = np.asarray([p.diameter for p in data], dtype=float)
    if not np.isfinite(diameters).all() or (diameters < 0).any():
        raise ValueError(
            "Root material summary requires finite nonnegative cylinder diameters"
        )
    mass = np.pi / 4 * lengths * diameters**2 * density
    return lengths, mass, diameters <= threshold


def summarize_root_material(
    simulation, max_order, threshold_root_diameter_cm, tapers=None
):
    """Summarize the published organ registry on the final physical centrelines."""
    threshold = threshold_root_diameter_cm
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold_root_diameter_cm must be positive and finite")
    by_order = []
    length_by_class = np.zeros(2)
    biomass_by_class = np.zeros(2)
    excluded = 0
    for order in range(1, max_order + 1):
        count, length = 0, 0.0
        for organ in simulation.organs.get(order, []):
            if organ.invalid_root or any(
                n.node_data.invalid_root for n in organ.segments
            ):
                excluded += 1
                continue
            oid = organ.segments[0].node_data.organ_id
            profile = (tapers or {}).get(oid)
            if profile is None:
                profile = getattr(getattr(organ, "axis_state", None), "material", None)
            lengths, masses, fine = _organ_pieces(organ, threshold, profile)
            count += 1
            length += float(lengths.sum())
            for index, selected in enumerate((fine, ~fine)):
                length_by_class[index] += lengths[selected].sum()
                biomass_by_class[index] += masses[selected].sum()
        by_order.append(dict(order=order, root_count=count, length_cm=length))
    classes = {
        label: dict(
            length_cm=float(length_by_class[i]),
            dry_biomass_g=float(biomass_by_class[i]),
        )
        for i, label in enumerate(("at_or_below", "above"))
    }
    return dict(
        threshold_root_diameter_cm=threshold,
        by_order=by_order,
        diameter_classes=classes,
        excluded_invalid_root_count=excluded,
        undefined_ratios={
            name: "no positive total on valid root material"
            for name, total in [
                ("root_ratio_biomass", biomass_by_class.sum()),
                ("root_ratio_length", length_by_class.sum()),
            ]
            if total == 0
        },
        achieved_root_ratio_biomass=_fraction(biomass_by_class),
        achieved_root_ratio_length=_fraction(length_by_class),
    )


def _fraction(totals):
    total = float(totals.sum())
    return float(totals[0] / total) if total else None

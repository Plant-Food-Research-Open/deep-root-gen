"""Assign exact volume-weighted dry density to published physical root intervals."""

import numpy as np

from .point_taper import exponential_profile_integral, point_diameter, profile_cuts


def _lookup(diameter_cm, density):
    bounds = np.asarray(density.bounds_mm) / 10
    values = np.asarray(diameter_cm)
    bands = np.searchsorted(bounds, values, side="left")
    for i, finer in enumerate(density.equality_to_finer):
        if not finer:
            bands += values == bounds[i]
    return np.asarray(density.density_g_cm3)[bands]


def apply_diameter_density(organ, density):
    data = [n.node_data for n in organ.segments]
    taper = getattr(getattr(organ, "axis_state", None), "material", None)
    if taper is None:
        effective = _lookup([node.diameter for node in data], density)
    else:
        points = [organ.parent_node.node_data, *data]
        xyz = np.array([(v.x, v.y, v.z) for v in points])
        ends = np.cumsum(np.linalg.norm(np.diff(xyz, axis=0), axis=1))
        if np.any(np.diff(np.r_[0.0, ends]) <= 0):
            raise ValueError(
                "Diameter-dependent density requires positive physical intervals"
            )
        length = ends[-1]
        cuts = [profile_cuts(length, taper, mm / 10) for mm in density.bounds_mm]
        stations = np.unique(np.concatenate(([0.0], ends, *cuts)))
        left, right = stations[:-1], stations[1:]
        d = point_diameter((left + right) / 2, length, taper)
        if "rate_per_cm" in taper:
            integral = exponential_profile_integral(left, right, length, taper)
        else:
            a, b = point_diameter(left, length, taper), point_diameter(
                right, length, taper
            )
            integral = (right - left) * (a * a + a * b + b * b) / 3
        owner = np.searchsorted(ends, right)
        volume = np.bincount(owner, weights=integral, minlength=len(ends))
        mass = np.bincount(
            owner, weights=integral * _lookup(d, density), minlength=len(ends)
        )
        mid = (np.r_[0.0, ends[:-1]] + ends) / 2
        effective = np.divide(
            mass,
            volume,
            out=_lookup(point_diameter(mid, length, taper), density),
            where=volume > 0,
        )
    for node, value in zip(data, effective):
        node.root_tissue_density = float(value)
    organ.diameter_density_applied = True
    organ.mass = organ.calculate_mass()

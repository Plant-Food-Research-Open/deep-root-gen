"""Diameter-resolved root material on realized axes. Lengths and diameters use cm."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DiameterDensity:
    """Dry g per cm³ of fresh tissue, ordered from finest to coarsest.

    Each equality flag assigns a cylinder at the corresponding boundary to
    the finer band (True) or the coarser band (False).
    """

    bounds_mm: tuple
    density_g_cm3: tuple
    equality_to_finer: tuple

    def __post_init__(self):
        bounds = np.asarray(self.bounds_mm, dtype=float)
        density = np.asarray(self.density_g_cm3, dtype=float)
        if (bounds.ndim != 1 or not np.isfinite(bounds).all()
                or np.any(bounds <= 0) or np.any(np.diff(bounds) <= 0)):
            raise ValueError("Diameter bounds must be positive, finite and increasing")
        if (density.shape != (len(bounds) + 1,) or np.any(density <= 0)
                or not np.isfinite(density).all()):
            raise ValueError("One positive finite density is required for each band")
        if (len(self.equality_to_finer) != len(bounds)
                or not all(isinstance(v, (bool, np.bool_)) for v in self.equality_to_finer)):
            raise ValueError("Each diameter bound needs an equality convention")


GRAPEVINE_STEPPED = DiameterDensity(
    (1., 2., 2.5, 12., 30.), (.25, .30, .40, .45, .50, .50),
    (False, True, True, True, True),
)


class TaperedAxes:
    """Vectorized integrals for the native exponential and two-slope point tapers."""

    def __init__(self, length_cm, base_cm, tip_cm, midpoint, rate_per_cm, thick_min_cm):
        length, base, tip, mid, rate, thick = np.broadcast_arrays(*[
            np.asarray(a, dtype=float) for a in
            (length_cm, base_cm, tip_cm, midpoint, rate_per_cm, thick_min_cm)
        ])
        if (not all(np.isfinite(x).all() for x in (length, base, tip, mid, rate, thick))
                or np.any(length <= 0) or np.any(tip < 0) or np.any(base < tip)
                or np.any((mid < 0) | (mid > 1))):
            raise ValueError("Expected finite lengths and nonincreasing physical tapers")
        exponential = rate >= 0  # negative rate denotes a pure two-slope taper
        if np.any(exponential & ((thick <= 0) | (thick > base))):
            raise ValueError("Invalid exponential transition diameter")
        self.length = length
        self.base = base
        self.rate = np.maximum(rate, 0.)
        log_ratio = np.log(np.where(exponential, base, 1.) / np.where(exponential, thick, 1.))
        transition = np.divide(log_ratio, rate, out=length.copy(), where=rate > 0)
        self.join = np.where(exponential, np.minimum(length, transition), 0.)
        start = np.where(exponential, thick, base)
        end = np.where(exponential, np.minimum(thick, tip), tip)
        half = (length - self.join) / 2
        middle = end + (start - end) * mid
        self.linear = ((self.join, half, start, middle),
                       (self.join + half, half, middle, end))

    def prefix_length(self, diameter_cm, inclusive=False):
        """Length with d > threshold, or d >= threshold when inclusive."""
        d = diameter_cm
        if not np.isfinite(d) or d <= 0:
            raise ValueError("Diameter threshold must be positive and finite")
        above = np.greater_equal if inclusive else np.greater
        crossing = np.divide(np.log(np.maximum(self.base, d) / d), self.rate,
                             out=np.zeros_like(self.length), where=self.rate > 0)
        prefix = np.where(self.rate > 0, np.minimum(self.join, crossing),
                          self.join * above(self.base, d))
        for _, width, start, end in self.linear:
            fraction = np.divide(start - d, start - end, out=np.zeros_like(width),
                                 where=start != end)
            prefix += width * np.where(start == end, above(start, d), np.clip(fraction, 0, 1))
        return prefix

    def prefix_volume(self, station):
        """Fresh volume in cm³ from the base through a physical arclength."""
        x = np.clip(station, 0, self.length)
        width = np.minimum(x, self.join)
        exponent = -2 * self.rate * width
        factor = np.divide(np.expm1(exponent), exponent, out=np.ones_like(width),
                           where=exponent != 0)
        integral = width * self.base**2 * factor
        for left, span, start, end in self.linear:
            width = np.clip(x - left, 0, span)
            fraction = np.divide(width, span, out=np.zeros_like(width), where=span > 0)
            right = start + (end - start) * fraction
            integral += width * (start**2 + start * right + right**2) / 3.
        return np.pi / 4 * integral

    def band_material(self, profile):
        """Return per-axis length, fresh volume and dry mass with band on the last axis."""
        stations = [self.length]
        stations.extend(self.prefix_length(b / 10., inclusive=not finer)
                        for b, finer in zip(profile.bounds_mm, profile.equality_to_finer))
        stations.append(np.zeros_like(self.length))
        volumes = [self.prefix_volume(x) for x in stations]
        lengths = -np.diff(np.stack(stations, axis=-1), axis=-1)
        volume = -np.diff(np.stack(volumes, axis=-1), axis=-1)
        return lengths, volume, volume * np.asarray(profile.density_g_cm3)


def summarize_diameter_material(simulation, density=GRAPEVINE_STEPPED):
    """Reweigh valid root organs after a run. Excludes crown/support connectors."""
    result = []
    for order, organs in sorted(simulation.organs.items()):
        profiles, lengths = [], []
        for organ in organs:
            nodes = [n.node_data for n in organ.segments]
            if organ.invalid_root or any(n.invalid_root for n in nodes):
                continue
            points = [organ.parent_node.node_data, *nodes]
            xyz = np.array([(p.x, p.y, p.z) for p in points])
            ds = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
            p = getattr(getattr(organ, "axis_state", None), "material", None)
            if p is None:
                for node, length in zip(nodes, ds):
                    profiles.append((node.diameter, node.diameter, .5, -1., 0.))
                    lengths.append(length)
            else:
                profiles.append((p["base"], p["tip"], p["midpoint"],
                                 p.get("rate_per_cm", -1.), p.get("thick_min_cm", 0.)))
                lengths.append(ds.sum())
        if lengths:
            axes = TaperedAxes(lengths, *np.asarray(profiles).T)
            length, volume, mass = (v.sum(axis=0) for v in axes.band_material(density))
            result.append(dict(order=order, length_cm=length.tolist(),
                               fresh_volume_cm3=volume.tolist(), dry_mass_g=mass.tolist()))
    return dict(bounds_mm=list(density.bounds_mm), density_g_cm3=list(density.density_g_cm3),
                equality_to_finer=list(density.equality_to_finer), by_order=result)

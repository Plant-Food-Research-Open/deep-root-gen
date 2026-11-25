"""Integrate wet exposure along a realized piecewise-linear root, in centimetres."""

import numpy as np
from scipy.optimize import brentq

from .point_taper import point_diameter, profile_cuts

GAUSS, WEIGHTS = np.polynomial.legendre.leggauss(16)


def cosine(r):
    r = np.clip(r, 0.0, 1.0)
    return 0.5 * (1.0 + np.cos(np.pi * r))


def exposure(zone, xyz):
    """K in surveyed coordinates, with positive depth in the third column."""
    x, y, d = np.asarray(xyz).T
    r2 = 0.0
    if zone.line_offsets_cm is not None:
        dx = np.min(np.abs(x[..., None] - zone.line_offsets_cm), axis=-1)
        if zone.row_period_cm:
            step = zone.row_period_cm
            dx = (x - zone.line_offsets_cm[0] + step / 2) % step - step / 2
        r2 = (dx / zone.across_radius_cm) ** 2
        if zone.emitter_spacing_cm is not None:
            spacing = zone.emitter_spacing_cm
            dy = (y - zone.emitter_origin_y_cm + spacing / 2) % spacing - spacing / 2
            r2 += (dy / zone.along_radius_cm) ** 2
    if zone.treatment == "buried_drip":
        dz = d - zone.irrigation_depth_cm
        radius = np.where(dz < 0, zone.upper_radius_cm, zone.lower_radius_cm)
        k = cosine(np.sqrt(r2 + (dz / radius) ** 2))
    elif zone.surface_profile == "deep_peak":
        k = cosine(np.sqrt(r2)) * cosine(
            np.where(d <= 37.5, (37.5 - d) / 37.5, (d - 37.5) / 12.5)
        )
    else:
        k = cosine(np.sqrt(r2)) * cosine((d - 40.0) / 10.0)
    return np.where(d >= 0, k, 0.0)


def _dcosine(r):
    """d cosine(r) / dr; zero where cosine is clipped (r <= 0 or r >= 1)."""
    r = np.asarray(r, float)
    return np.where((r > 0) & (r < 1), -0.5 * np.pi * np.sin(np.pi * r), 0.0)


def exposure_gradient(zone, xyz):
    """Analytic dK/d(x, y, depth) in surveyed coordinates, on soil support only.

    Above the surface K and its gradient are zero; no evaluation probes air.
    At the outlet centre and beyond the footprint the gradient is exactly zero.
    """
    xyz = np.atleast_2d(np.asarray(xyz, float))
    x, y, d = xyz.T
    n = len(x)
    r2, dr2_dx, dr2_dy = np.zeros(n), np.zeros(n), np.zeros(n)
    if zone.line_offsets_cm is not None:
        lines = np.asarray(zone.line_offsets_cm, float)
        if zone.row_period_cm:
            step = zone.row_period_cm
            dx = (x - lines[0] + step / 2) % step - step / 2
        else:
            signed = x[:, None] - lines
            dx = signed[np.arange(n), np.argmin(np.abs(signed), axis=1)]
        r2 = (dx / zone.across_radius_cm) ** 2
        dr2_dx = 2 * dx / zone.across_radius_cm**2
        if zone.emitter_spacing_cm is not None:
            spacing = zone.emitter_spacing_cm
            dy = (y - zone.emitter_origin_y_cm + spacing / 2) % spacing - spacing / 2
            r2 = r2 + (dy / zone.along_radius_cm) ** 2
            dr2_dy = 2 * dy / zone.along_radius_cm**2
    with np.errstate(divide="ignore", invalid="ignore"):
        if zone.treatment == "buried_drip":
            dz = d - zone.irrigation_depth_cm
            radius = np.where(dz < 0, zone.upper_radius_cm, zone.lower_radius_cm)
            big_r = np.sqrt(r2 + (dz / radius) ** 2)
            f = np.where(big_r > 0, _dcosine(big_r) / (2 * big_r), 0.0)
            grad = np.column_stack([f * dr2_dx, f * dr2_dy, f * 2 * dz / radius**2])
        else:
            rh = np.sqrt(r2)
            fh = np.where(rh > 0, _dcosine(rh) / (2 * rh), 0.0)
            if zone.surface_profile == "deep_peak":
                upper = d <= 37.5
                s = np.where(upper, (37.5 - d) / 37.5, (d - 37.5) / 12.5)
                dv = _dcosine(s) * np.where(upper, -1 / 37.5, 1 / 12.5)
            else:
                s = (d - 40.0) / 10.0
                dv = _dcosine(s) / 10.0
            v = cosine(s)
            grad = np.column_stack([fh * dr2_dx * v, fh * dr2_dy * v, cosine(rh) * dv])
    return np.where((d >= 0)[:, None], grad, 0.0)


def gradient_bound(zone):
    """Upper bound on |grad K| per cm: pi / (2 * shortest kernel length scale)."""
    scales = []
    if zone.line_offsets_cm is not None:
        scales.append(zone.across_radius_cm)
        if zone.emitter_spacing_cm is not None:
            scales.append(zone.along_radius_cm)
    if zone.treatment == "buried_drip":
        scales += [zone.upper_radius_cm, zone.lower_radius_cm]
    else:
        scales.append(12.5 if zone.surface_profile == "deep_peak" else 10.0)
    return np.pi / (2 * min(scales))


class MoistureTropism:
    """Per-cm heading increment gain * grad K at a model-frame point (z up).

    K is the long-term wet-zone exposure; its analytic gradient is zero outside
    the footprint and at its centre, so roots are turned back into the zone
    near its edge and soil beyond the footprint exerts no pull.
    """

    def __init__(self, zone, surface_z, gain):
        self.zone, self.surface_z, self.gain = zone, surface_z, float(gain)
        self.flip = np.array([zone.reflect_x, zone.reflect_y, -1.0])

    def __call__(self, point):
        s = survey_points(np.asarray(point, float)[None, :], self.zone, self.surface_z)
        return self.gain * self.flip * exposure_gradient(self.zone, s)[0]


def survey_points(points, zone, surface_z):
    return np.array([zone.origin_x_cm, zone.origin_y_cm, surface_z]) + points * [
        zone.reflect_x,
        zone.reflect_y,
        -1.0,
    ]


def _crossings(grid, values, stations):
    """Arc at each strict crossing of a coordinate plane."""
    out = []
    a, b = values[:-1], values[1:]
    for level in grid:
        hit = ((a < level) & (b > level)) | ((b < level) & (a > level))
        out.extend(
            stations[:-1][hit]
            + np.diff(stations)[hit] * (level - a[hit]) / (b[hit] - a[hit])
        )
    return out


def _positions(arcs, stations, points):
    return np.column_stack([np.interp(arcs, stations, coord) for coord in points.T])


def _footprint_edges(zone, stations, points):
    """Find ellipsoid entry/exit even when both segment endpoints are dry."""
    if zone.line_offsets_cm is None:
        return []
    start = points[:-1].copy()
    step = np.diff(points, axis=0)
    mid = start + 0.5 * step
    lines = np.asarray(zone.line_offsets_cm)
    start[:, 0] -= lines[np.argmin(abs(mid[:, :1] - lines), axis=1)]
    if zone.row_period_cm:
        s = zone.row_period_cm
        start[:, 0] -= s * np.floor((mid[:, 0] - lines[0]) / s + 0.5)
    start[:, 0] /= zone.across_radius_cm
    step[:, 0] /= zone.across_radius_cm
    if zone.emitter_spacing_cm is None:
        start[:, 1] = step[:, 1] = 0.0
    else:
        s = zone.emitter_spacing_cm
        center = zone.emitter_origin_y_cm + s * np.floor(
            (mid[:, 1] - zone.emitter_origin_y_cm) / s + 0.5
        )
        start[:, 1] = (start[:, 1] - center) / zone.along_radius_cm
        step[:, 1] /= zone.along_radius_cm
    if zone.treatment == "buried_drip":
        rad = np.where(
            mid[:, 2] < zone.irrigation_depth_cm,
            zone.upper_radius_cm,
            zone.lower_radius_cm,
        )
        start[:, 2] = (start[:, 2] - zone.irrigation_depth_cm) / rad
        step[:, 2] /= rad
    else:
        start[:, 2] = step[:, 2] = 0.0
    aa = np.einsum("ij,ij->i", step, step)
    bb = np.einsum("ij,ij->i", start, step)
    cc = np.einsum("ij,ij->i", start, start) - 1.0
    disc = bb * bb - aa * cc
    ok = (aa > 0) & (disc > 0)
    roots = []
    for sign in (-1, 1):
        t = (-bb[ok] + sign * np.sqrt(disc[ok])) / aa[ok]
        inside = (t > 0) & (t < 1)
        roots.extend((stations[:-1][ok] + np.diff(stations)[ok] * t)[inside])
    return roots


class WetContour:
    """Eligible linear intervals with quadrature of smooth, boundary-clipped K."""

    def __init__(
        self, zone, curve, surface_z, lower, upper, taper, ends, diameters, threshold
    ):
        self.zone = zone
        points = survey_points(curve.points, zone, surface_z)
        s = curve.stations
        planes = (
            [0.0, zone.irrigation_depth_cm]
            if zone.treatment == "buried_drip"
            else [0.0, 37.5, 40.0, 50.0]
        )
        depth_bins = 10 * np.arange(
            np.ceil(points[:, 2].min() / 10), np.floor(points[:, 2].max() / 10) + 1
        )
        cuts = _crossings(np.unique(np.r_[planes, depth_bins]), points[:, 2], s)
        lines = np.sort(zone.line_offsets_cm) if zone.line_offsets_cm else []
        if len(lines) > 1:
            cuts.extend(_crossings((lines[:-1] + lines[1:]) / 2, points[:, 0], s))
        if zone.row_period_cm:
            step = zone.row_period_cm
            first = lines[0] + step / 2
            bounds = np.ceil((points[:, 0].min() - first) / step), np.floor(
                (points[:, 0].max() - first) / step
            )
            cuts.extend(
                _crossings(
                    first + step * np.arange(bounds[0], bounds[1] + 1), points[:, 0], s
                )
            )
        if zone.emitter_spacing_cm:
            step = zone.emitter_spacing_cm
            first = zone.emitter_origin_y_cm + step / 2
            bounds = np.ceil((points[:, 1].min() - first) / step), np.floor(
                (points[:, 1].max() - first) / step
            )
            cuts.extend(
                _crossings(
                    first + step * np.arange(bounds[0], bounds[1] + 1), points[:, 1], s
                )
            )
        stages = np.unique(np.r_[s, cuts])
        edges = _footprint_edges(zone, stages, _positions(stages, s, points))
        material = (
            profile_cuts(taper["length"], taper, threshold)
            if taper is not None
            else ends
        )
        bounds = np.unique(
            np.clip(np.r_[stages, edges, material, lower, upper], lower, upper)
        )
        mid = (bounds[1:] + bounds[:-1]) / 2
        values = (
            point_diameter(mid, taper["length"], taper)
            if taper is not None
            else diameters[np.searchsorted(ends, mid).clip(max=len(ends) - 1)]
        )
        keep = values >= threshold
        self.starts, self.stops = bounds[:-1][keep], bounds[1:][keep]
        self.widths = self.stops - self.starts
        self.xyz = _positions(self.starts, s, points)
        self.steps = _positions(self.stops, s, points) - self.xyz
        self.eligible = float(self.widths.sum())
        self.weights = self.integral(np.arange(len(self.widths)), 1.0)
        self.H = float(self.weights.sum())

    def integral(self, idx, fraction):
        pts = (
            self.xyz[idx, None, :]
            + self.steps[idx, None, :] * ((GAUSS + 1) * (0.5 * fraction))[None, :, None]
        )
        k = exposure(self.zone, pts.reshape(-1, 3)).reshape(len(idx), len(GAUSS))
        return (k @ WEIGHTS) * (0.5 * fraction * self.widths[idx])

    def sample(self, rng, count, wet):
        weights = self.weights if wet else self.widths
        cs = np.cumsum(weights)
        target = rng.random(count) * cs[-1]
        bins = np.minimum(np.searchsorted(cs, target, side="right"), len(cs) - 1)
        mass = np.clip(target - np.r_[0.0, cs][bins], 0.0, weights[bins])
        if wet:
            frac = [
                (
                    brentq(lambda u: self.integral([i], u)[0] - v, 0.0, 1.0, xtol=1e-12)
                    if 0 < v < weights[i]
                    else float(v > 0)
                )
                for i, v in zip(bins, mass)
            ]
        else:
            frac = mass / weights[bins]
        return self.starts[bins] + self.widths[bins] * frac

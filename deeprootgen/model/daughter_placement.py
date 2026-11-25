"""Place existing terminal daughters on the realized, diameter-eligible contour."""

import numpy as np

from .branch_eligibility import attachment_diameters
from .cohort_geometry import bounded_draw
from .irrigation_branching import _add_child, _insert, _support
from .laws import first_branch_sites, law_stream, point_taper_dimensions
from .point_taper import point_diameter, profile_cuts
from .streams import RandomStreams


QUAD_POINTS, QUAD_WEIGHTS = np.polynomial.legendre.leggauss(8)


def row_distance(x_cm, period_cm):
    """Fraction of the half-spacing to the nearest parallel row (along y)."""
    half = period_cm / 2
    return abs((x_cm + half) % period_cm - half) / half


def depth_basis(depth_cm):
    depth_cm = np.asarray(depth_cm)
    return np.stack(
        [
            np.ones_like(depth_cm),
            depth_cm / 100,
            np.maximum(depth_cm - 30, 0) / 100,
            np.maximum(depth_cm - 90, 0) / 100,
        ],
        axis=-1,
    )


def profile_preference(profile, depth, cross):
    lo, hi = profile.depth_range_cm
    supported = np.clip(depth, lo, hi)
    span = np.maximum(lo - depth, depth - hi)
    fade = np.clip(1 - span / profile.fade_cm, 0, 1)
    zone = np.searchsorted(profile.zone_boundaries, cross, side="right")
    support = np.minimum(np.asarray(profile.zone_tube_counts)[zone] / 2, 1)
    beta = profile.coefficients
    row_term = beta[4] + (profile.row_depth_slope or 0.0) * (supported - 90.0) / 100.0
    score = depth_basis(supported) @ beta[:4] + row_term * cross * support
    return np.clip((score - profile.training_mean) / 0.20, -1, 1) * fade


def vineyard_3d_preference(profile, depth_cm, x_cm, y_cm):
    """Evaluate normalized preference at broadcastable crown-relative x/y and soil depths."""
    depth = np.asarray(depth_cm, dtype=float)
    knots = profile.depth_knots_cm
    coefficients = np.asarray(profile.coefficients)
    intercept, across, along, interaction = [
        np.interp(depth, knots, column) for column in coefficients.T
    ]
    x_phase = np.remainder(x_cm, profile.across_period_cm) / profile.across_period_cm
    y_phase = np.remainder(y_cm, profile.along_period_cm) / profile.along_period_cm
    x_cos, y_cos = np.cos(2 * np.pi * x_phase), np.cos(2 * np.pi * y_phase)
    score = intercept + across * x_cos + along * y_cos + interaction * x_cos * y_cos
    outside = np.maximum(np.maximum(knots[0] - depth, depth - knots[-1]), 0.0)
    fade = np.clip(1.0 - outside / profile.fade_cm, 0.0, 1.0)
    return np.clip(score, -1.0, 1.0) * fade


def _crown_xy(state):
    """Disk and indexed primary positions use the local model frame centred on the vine."""
    origin = state.laws.origins or {}
    if origin.get("layout") == "point":
        return origin["x_cm"], origin["y_cm"]
    if state.vine_origin is not None:
        entry, _ = state.vine_origin
        if entry["layout"] == "common_point":
            return entry["origin"]["x_cm"], entry["origin"]["y_cm"]
    return 0.0, 0.0


BEARING_PROBE_CM = 40.0
BEARING_GAIN = 2.0


def surface_bearing_heading(
    state, settings, tangent, heading, position, length_cm, order, organ_id
):
    """Tilt the native uniform azimuth over four quarter turns at its original polar angle."""
    axis = tangent / np.linalg.norm(tangent)
    parallel = (axis @ heading) * axis
    radial = heading - parallel
    quarter_turn = np.cross(axis, radial)
    candidates = np.array(
        [heading, parallel + quarter_turn, parallel - radial, parallel - quarter_turn]
    )
    probe_cm = min(BEARING_PROBE_CM, length_cm)
    probes = position + probe_cm * candidates
    # The native integrator reflects the entire vertical step when it would cross the soil surface.
    reflected = probes[:, 2] > state.laws.surface_z_cm
    probes[reflected, 2] = position[2] - probe_cm * np.abs(candidates[reflected, 2])
    x0, y0 = _crown_xy(state)
    scores = vineyard_3d_preference(
        settings.profile,
        state.laws.surface_z_cm - probes[:, 2],
        probes[:, 0] - x0,
        probes[:, 1] - y0,
    )
    weights = np.exp(BEARING_GAIN * settings.strength * scores)
    probabilities = weights / weights.sum()
    # Native uniform rotations supply 1/4 of each quartet. Keep the common probability
    # mass; only transfer its excess to directions with a target probability above 1/4.
    keep = min(1.0, 4.0 * probabilities[0])
    chosen = 0
    if keep < 1.0:
        rng = state.streams.keyed(
            "daughter_placement.surface_bearing", "1", order, organ_id
        )
        if rng.random() >= keep:
            excess = np.maximum(probabilities - 0.25, 0.0)
            chosen = int(rng.choice(4, p=excess / excess.sum()))
    receipt = dict(
        quarter_turns=chosen,
        probe_cm=float(probe_cm),
        reflected_probes=int(reflected.sum()),
        native_preference=float(scores[0]),
        selected_preference=float(scores[chosen]),
        score_range=float(np.ptp(scores)),
    )
    return candidates[chosen], receipt


def _weights(settings, xyz, surface, crown_xy=(0.0, 0.0)):
    depth = surface - xyz[:, 2]
    profile = settings.profile
    if profile is None:
        start, top, bottom, stop = settings.layer_depths_cm or (
            80.0,
            90.0,
            150.0,
            170.0,
        )
        peak = settings.layer_peak_multiplier or 1.5
        ramp = np.clip(
            np.minimum(
                (depth - start) / (top - start), (stop - depth) / (stop - bottom)
            ),
            0,
            1,
        )
        return 1 + settings.strength * ((peak - 1) / 2) * (1 - np.cos(np.pi * ramp))
    if profile.version == "vineyard_3d_v1":
        score = vineyard_3d_preference(
            profile, depth, xyz[:, 0] - crown_xy[0], xyz[:, 1] - crown_xy[1]
        )
    else:
        score = profile_preference(
            profile, depth, row_distance(xyz[:, 0], profile.row_period_cm)
        )
    return np.power(1.5, settings.strength * score)


def eligible_contour(parent, curve, threshold, lower, upper):
    """Return exact diameter-clipped intervals over the selected arc bounds."""
    if upper <= lower:
        return np.empty(0), np.empty(0)
    taper = parent.axis_state.material
    ends = curve.construction_arcs
    material = (
        profile_cuts(taper["length"], taper, threshold) if taper is not None else ends
    )
    bounds = np.unique(
        np.clip(np.r_[curve.stations, material, lower, upper], lower, upper)
    )
    mid = (bounds[:-1] + bounds[1:]) / 2
    diameters = (
        point_diameter(mid, taper["length"], taper)
        if taper is not None
        else parent.get_diameters()[np.searchsorted(ends, mid).clip(max=len(ends) - 1)]
    )
    keep = diameters >= threshold
    return bounds[:-1][keep], bounds[1:][keep]


def _depth_add_envelope(settings, curve, starts, stops, surface):
    """Bound excess intensity on monotone pieces of each eligible linear segment."""
    knots = np.asarray(settings.layer_depths_cm or (80.0, 90.0, 150.0, 170.0))
    pieces = []
    for left, right in zip(starts, stops):
        first, last = surface - curve.position([left, right])[:, 2]
        cuts = np.array([left, right])
        if first != last:
            fractions = (knots - first) / (last - first)
            interior = fractions[(fractions > 0.0) & (fractions < 1.0)]
            cuts = np.sort(np.r_[left, left + (right - left) * interior, right])
        values = _weights(settings, curve.position(cuts), surface) - 1.0
        for a, b, bound in zip(
            cuts[:-1], cuts[1:], np.maximum(values[:-1], values[1:])
        ):
            if bound > 0.0 and b > a:
                pieces.append((a, b, bound))
    if not pieces:
        raise ValueError("No eligible contour with positive deep-add intensity")
    return np.asarray(pieces).T


def _sample_sites(
    state, settings, parent, curve, starts, stops, count, *, uniform=False
):
    oid = parent.axis_state.biological_id
    rng = state.streams.keyed("daughter_placement.position", "1", oid)
    cdf = np.cumsum(stops - starts)
    sites = []
    occupied = np.r_[curve.construction_arcs, curve.stations]
    max_weight = (
        1.5**settings.strength
        if settings.profile
        else 1 + ((settings.layer_peak_multiplier or 1.5) - 1) * settings.strength
    )
    envelope = None
    for attempt in range(20000):
        if len(sites) == count:
            return sorted(sites)
        if attempt == 10000:
            if settings.mode != "add" or uniform or settings.profile is not None:
                break
            # A grazing contour can have negligible acceptance from the whole
            # parent. Change only the rejection proposal for the remaining sites.
            starts, stops, envelope = _depth_add_envelope(
                settings,
                curve,
                starts,
                stops,
                state.laws.surface_z_cm,
            )
            cdf = np.cumsum((stops - starts) * envelope)
        target = rng.random(count - len(sites)) * cdf[-1]
        idx = np.minimum(np.searchsorted(cdf, target, side="right"), len(cdf) - 1)
        distance = cdf[idx] - target
        if envelope is not None:
            distance = distance / envelope[idx]
        arcs = stops[idx] - distance
        xyz = curve.position(arcs)
        if not uniform:
            weight = _weights(settings, xyz, state.laws.surface_z_cm, _crown_xy(state))
            if settings.mode == "add":
                weight, bound = weight - 1, max_weight - 1
                if envelope is not None:
                    bound = envelope[idx]
            else:
                bound = max_weight
            arcs = arcs[rng.random(len(arcs)) * bound < weight]
        for arc in arcs:
            if (
                min(
                    np.min(abs(occupied - arc)),
                    min((abs(s - arc) for s in sites), default=np.inf),
                )
                > 1e-9
            ):
                sites.append(arc)
    if len(sites) == count:
        return sorted(sites)
    raise ValueError("Daughter placement exhausted its site sampling budget")


def _average_weight(state, settings, curve, starts, stops):
    if not len(starts):
        return 1.0
    # A bounded/even subdivision reduces quadrature error near profile hinges.
    fraction = (1 + QUAD_POINTS) / 2
    width = stops - starts
    arcs = starts[:, None] + width[:, None] * fraction
    xyz = curve.position(arcs.ravel())
    values = _weights(settings, xyz, state.laws.surface_z_cm, _crown_xy(state)).reshape(
        arcs.shape
    )
    return float(width @ (values @ (QUAD_WEIGHTS / 2)) / width.sum())


def _replay_stream(state, purpose, oid):
    # The live stream has already been consumed by scaffold construction.
    return law_stream(
        RandomStreams(state.resolved.seed), state.laws.streams, purpose, oid
    )


def _fresh_dimensions(state, parent, child, node):
    """Use the same pre-cap taper draw when the terminal birth site changes."""
    order = int(child.segments[0].node_data.order)
    law = state.laws.taper[order]
    maturity = state.laws.maturity
    oid = child.axis_state.biological_id
    diameter = float(attachment_diameters(parent, [node])[0])
    features = parent.feature_laws
    base, tip = point_taper_dimensions(
        law,
        child.plan["maturity"],
        None if maturity is None else maturity["diameter_power"],
        diameter,
        state.laws.cap,
        _replay_stream(state, "taper", oid),
        dict(diameter_constrained=0, tip_constrained=0),
        diameter_scale=features.diameter_factor(child),
    )
    child.parent_node = node
    child.segments[0].node_data.parent_id = node.node_data.node_id
    material = child.axis_state.material
    material.update(base=base, tip=tip)
    material.pop("rate_per_cm", None)
    material.pop("thick_min_cm", None)
    if "rate_per_cm" in law and base >= law["thick_min_cm"]:
        material.update(
            rate_per_cm=law["rate_per_cm"], thick_min_cm=law["thick_min_cm"]
        )
    child.plan.update(base=base, tip=tip)


def _birth(state, parent, curve, child, arc, **extra):
    x, y, z = curve.position([arc])[0]
    return dict(
        parent_id=parent.axis_state.biological_id,
        daughter_id=child.axis_state.biological_id,
        arc_cm=float(arc),
        x_cm=float(x),
        y_cm=float(y),
        depth_cm=float(state.laws.surface_z_cm - z),
        **extra
    )


def _new_daughters(state, parent, curve, sites, receipt):
    oid = parent.axis_state.biological_id
    order = int(parent.segments[0].node_data.order)
    state.budget.reserve_branch_proposals(
        len(sites), len(state.simulation.G.nodes), 0, oid
    )
    for index, arc in enumerate(sites):
        node = _insert(parent, curve, state, arc)
        child = _add_child(parent, node, state, oid, index)
        state.simulation.organs[order + 1].append(child)
        receipt["births"].append(_birth(state, parent, curve, child, arc))


def _discard(state, order, removed):
    if not removed:
        return
    doomed = set(removed)
    terminal = state.simulation.organs[order + 1]
    terminal[:] = [child for child in terminal if child not in doomed]
    for parent in {child.parent_node.organ for child in removed}:
        parent.child_organs[:] = [
            child for child in parent.child_organs if child not in doomed
        ]
    ids = {id(node) for child in removed for node in child.segments}
    graph = state.simulation.G
    graph.nodes[:] = [node for node in graph.nodes if id(node) not in ids]


def _place_parent(state, settings, parent, curve, threshold):
    lower, upper, rate, active, _ = _support(parent, curve)
    starts, stops = eligible_contour(parent, curve, threshold, max(0, lower), upper)
    width = float((stops - starts).sum())
    oid = parent.axis_state.biological_id
    children = parent.child_organs
    receipt = dict(parent_id=oid, eligible_cm=width, daughters=len(children), births=[])
    if not width:
        return receipt
    if settings.mode in ("add", "uniform_extra"):
        expected = (
            (_average_weight(state, settings, curve, starts, stops) - 1) * width * rate
        )
        count = (
            int(
                state.streams.keyed("daughter_placement.count", "1", oid).poisson(
                    max(0.0, expected)
                )
            )
            if active and expected > 0
            else 0
        )
        receipt.update(expected_extra=max(0.0, expected), drawn_extra=count)
        if count:
            sites = _sample_sites(
                state,
                settings,
                parent,
                curve,
                starts,
                stops,
                count,
                uniform=settings.mode == "uniform_extra",
            )
            _new_daughters(state, parent, curve, sites, receipt)
        return receipt
    if len(children) < 2:
        return receipt
    if settings.profile is None:
        z = state.laws.surface_z_cm - curve.position(np.r_[starts, stops])[:, 2]
        start, _, _, stop = settings.layer_depths_cm or (80.0, 90.0, 150.0, 170.0)
        if z.max() <= start or z.min() >= stop:
            return receipt
    # The earliest realized site is kept even when the proposed first was thin.
    sites = _sample_sites(
        state, settings, parent, curve, starts, stops, len(children) - 1
    )
    for child, site in zip(children[1:], sites):
        node = _insert(parent, curve, state, site)
        _fresh_dimensions(state, parent, child, node)
        receipt["births"].append(_birth(state, parent, curve, child, site))
    return receipt


def _terminal_support(state, parents):
    threshold = state.parameters.min_branching_diameter_cm
    for parent in parents:
        oid = parent.axis_state.biological_id
        curve = state.curves.get(oid)
        if curve is None or parent.invalid_root:
            continue
        lower, upper, _, active, _ = _support(parent, curve)
        starts, stops = eligible_contour(parent, curve, threshold, max(0, lower), upper)
        yield parent, curve, starts, stops, active


def _branch_probability(state, settings, parents):
    """Keep the usual conditional family and match expected eligible daughters."""
    from scipy.optimize import brentq

    order = settings.parent_order
    law = state.laws.branching[order]
    maturity = state.laws.maturity
    candidates = []
    for parent, curve, starts, stops, active in _terminal_support(state, parents):
        oid = parent.axis_state.biological_id
        factor = (
            parent.plan["maturity"]
            if maturity and maturity["scale_branch_probability"]
            else 1.0
        )
        baseline = factor * law["branch_probability"] if len(starts) else 0.0
        rng = _replay_stream(state, "branching", oid)
        if bounded_draw(law["first_branch_cm"], rng) != parent.plan["first_draw"]:
            raise ValueError(
                "Terminal branch replay did not reproduce the scaffold's first draw"
            )
        draw = float(rng.uniform())
        multiplier = _average_weight(state, settings, curve, starts, stops)
        sites = []
        if not active and baseline > 0:
            _, proposed = first_branch_sites(
                dict(law, branch_probability=1.0),
                order,
                order + 1,
                float(curve.stations[-1]),
                1.0,
                False,
                _replay_stream(state, "branching", oid),
                dict(branch_beyond_tip=0),
            )
            occupied = curve.construction_arcs
            sites = [
                arc
                for arc in proposed
                if np.any((starts <= arc) & (arc <= stops))
                and np.min(abs(occupied - arc)) > 1e-9
            ]
        n = len(parent.child_organs) if active else len(sites)
        candidates.append(
            (
                parent,
                curve,
                sites,
                draw,
                baseline,
                multiplier,
                n,
                float((stops - starts).sum()),
            )
        )
    if not candidates:
        return dict(parents=[], expected_daughters=0.0, guided_expected_daughters=0.0)
    old, weights, counts = (
        np.array(values) for values in zip(*(entry[4:7] for entry in candidates))
    )

    def probability(multiplier):
        return old * multiplier / (1 - old + old * multiplier)

    probs = probability(weights)
    target = float(counts @ probs)
    uniform = None
    if settings.mode == "branch_probability_uniform":
        low, high = weights.min(), weights.max()
        if low == high or not np.any(counts * old * (1 - old)):
            uniform = float(low)
        else:
            uniform = float(
                brentq(lambda x: counts @ probability(x) - target, low, high)
            )
        probs = probability(uniform)
    records, removed = [], []
    for (parent, curve, sites, draw, base, multiplier, n, eligible), p in zip(
        candidates, probs
    ):
        chosen = draw < p
        result = dict(
            parent_id=parent.axis_state.biological_id,
            eligible_cm=eligible,
            baseline_probability=base,
            multiplier=multiplier,
            probability=float(p),
            selected=bool(chosen),
            conditional_daughters=n,
            births=[],
            realized_daughters=n if chosen else 0,
        )
        if chosen:
            _new_daughters(state, parent, curve, sites, result)
        else:
            removed.extend(parent.child_organs)
        records.append(result)
    _discard(state, order, removed)
    return dict(
        parents=records,
        expected_daughters=float(counts @ probs),
        guided_expected_daughters=target,
        uniform_multiplier=uniform,
    )


def _deep_intervals(curve, starts, stops, z_limit):
    a, b = curve.position(starts)[:, 2], curve.position(stops)[:, 2]
    crossing = (a > z_limit) != (b > z_limit)
    cuts = starts[crossing] + (stops[crossing] - starts[crossing]) * (
        z_limit - a[crossing]
    ) / (b[crossing] - a[crossing])
    left, right = starts.copy(), stops.copy()
    left[crossing & (a > z_limit)] = cuts[a[crossing] > z_limit]
    right[crossing & (b > z_limit)] = cuts[b[crossing] > z_limit]
    keep = ((a < z_limit) | (b < z_limit)) & (right > left)
    return left[keep], right[keep]


def _balanced_cell_selection(xy, count, width_cm, rng):
    """Draw from every occupied horizontal cell once before revisiting a cell."""
    offset = rng.random(2)
    # Keep large cell coordinates out of fixed-width integer casts.
    scaled = np.asarray(xy, dtype=np.longdouble).reshape(-1, 2) / width_cm
    cells = np.floor(scaled - offset)
    _, labels = np.unique(cells, axis=0, return_inverse=True)
    labels = labels.reshape(-1)
    occupied = np.bincount(labels)
    visits = np.zeros(len(occupied), dtype=int)
    rounds = np.empty(len(labels), dtype=int)
    for i in rng.permutation(len(labels)):
        cell = labels[i]
        rounds[i] = visits[cell]
        visits[cell] += 1
    # A separate tie break gives each available cell an equal chance in a partial round.
    selected = np.lexsort((rng.random(len(labels)), rounds))[:count]
    diagnostics = dict(
        grid_origin_offset_cm=(offset * width_cm).tolist(),
        occupied_candidate_cells=len(occupied),
        occupied_birth_cells=len(np.unique(labels[selected])),
    )
    return np.sort(selected), diagnostics


def _balanced_sparse_sites(state, settings, candidates, count):
    arcs, xy = [], []
    for _, parent, curve, starts, stops in candidates:
        (arc,) = _sample_sites(
            state, settings, parent, curve, starts, stops, 1, uniform=True
        )
        arcs.append(arc)
        xy.append(curve.position([arc])[0, :2])
    rng = state.streams.keyed(
        "daughter_placement.sparse_balance", "1", settings.parent_order
    )
    selected, diagnostics = _balanced_cell_selection(
        xy, count, settings.spatial_cell_width_cm, rng
    )
    diagnostics["deep_eligible_parents"] = len(candidates)
    return ((candidates[i], arcs[i]) for i in selected), diagnostics


def _sparse_recruitment(state, settings, parents):
    eligible, deep, deep_candidates = [], [], []
    balanced = settings.mode == "sparse_depth_balanced"
    surface = state.laws.surface_z_cm
    for parent, curve, starts, stops, _ in _terminal_support(state, parents):
        if not len(starts):
            continue
        oid = parent.axis_state.biological_id
        draw = state.streams.keyed(
            "daughter_placement.sparse_activation", "1", oid
        ).random()
        lo, hi = _deep_intervals(curve, starts, stops, surface - 90.0)
        eligible.append((oid, parent, curve, starts, stops))
        if len(lo):
            candidate = (oid, parent, curve, lo, hi)
            if balanced:
                deep_candidates.append(candidate)
            if draw < settings.strength:
                deep.append(candidate)
    # Every sparse arm uses the same realized count, with one birth per selected parent.
    diagnostics = dict(
        all_depth_eligible_parents=len(eligible), deep_activated_parents=len(deep)
    )
    if balanced:
        placements, coverage = _balanced_sparse_sites(
            state, settings, deep_candidates, len(deep)
        )
        diagnostics.update(coverage)
    else:
        chosen = deep
        if settings.mode == "sparse_uniform":

            def priority(item):
                return state.streams.keyed(
                    "daughter_placement.sparse_uniform_rank", "1", item[0]
                ).random()

            chosen = sorted(eligible, key=priority)[: len(deep)]
        placements = (
            (item, _sample_sites(state, settings, *item[1:], 1, uniform=True)[0])
            for item in chosen
        )
    records = []
    for (_, parent, curve, starts, stops), arc in placements:
        result = dict(
            parent_id=parent.axis_state.biological_id,
            eligible_cm=float((stops - starts).sum()),
            births=[],
        )
        _new_daughters(state, parent, curve, [arc], result)
        records.append(result)
    return dict(parents=records, **diagnostics)


def _retention(state, settings, parents):
    from scipy.optimize import brentq
    from scipy.special import expit, logit

    candidates, positions, records = [], [], []
    for parent in parents:
        curve = state.curves.get(parent.axis_state.biological_id)
        if curve is None or parent.invalid_root:
            continue
        arcs = {
            id(node): arc for node, arc in zip(parent.segments, curve.construction_arcs)
        }
        for child in parent.child_organs:
            arc = arcs[id(child.parent_node)]
            candidates.append(child)
            positions.append(curve.position([arc])[0])
            records.append(_birth(state, parent, curve, child, arc))
    if not candidates:
        return records
    weights = _weights(
        settings, np.asarray(positions), state.laws.surface_z_cm, _crown_xy(state)
    )
    logits = logit(0.85) + np.log(weights)
    shift = (
        brentq(lambda a: expit(logits + a).mean() - 0.85, -2, 2)
        if settings.strength
        else 0.0
    )
    probabilities = expit(logits + shift)
    removed = []
    for child, record, probability in zip(candidates, records, probabilities):
        rng = state.streams.keyed(
            "daughter_placement.retention", "1", child.axis_state.biological_id
        )
        kept = rng.uniform() < probability
        record.update(probability=float(probability), kept=bool(kept))
        if not kept:
            removed.append(child)
    _discard(state, settings.parent_order, removed)
    return records


def apply_terminal_preference(state, settings):
    order = settings.parent_order
    threshold = state.parameters.min_branching_diameter_cm
    parents = state.simulation.organs.get(order, [])
    state.simulation.organs.setdefault(order + 1, [])
    receipt = dict(
        settings=settings.model_dump(exclude_none=True),
        minimum_parent_diameter_cm=threshold,
    )
    state.diagnostics["daughter_placement"] = receipt
    if settings.mode == "retention":
        receipt["retentions"] = _retention(state, settings, parents)
        return
    if settings.mode.startswith("branch_probability"):
        receipt.update(_branch_probability(state, settings, parents))
        return
    if settings.mode.startswith("sparse_"):
        receipt.update(_sparse_recruitment(state, settings, parents))
        return
    records = []
    for parent in parents:
        curve = state.curves.get(parent.axis_state.biological_id)
        if curve is not None and not parent.invalid_root:
            records.append(_place_parent(state, settings, parent, curve, threshold))
    receipt["parents"] = records

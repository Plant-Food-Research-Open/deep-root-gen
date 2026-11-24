"""Inverse placement fit to training-core projections and a mean mass response."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import LinearConstraint, linprog, minimize

from .core_placement_cost import (
    _depth_projection,
    _tube_weights,
    score_core_placement,
)


# At a knot the four signed cosine corners are an orthogonal linear transform
# of [intercept, across, along, across*along]. Between corners and depth knots
# the field is a convex combination of the respective corner values.
_CORNERS = np.array([[1, x, y, x * y] for x in (-1, 1) for y in (-1, 1)])
_FEASIBILITY_TOL = 1e-8


def _mass_extreme(direction, section_design, section_offsets):
    """Minimize a linear mass direction on the bounded physical response."""
    if not np.any(direction) or len(section_offsets) == 0:
        return -np.sign(direction)
    result = linprog(
        direction,
        A_ub=-section_design,
        b_ub=section_offsets,
        bounds=(-1.0, 1.0),
        method="highs",
        options={
            "primal_feasibility_tolerance": 1e-10,
            "dual_feasibility_tolerance": 1e-10,
        },
    )
    if not result.success:
        raise RuntimeError(
            "Could not establish the achievable mass range: " + result.message
        )
    return result.x


def _physical_gradient(
    predicted, observed, weights, mean, cap, observed_share, depth_projection
):
    """Training score and one subgradient with respect to the section RLD."""
    # SLSQP can evaluate outside its linearized constraints on a trial step.
    physical = np.maximum(predicted, 0)
    residual = physical - observed
    error = np.abs(residual)
    magnitude = error if cap is None else np.minimum(error, cap)
    loss = 0.5 * (weights @ magnitude) / mean
    gradient = 0.5 * weights * np.sign(residual) / mean
    if cap is not None:
        gradient[error > cap] = 0
    weighted = weights * physical
    total = weighted.sum()
    if total == 0:
        # A positive observed mean is required by score_core_placement.
        loss += 0.5
    else:
        share = weighted / total
        difference = share - observed_share
        by_depth = depth_projection.shares_by_depth(difference)
        loss += 0.125 * (np.abs(difference).sum() + np.abs(by_depth).sum())
        signs = np.sign(difference) + depth_projection.gradient_by_section(
            np.sign(by_depth)
        )
        gradient += 0.125 * weights * (signs - share @ signs) / total
    gradient[predicted < 0] = 0
    return loss, gradient


def _mass_constraints(
    corner_mass, limited_design, limited_offset, mass_offset_kg, bounds
):
    """Construct physical constraints and a feasible starting corner field."""
    low = _mass_extreme(corner_mass, limited_design, limited_offset)
    high = _mass_extreme(-corner_mass, limited_design, limited_offset)
    attainable = mass_offset_kg + np.array(
        [corner_mass @ low, corner_mass @ high]
    )
    start = np.zeros_like(corner_mass)
    constraints = []
    if len(limited_offset):
        constraints.append(
            LinearConstraint(limited_design, -limited_offset, np.inf)
        )
    if bounds is None:
        return constraints, start, "not_requested", attainable
    lower, upper = bounds
    lo, hi = max(lower, attainable[0]), min(upper, attainable[1])
    if lo > hi + _FEASIBILITY_TOL:
        return constraints, start, "infeasible", attainable

    target = np.clip(mass_offset_kg, lo, hi)
    if target != mass_offset_kg:
        endpoint = high if target > mass_offset_kg else low
        delta = corner_mass @ endpoint
        if delta != 0:
            start = endpoint * np.clip((target - mass_offset_kg) / delta, 0, 1)
    if np.any(corner_mass) and (
        lower > attainable[0] or upper < attainable[1]
    ):
        constraints.append(
            LinearConstraint(
                corner_mass, lower - mass_offset_kg, upper - mass_offset_kg
            )
        )
    return constraints, start, "enforced", attainable


def _plateau_start(start, design, residual, weights, constraints):
    """Probe a flat capped objective along a feasible training LS direction."""
    root_weights = np.sqrt(weights)
    delta = np.linalg.lstsq(
        root_weights[:, None] * design, root_weights * residual, rcond=None
    )[0]
    delta = np.clip(start + delta, -1, 1) - start
    step = 1.0
    for constraint in constraints:
        movement = constraint.A @ delta
        location = constraint.A @ start
        # Divide only nonzero movements, with the boundary in their direction.
        moving = movement != 0
        limits = np.where(movement > 0, constraint.ub, constraint.lb)
        bounds = (limits[moving] - location[moving]) / movement[moving]
        step = min(step, np.min(bounds, initial=1.0))
    return start + np.clip(step, 0, 1) * delta


def _response_arrays(training_index, design, mass_gradient_kg, mass_offset_kg):
    if isinstance(design, pd.DataFrame):
        if not design.index.equals(training_index):
            raise ValueError(
                "Response design index must match training rows in order"
            )
        if isinstance(
            mass_gradient_kg, pd.Series
        ) and not mass_gradient_kg.index.equals(design.columns):
            raise ValueError(
                "Mass gradient index must match response design columns in order"
            )
    design = np.asarray(design, dtype=float)
    gradient = np.asarray(mass_gradient_kg, dtype=float)
    if (
        design.ndim != 2
        or design.shape[0] != len(training_index)
        or design.shape[1] < 8
        or design.shape[1] % 4
        or gradient.shape != (design.shape[1],)
    ):
        raise ValueError(
            "Expected a section-by-(4 * knots) design and matching mass gradient"
        )
    if (
        not np.isfinite(design).all()
        or not np.isfinite(gradient).all()
        or not np.isfinite(mass_offset_kg)
    ):
        raise ValueError(
            "Physical response and mass parameters must be finite"
        )
    return design, gradient


def _training_response_ranks(design, weights):
    """Numerical response rank on weighted training rows, before penalties."""
    weighted = np.sqrt(weights)[:, None] * design
    depth = weighted[:, ::4]
    horizontal = weighted.reshape(len(weights), -1, 4)[:, :, 1:].reshape(
        len(weights), -1
    )
    tolerance = (
        np.finfo(float).eps
        * max(weighted.shape)
        * np.linalg.norm(weighted, ord=2)
    )
    left, singular, _ = np.linalg.svd(depth, full_matrices=False)
    depth_basis = left[:, singular > tolerance]
    residual = horizontal - depth_basis @ (depth_basis.T @ horizontal)
    horizontal_singular = np.linalg.svd(residual, compute_uv=False)
    return {
        "depth_response_rank": int(depth_basis.shape[1]),
        "horizontal_residual_rank": int(
            np.count_nonzero(horizontal_singular > tolerance)
        ),
        "horizontal_column_count": int(horizontal.shape[1]),
        "response_rank_tolerance": float(tolerance),
    }


def fit_core_response_surface(
    training: pd.DataFrame,
    offset,
    design,
    mass_offset_kg,
    mass_gradient_kg,
    *,
    top30_weight: float = 1.0,
    cap_multiple: float | None = None,
    horizontal_penalty: float = 0.02,
    depth_penalty: float = 0.05,
    mass_bounds_kg: tuple[float, float] | None = (6.0, 8.0),
    maxiter: int = 250,
) -> dict:
    """Fit coefficients to an affine training projection using constrained SLSQP.

    Rows match training in order. Columns are knot-major groups of four:
    [intercept, cos(across), cos(along), product]. Both response arrays use
    the same basis. All inputs, including the mean mass response, must be
    constructed by the caller from the training design. The physical loss
    uses score_core_placement's tube weights, MAE normalization and two TVs.

    The objective adds horizontal_penalty times summed squared horizontal
    coefficients and depth_penalty times summed squared adjacent-knot
    differences. The bounded field keeps every knot/cosine corner in [-1,1].
    Section predictions must be nonnegative. A feasible mass interval is
    enforced; an impossible interval is reported and omitted from the solve.
    SLSQP seeks a local solution. The best feasible iterate is retained even
    if the iteration limit is reached; optimizer convergence is reported.
    """
    if (
        min(horizontal_penalty, depth_penalty) < 0
        or not np.isfinite([horizontal_penalty, depth_penalty]).all()
    ):
        raise ValueError("Penalties must be finite and nonnegative")
    if not isinstance(maxiter, (int, np.integer)) or maxiter <= 0:
        raise ValueError("maxiter must be a positive integer")
    baseline = score_core_placement(
        training,
        training,
        offset,
        top30_weight=top30_weight,
        cap_multiple=cap_multiple,
    )
    design, gradient = _response_arrays(
        training.index, design, mass_gradient_kg, mass_offset_kg
    )
    offset = np.asarray(offset, dtype=float)
    if mass_bounds_kg is not None:
        if (
            np.shape(mass_bounds_kg) != (2,)
            or not np.isfinite(mass_bounds_kg).all()
            or mass_bounds_kg[0] > mass_bounds_kg[1]
        ):
            raise ValueError("Expected ordered finite mass bounds in kg")
    n_coefficients = design.shape[1]
    corner_design = (
        design.reshape(len(training), -1, 4) @ _CORNERS.T / 4
    ).reshape(-1, n_coefficients)
    corner_mass = (gradient.reshape(-1, 4) @ _CORNERS.T / 4).ravel()
    # A row whose minimum over the full corner box is nonnegative needs no
    # extra inequality in the optimizer or mass range linear programs.
    needs_bound = offset < np.abs(corner_design).sum(axis=1)
    limited_design, limited_offset = (
        corner_design[needs_bound],
        offset[needs_bound],
    )
    constraints, start, mass_status, attainable = _mass_constraints(
        corner_mass,
        limited_design,
        limited_offset,
        mass_offset_kg,
        mass_bounds_kg,
    )
    lower, upper = (
        mass_bounds_kg if mass_bounds_kg is not None else (-np.inf, np.inf)
    )
    weights = _tube_weights(training, top30_weight)
    observed = training["rld_est"].to_numpy(dtype=float)
    mean, cap = baseline["training_mean_rld"], baseline["cap_rld"]
    observed_share = weights * observed / mean
    depth_projection = _depth_projection(training, top30_weight)

    def objective(corners):
        coefs = corners.reshape(-1, 4) @ _CORNERS / 4
        predicted = offset + corner_design @ corners
        loss, section_gradient = _physical_gradient(
            predicted,
            observed,
            weights,
            mean,
            cap,
            observed_share,
            depth_projection,
        )
        differences = np.diff(coefs, axis=0)
        loss += (
            horizontal_penalty * np.square(coefs[:, 1:]).sum()
            + depth_penalty * np.square(differences).sum()
        )
        penalty_gradient = np.zeros_like(coefs)
        penalty_gradient[:, 1:] = 2 * horizontal_penalty * coefs[:, 1:]
        penalty_gradient[:-1] -= 2 * depth_penalty * differences
        penalty_gradient[1:] += 2 * depth_penalty * differences
        return (
            float(loss),
            section_gradient @ corner_design
            + (penalty_gradient @ _CORNERS.T / 4).ravel(),
        )

    # On a capped plateau SLSQP can terminate at a completely empty profile.
    # Try a feasible direction from the training responses, accepting it only
    # if the actual regularized physical objective improves.
    start_value, start_gradient = objective(start)
    if cap is not None and np.max(np.abs(start_gradient)) < 1e-12:
        residual = observed - (offset + corner_design @ start)
        probe = _plateau_start(
            start, corner_design, residual, weights, constraints
        )
        if objective(probe)[0] < start_value:
            start = probe
    best = start.copy()
    best_objective = objective(best)[0]

    def keep_feasible(proposal):
        nonlocal best, best_objective
        if not np.isfinite(proposal).all():
            return
        candidate = np.clip(proposal, -1, 1)
        if np.any(
            limited_offset + limited_design @ candidate < -_FEASIBILITY_TOL
        ):
            return
        mass = mass_offset_kg + corner_mass @ candidate
        if (
            mass_status == "enforced"
            and not lower - _FEASIBILITY_TOL
            <= mass
            <= upper + _FEASIBILITY_TOL
        ):
            return
        value = objective(candidate)[0]
        if value < best_objective:
            best, best_objective = candidate, value

    fitted = minimize(
        objective,
        start,
        method="SLSQP",
        jac=True,
        bounds=[(-1, 1)] * n_coefficients,
        constraints=constraints,
        callback=keep_feasible,
        options={"ftol": 1e-10, "maxiter": maxiter},
    )
    keep_feasible(fitted.x)
    coefficients = best.reshape(-1, 4) @ _CORNERS / 4
    predicted = offset + design @ coefficients.ravel()
    mass = float(mass_offset_kg + gradient @ coefficients.ravel())
    if np.min(predicted) < -_FEASIBILITY_TOL or (
        mass_status == "enforced"
        and not lower - _FEASIBILITY_TOL <= mass <= upper + _FEASIBILITY_TOL
    ):
        raise RuntimeError("Unable to return a feasible physical response")
    score = score_core_placement(
        training,
        training,
        np.maximum(predicted, 0),
        top30_weight=top30_weight,
        cap_multiple=cap_multiple,
    )
    return {
        "coefficients": coefficients.tolist(),
        "loss": score["loss"],
        "score": score,
        "objective": best_objective,
        "predicted_mass_kg": mass,
        "mass_status": mass_status,
        "attainable_mass_range_kg": attainable.tolist(),
        "within_mass_bounds": (
            None
            if mass_bounds_kg is None
            else bool(
                lower - _FEASIBILITY_TOL <= mass <= upper + _FEASIBILITY_TOL
            )
        ),
        "success": bool(fitted.success),
        "message": str(fitted.message),
        "iterations": int(fitted.nit),
        "optimizer_status": int(fitted.status),
        "max_abs_corner": float(np.max(np.abs(best))),
        "min_predicted_section_rld": float(predicted.min()),
        "feasibility_tolerance": _FEASIBILITY_TOL,
        **_training_response_ranks(design, weights),
    }

"""Opt-in rotation of attached lateral subtrees about the realized parent tangent."""
import numpy as np
import pandas as pd
from scipy.special import softmax
from scipy.stats import qmc


ANGLES_DEG = (0, 60, -60, 120, -120, 180)
PARAMETERS = ("turn", "width", "birth_depth", "shallow", "middle", "deep", "crowding", "surface")


def lateral_orientation_design(seed=914106):
    """Cross two primary scaffolds and lateral orders 2 and 3 with 1,250 rules.

    On each background the ten fixed controls precede 1,240 Latin-hypercube
    draws. Every fifth draw disables the coring surface for paired generic
    inference. Scaffold 0 uses original primary bearings. Scaffold 1 uses
    randomized primary bearings and weak avoidance of crowded soil by growing
    terminals. The first 1,250 rows target second order on scaffold 0.
    """
    anchors = np.zeros((10, len(PARAMETERS)))
    anchors[0, 0] = -1000  # Hold the existing orientation.
    anchors[2, 0] = -2
    anchors[3, 1] = -2
    anchors[4, 2] = 2
    anchors[5, 3] = -2
    anchors[6, 4] = 2
    anchors[7, 5] = 2
    anchors[8, 6] = -1.5
    anchors[9, 7] = 1.5
    draws = qmc.LatinHypercube(len(PARAMETERS), seed=seed).random(1240)
    draws = draws * 6 + [-4, -3, -3, -3, -3, -3, -3, -3]
    draws[::5, -1] = 0
    rows = np.vstack((anchors, draws))
    design = pd.DataFrame(np.tile(rows, (4, 1)), columns=PARAMETERS)
    design.insert(0, "order", np.repeat([2, 3, 2, 3], len(rows)))
    design.insert(0, "scaffold", np.repeat([0, 1], 2 * len(rows)))
    return design.rename_axis("design_id")


def roll_options(points, insertion, tangent, *, soil_z=0, tolerance=1e-8):
    """Rotate every supplied point of ONE complete subtree as a single body.

    All coordinates share length units. The tangent points in the direction
    of growth of the parent at the insertion. Elevation increases upwards.
    Return six point arrays in ANGLES_DEG order and a mask of whole-subtree
    feasibility. Illegal options retain their computed geometry for inspection
    and have zero probability under roll_probabilities.
    """
    xyz = np.asarray(points, dtype=float)
    origin = np.asarray(insertion, dtype=float)
    axis = np.asarray(tangent, dtype=float)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or not len(xyz):
        raise ValueError("Supply one or more three-dimensional subtree points")
    if origin.shape != (3,) or axis.shape != (3,):
        raise ValueError("Supply a three-dimensional insertion and parent tangent")
    if not all(np.isfinite(x).all() for x in (xyz, origin, axis, soil_z, tolerance)) or tolerance < 0:
        raise ValueError("Coordinates and soil limits must be finite and tolerance nonnegative")
    magnitude = np.linalg.norm(axis)
    if magnitude == 0 or not np.isfinite(magnitude):
        raise ValueError("The parent tangent must have a finite positive length")
    axis = axis / magnitude
    theta = np.deg2rad(ANGLES_DEG)[:, None, None]
    offset = xyz - origin
    along = (offset @ axis)[:, None] * axis
    curves = origin + np.cos(theta) * offset + np.sin(theta) * np.cross(axis, offset) + (1 - np.cos(theta)) * along
    curves[0] = xyz
    legal = curves[:, :, 2].max(axis=1) <= soil_z + tolerance
    if not legal[0]:
        raise ValueError("The original subtree must be below the soil surface")
    return curves, legal


def roll_probabilities(coefficients, birth_depth, deposition_contrasts, legal):
    """Return categorical probabilities for one physical lateral subtree.

    Supply an eight-vector in PARAMETERS order, scaled birth depth and a 6×5
    array of differences from the original course in shallow, middle, deep,
    crowding and relative coring-field deposition. The first angle is fixed.
    Each alternative receives one fifth of the prior odds of initiating a
    turn. Infeasible options are masked before probabilities are normalized.
    """
    beta = np.asarray(coefficients, dtype=float)
    delta = np.asarray(deposition_contrasts, dtype=float)
    valid = np.asarray(legal)
    if beta.shape != (8,) or delta.shape != (6, 5) or np.ndim(birth_depth) != 0:
        raise ValueError("Supply eight coefficients, one birth depth and six five-component contrasts")
    if valid.dtype != np.bool_ or valid.shape != (6,) or not valid[0]:
        raise ValueError("Supply a six-angle feasibility mask with a legal unchanged option")
    if not all(np.isfinite(x).all() for x in (delta, beta, birth_depth)):
        raise ValueError("Coefficients, birth depth and deposition contrasts must be finite")
    width = np.abs(ANGLES_DEG) / 180
    logits = beta[0] - np.log(5) + beta[1] * width + beta[2] * birth_depth + delta @ beta[3:]
    logits[0] = 0
    logits[~valid] = -np.inf
    return softmax(logits)

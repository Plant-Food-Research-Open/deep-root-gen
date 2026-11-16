"""Pure rigid primary-inclination geometry; no sampling or growth laws."""

import numpy as np


def _unit(vector):
    vector = np.asarray(vector, dtype=float)
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError("Primary direction must be a finite 3-vector")
    norm = np.linalg.norm(vector)
    if not np.isfinite(norm) or norm <= 1e-12:
        raise ValueError("Primary chord/direction is zero or degenerate")
    return vector / norm


def proper_rotation(source, target):
    """Shortest proper rotation, deterministic at parallel/antiparallel limits."""
    source, target = _unit(source), _unit(target)
    cross = np.cross(source, target)
    sine, cosine = np.linalg.norm(cross), float(np.clip(source @ target, -1., 1.))
    if sine <= 1e-12:
        if cosine > 0:
            return np.eye(3)
        axis = np.cross(source, np.eye(3)[np.argmin(np.abs(source))])
        axis /= np.linalg.norm(axis)
        return 2. * np.outer(axis, axis) - np.eye(3)
    axis = cross / sine
    angle = np.arctan2(sine, cosine)
    skew = np.array([[0., -axis[2], axis[1]], [axis[2], 0., -axis[0]], [-axis[1], axis[0], 0.]])
    return np.cos(angle) * np.eye(3) + (1. - np.cos(angle)) * np.outer(axis, axis) + np.sin(angle) * skew


def chord_angles(direction):
    direction = _unit(direction)
    return dict(inclination_down_deg=float(np.degrees(np.arcsin(np.clip(-direction[2], -1., 1.)))),
                azimuth_deg=(None if np.linalg.norm(direction[:2]) <= 1e-12
                             else float(np.degrees(np.arctan2(direction[1], direction[0])))))


def inclination_rotation(chord, bias):
    """Return R and diagnostics for unit(h + bias * (0,0,-1))."""
    if bias is None or not np.isfinite(bias) or not 0 <= bias <= 1:
        raise ValueError("Primary inclination bias must be finite in [0,1]")
    original = _unit(chord)
    target = _unit(original + np.array([0., 0., -float(bias)]))
    rotation = proper_rotation(original, target)
    if (not np.allclose(rotation.T @ rotation, np.eye(3), rtol=0, atol=1e-12)
            or not np.isclose(np.linalg.det(rotation), 1., rtol=0, atol=1e-12)
            or not np.allclose(rotation @ original, target, rtol=0, atol=1e-12)):
        raise ValueError("Primary rotation is not a proper target-preserving rotation")
    return rotation, dict(bias=float(bias), original_chord_unit=original.tolist(),
                          target_chord_unit=target.tolist(), original_angles=chord_angles(original),
                          target_angles=chord_angles(target), rotation=rotation.tolist())


def check_edge_conservation(original, proposed, parents, node_ids, base_id):
    """Validate a planned rigid subtree before any graph node is mutated."""
    old_lengths, new_lengths = [], []
    for node in node_ids:
        parent = parents[node]
        if parent not in node_ids and parent != base_id:
            raise ValueError("Primary subtree has an external parent attachment")
        old_lengths.append(np.linalg.norm(original[node] - original[parent]))
        new_lengths.append(np.linalg.norm(proposed[node] - proposed[parent]))
    if (not np.isfinite(new_lengths).all() or np.any(np.asarray(old_lengths) <= 0)
            or not np.allclose(old_lengths, new_lengths, rtol=1e-5, atol=1e-6)
            or not np.isclose(sum(old_lengths), sum(new_lengths), rtol=0, atol=1e-8)):
        raise ValueError("Primary subtree edge-length conservation failed")
    return float(np.max(np.abs(np.asarray(new_lengths) - old_lengths), initial=0.))

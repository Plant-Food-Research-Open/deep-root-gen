"""Compose generation input from the existing vineyard study's four sampling axes."""

from ..data_model.canonical import RootConfig


def vineyard_trial(
    *, random_seed, outer_root_num, inner_root_num, min_sec_root_num, max_sec_root_num,
    growth_sec_root, min_sec_root_length, max_sec_root_length, **parameters
):
    """Keep experimental group counts and exclusive daughter bounds in the study design."""
    values = (outer_root_num, inner_root_num, min_sec_root_num, max_sec_root_num)
    if any(type(v) is bool or int(v) != v for v in values):
        raise ValueError("Vineyard count coordinates must be integers")
    outer, inner, lo, hi = map(int, values)
    if min(outer, inner, lo) < 0 or outer + inner < 1 or hi < lo:
        raise ValueError("Invalid vineyard population or daughter bounds")
    return RootConfig(
        schema_version=4, random_seed=int(random_seed), parameters=dict(
            parameters, daughter_count_order_gain=growth_sec_root,
            min_lateral_length=min_sec_root_length, max_lateral_length=max_sec_root_length,
            primary_root_count=outer + inner, outer_primary_fraction=outer / (outer + inner),
            daughters_per_parent=lo if hi == lo else dict(min=lo, max_exclusive=hi),
        )
    )

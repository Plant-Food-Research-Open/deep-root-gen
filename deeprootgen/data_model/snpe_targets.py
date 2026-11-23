"""Build the conditioning vector expected by a trained summary SNPE model."""

from collections.abc import Iterable, Mapping, Sequence
from math import isfinite


def conditioning_rows(
    names: Sequence[str], rows: Iterable[Mapping]
) -> list[dict]:
    """Return one finite value per required statistic in training order."""
    if not names:
        raise ValueError("The served model has no conditioning schema.")
    values = {}
    seen = set()
    required = set(names)
    for row in rows:
        name = row.get("statistic_name")
        if not isinstance(name, str) or name not in required:
            continue
        if name in seen:
            raise ValueError(f"Supply exactly one value for {name}.")
        seen.add(name)
        value = row.get("statistic_value")
        if value is None:
            continue
        try:
            if isinstance(value, bool):
                raise ValueError()
            value = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Enter a finite numeric value for {name}.") from exc
        if not isfinite(value):
            raise ValueError(f"Enter a finite numeric value for {name}.")
        values[name] = value

    missing = [name for name in names if name not in values]
    if missing:
        raise ValueError(f"Supply a value for {', '.join(missing)}.")
    return [
        {"statistic_name": name, "statistic_value": values[name]}
        for name in names
    ]

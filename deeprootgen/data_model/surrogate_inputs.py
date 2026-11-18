"""Prediction inputs use the numeric columns recorded when a surrogate was trained."""

import json
import math
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class SurrogateFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: list[dict[str, Any]] = Field(min_length=1)

    def feature_frame(self, dtypes):
        """Project each complete request row into the trained order and numeric types."""
        columns = {}
        for name, dtype in dtypes.items():
            values = []
            for i, row in enumerate(self.data, start=1):
                if name not in row:
                    raise ValueError(f"Row {i} is missing trained feature {name!r}")
                value = row[name]
                if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
                    raise ValueError(f"Row {i} feature {name!r} requires a finite number")
                if dtype.kind in "iu":
                    limits = np.iinfo(dtype)
                    if value != int(value) or not limits.min <= int(value) <= limits.max:
                        raise ValueError(f"Row {i} feature {name!r} requires an integer in {dtype} range")
                elif abs(value) > float(np.finfo(dtype).max):
                    raise ValueError(f"Row {i} feature {name!r} exceeds {dtype} range")
                values.append(value)
            columns[name] = np.asarray(values, dtype=dtype)
        return pd.DataFrame(columns)


def surrogate_form_row(children, values):
    """An explicit row can supply the trained names of a historical model."""
    row = dict(zip((child["param"] for child in children), values, strict=True))
    explicit = row.pop("trained_features_json", None)
    if not explicit:
        return {k: v for k, v in row.items() if v is not None}
    row = json.loads(explicit)
    if not isinstance(row, dict) or not row:
        raise ValueError("Trained features must be a JSON object with feature names and values")
    return row

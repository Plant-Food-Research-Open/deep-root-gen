"""Serve accepted particles from the latest ABC calibrator."""

import pandas as pd
from bentoml.exceptions import BadInput
from bentoml.io import JSON, PandasDataFrame
from pydantic import BaseModel, Field

from deeprootgen.serving import load, require, service

TASK = "abc"
model, missing = load(TASK)
svc, runner = service(TASK, model)


class AbcFeatures(BaseModel):
    """Sequential Monte Carlo populations; -1 returns all populations."""

    t: list[int] = Field(min_length=1)


@svc.api(input=JSON(pydantic_model=AbcFeatures), output=PandasDataFrame())
def predict(inputs: AbcFeatures) -> pd.DataFrame:
    """Return particle rows for the requested populations."""
    result = require(runner, missing).predict.run(pd.DataFrame({"t": inputs.t}))
    if len(result) == 0:
        raise BadInput(f"The served {TASK} model has no accepted population t={inputs.t}")
    return result

"""Serve the best stored trials of the latest optimisation calibrator."""

import pandas as pd
from bentoml.io import JSON, PandasDataFrame
from pydantic import BaseModel, Field

from deeprootgen.serving import load, require, service

TASK = "optimisation"
model, missing = load(TASK)
svc, runner = service(TASK, model)


class OptimisationFeatures(BaseModel):
    """The number of best trials to return."""

    n_trials: int = Field(ge=1)


@svc.api(input=JSON(pydantic_model=OptimisationFeatures), output=PandasDataFrame())
def predict(inputs: OptimisationFeatures) -> pd.DataFrame:
    """Return the ``n_trials`` lowest-objective trials."""
    return require(runner, missing).predict.run(pd.DataFrame({"n_trials": [inputs.n_trials]}))

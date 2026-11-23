"""Serve total-order Sobol indices from the latest sensitivity analysis."""

import pandas as pd
from bentoml.exceptions import BadInput
from bentoml.io import JSON, PandasDataFrame
from pydantic import BaseModel, Field

from deeprootgen.serving import load, require, service

TASK = "sensitivity_analysis"
model, missing = load(TASK)
svc, runner = service(TASK, model)


class SensitivityAnalysisFeatures(BaseModel):
    """Parameter names whose indices are requested."""

    names: list[str] = Field(min_length=1)


@svc.api(input=JSON(pydantic_model=SensitivityAnalysisFeatures), output=PandasDataFrame())
def predict(inputs: SensitivityAnalysisFeatures) -> pd.DataFrame:
    """Return the total-order index rows for the requested parameter names."""
    result = require(runner, missing).predict.run(pd.DataFrame({"name": inputs.names}))
    if len(result) == 0:
        raise BadInput(f"The served {TASK} model has no index for: {', '.join(inputs.names)}")
    return result

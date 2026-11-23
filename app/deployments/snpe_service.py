"""Serve posterior draws from the latest summary-statistic SNPE model."""

from typing import List

import bentoml
import pandas as pd
from bentoml.exceptions import BadInput
from bentoml.io import JSON, PandasDataFrame
from mlflow.models import Model
from pydantic import BaseModel, Field

from deeprootgen.data_model import SummaryStatisticsModel
from deeprootgen.serving import Unsupported, load, require, service

TASK = "snpe"
model, missing = load(TASK)
svc, runner = service(TASK, model)
inference_type = None
if model is not None:
    flavor = Model.load(model.path_of(bentoml.mlflow.MLFLOW_MODEL_FOLDER)).flavors["python_function"]
    # MLflow 2.x stores the pyfunc model_config under "config".
    inference_type = (flavor.get("config") or flavor.get("model_config") or {}).get("inference_type")


class SnpeFeatures(BaseModel):
    """Observed summary statistics to condition the posterior on."""

    summary_statistics: List[SummaryStatisticsModel] = Field(min_length=1)


@svc.api(input=JSON(pydantic_model=SnpeFeatures), output=PandasDataFrame())
def predict(inputs: SnpeFeatures) -> pd.DataFrame:
    """Return posterior draws conditional on the observed statistics."""
    served = require(runner, missing)
    if inference_type != "summary_statistics":
        raise Unsupported(
            f"The served {TASK} model was trained with inference type '{inference_type}'. "
            "Serving implements summary-statistic posteriors only; graph-mode inference is not served."
        )
    frame = pd.DataFrame([statistic.model_dump() for statistic in inputs.summary_statistics])
    result = served.predict.run(frame)
    if len(result) == 0:
        raise BadInput("None of the supplied statistic names match the served model's statistics.")
    return result

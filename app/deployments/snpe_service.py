"""Serve posterior draws from the latest summary-statistic SNPE model."""

from pathlib import Path
from pickle import UnpicklingError
from typing import List

import bentoml
import joblib
import pandas as pd
from bentoml.exceptions import BadInput
from bentoml.io import JSON, PandasDataFrame
from mlflow.models import Model
from pydantic import BaseModel, Field

from deeprootgen.data_model import SummaryStatisticsModel
from deeprootgen.data_model.snpe_targets import conditioning_rows
from deeprootgen.serving import Unsupported, load, require, service

TASK = "snpe"


def read_prediction_info(model_dir: Path) -> dict:
    """Read the ordered statistic names from the model's saved training data."""
    unavailable = {"prediction_ready": False}
    try:
        flavor = Model.load(str(model_dir)).flavors["python_function"]
        config = flavor.get("config") or flavor.get("model_config") or {}
        inference_type = config.get("inference_type")
        if inference_type != "summary_statistics":
            return {
                **unavailable,
                "prediction_detail": f"The served model uses '{inference_type}'. "
                "SNPE serving supports summary-statistic models only.",
            }
        artifact = flavor["artifacts"]["statistics_list"]["path"]
        rows = joblib.load(model_dir / artifact)
        names = list(dict.fromkeys(row["statistic_name"] for row in rows))
        if not names or any(not isinstance(name, str) or not name for name in names):
            raise ValueError("Invalid statistic names")
    except (OSError, KeyError, TypeError, ValueError, EOFError, UnpicklingError):
        return {
            **unavailable,
            "prediction_detail": "The served SNPE model has no readable statistic schema.",
        }
    return {"prediction_ready": True, "input_schema": {"statistic_names": names}}


model, missing = load(TASK)
prediction_info = (
    read_prediction_info(Path(model.path_of(bentoml.mlflow.MLFLOW_MODEL_FOLDER)))
    if model is not None
    else {"prediction_ready": False, "prediction_detail": missing}
)
svc, runner = service(TASK, model, prediction_info=prediction_info)


class SnpeFeatures(BaseModel):
    """Observed summary statistics to condition the posterior on."""

    summary_statistics: List[SummaryStatisticsModel] = Field(min_length=1)
    expected_model_tag: str | None = Field(default=None, alias="model_tag")


@svc.api(input=JSON(pydantic_model=SnpeFeatures), output=PandasDataFrame())
def predict(inputs: SnpeFeatures) -> pd.DataFrame:
    """Return posterior draws conditional on the observed statistics."""
    served = require(runner, missing)
    if not prediction_info["prediction_ready"]:
        raise Unsupported(prediction_info["prediction_detail"])
    if inputs.expected_model_tag is not None and inputs.expected_model_tag != str(model.tag):
        raise BadInput("The served model changed. Refresh model services and review the targets.")
    names = prediction_info["input_schema"]["statistic_names"]
    supplied = [statistic.model_dump() for statistic in inputs.summary_statistics]
    try:
        rows = conditioning_rows(names, supplied)
    except ValueError as exc:
        raise BadInput(str(exc)) from exc
    rows_by_name = {statistic["statistic_name"]: statistic for statistic in supplied}
    frame = pd.DataFrame([rows_by_name[row["statistic_name"]] for row in rows])
    result = served.predict.run(frame)
    if result.empty:
        raise BadInput("The served SNPE model returned no posterior draws for these targets.")
    return result

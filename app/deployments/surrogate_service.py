"""Serve the numeric feature signature bundled with the selected surrogate."""

import bentoml
import pandas as pd
from bentoml.exceptions import BadInput
from bentoml.io import JSON, PandasDataFrame
from mlflow.models import Model

from deeprootgen.data_model.surrogate_inputs import SurrogateFeatures
from deeprootgen.serving import load, require, service

TASK = "surrogate"
model, missing = load(TASK)
feature_types = {}
if model is not None:
    schema = Model.load(model.path_of(bentoml.mlflow.MLFLOW_MODEL_FOLDER)).get_input_schema()
    if schema is None or not schema.has_input_names() or schema.is_tensor_spec():
        model, missing = None, f"Surrogate {model.tag} has no named numeric training signature; retrain it."
    else:
        feature_types = dict(zip(schema.input_names(), schema.numpy_types(), strict=True))
        if any(dtype.kind not in "iuf" for dtype in feature_types.values()):
            model, missing = None, f"Surrogate {model.tag} has a nonnumeric feature in its training signature."
svc, runner = service(TASK, model)


@svc.api(input=JSON(pydantic_model=SurrogateFeatures), output=PandasDataFrame())
def predict(inputs: SurrogateFeatures) -> pd.DataFrame:
    """Predict with the feature names and column order of the loaded model."""
    served = require(runner, missing)
    try:
        frame = inputs.feature_frame(feature_types)
    except ValueError as exc:
        raise BadInput(f"Surrogate {model.tag}: {exc}") from exc
    return served.predict.run(frame)

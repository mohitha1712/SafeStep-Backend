
from pathlib import Path

import joblib
import pandas as pd

MODEL_PATH = Path(__file__).resolve().parent / "safestep_surface_model.pkl"

_model = None


def load_model():
    global _model

    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                "Random Forest model not found: " + str(MODEL_PATH)
            )

        _model = joblib.load(MODEL_PATH)

    return _model


def predict_surface(moisture_raw, moisture_percent):
    model = load_model()

    readings = pd.DataFrame(
        [{
            "moisture_raw": float(moisture_raw),
            "moisture_percent": float(moisture_percent),
        }],
        columns=["moisture_raw", "moisture_percent"],
    )

    prediction = model.predict(readings)[0]
    probabilities = model.predict_proba(readings)[0]

    confidence = float(max(probabilities)) * 100

    return {
        "surface": str(prediction),
        "confidence_percent": round(confidence, 2),
    }

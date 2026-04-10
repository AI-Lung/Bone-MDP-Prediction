from __future__ import annotations

import math


def standardize_features(feature_values: dict[str, float], scaling: dict[str, dict[str, float]]) -> dict[str, float]:
    standardized: dict[str, float] = {}
    for name, value in feature_values.items():
        params = scaling[name]
        scale = params["scale"]
        if scale == 0:
            standardized[name] = 0.0
        else:
            standardized[name] = (float(value) - float(params["mean"])) / float(scale)
    return standardized


def compute_linear_score(values: dict[str, float], weights: dict[str, float], intercept: float = 0.0) -> float:
    score = float(intercept)
    for name, weight in weights.items():
        score += float(values[name]) * float(weight)
    return score


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def compute_diagnostic_probability(age: float, acquisition_view: int, radscore: float, model: dict) -> float:
    linear_term = (
        float(model["intercept"])
        + float(model["weights"]["Age"]) * float(age)
        + float(model["weights"]["Acquisition_view"]) * float(acquisition_view)
        + float(model["weights"]["Radscore"]) * float(radscore)
    )
    return sigmoid(linear_term)


def compute_total_points(age: float, acquisition_view: int, radscore: float, point_formula: dict) -> float:
    return (
        float(point_formula["Intercept"])
        + float(point_formula["Age"]) * float(age)
        + float(point_formula["Acquisition_view"]) * float(acquisition_view)
        + float(point_formula["Radscore"]) * float(radscore)
    )


def compute_radscore_contributions(standardized_features: dict[str, float], weights: dict[str, float]) -> list[dict]:
    rows = []
    for name, value in standardized_features.items():
        weight = float(weights[name])
        rows.append(
            {
                "Feature": name,
                "Standardized value": float(value),
                "Weight": weight,
                "Contribution": float(value) * weight,
            }
        )
    rows.sort(key=lambda item: abs(item["Contribution"]), reverse=True)
    return rows


def compute_diagnostic_contributions(age: float, acquisition_view: int, radscore: float, model: dict) -> list[dict]:
    rows = [
        {
            "Predictor": "Age",
            "Value": float(age),
            "Weight": float(model["weights"]["Age"]),
            "Contribution": float(age) * float(model["weights"]["Age"]),
        },
        {
            "Predictor": "Acquisition_view",
            "Value": float(acquisition_view),
            "Weight": float(model["weights"]["Acquisition_view"]),
            "Contribution": float(acquisition_view) * float(model["weights"]["Acquisition_view"]),
        },
        {
            "Predictor": "Radscore",
            "Value": float(radscore),
            "Weight": float(model["weights"]["Radscore"]),
            "Contribution": float(radscore) * float(model["weights"]["Radscore"]),
        },
    ]
    rows.sort(key=lambda item: abs(item["Contribution"]), reverse=True)
    return rows


def classify_probability(probability: float, threshold: float) -> str:
    return "Malignant / Bone metastasis" if probability >= threshold else "Benign lesion"


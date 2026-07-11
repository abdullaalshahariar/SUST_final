"""Train a context-aware model for unexpected agent monthly volume changes."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from seasonal_ml import (  # noqa: E402
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    load_monthly_history,
    model_input,
    score_monthly_history,
)


SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPTS_DIR / "agent_monthly_history.csv"
DEFAULT_MODEL = SCRIPTS_DIR / "seasonal_volume_model.joblib"
DEFAULT_THRESHOLD = SCRIPTS_DIR / "seasonal_volume_threshold.json"
DEFAULT_SCORES = SCRIPTS_DIR / "seasonal_volume_scores.csv"


def make_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
            ("numeric", "passthrough", NUMERIC_FEATURES),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=400,
                    min_samples_leaf=2,
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def train(
    input_path: Path,
    model_path: Path,
    threshold_path: Path,
    scores_path: Path,
) -> dict[str, float | int]:
    history = load_monthly_history(input_path)
    normal_history = history[history["is_injected_anomaly"] == 0].copy()
    train_history, validation_history = train_test_split(
        normal_history, test_size=0.25, random_state=42
    )
    pipeline = make_pipeline()
    pipeline.fit(model_input(train_history), train_history["monthly_volume"])

    validation_predictions = pipeline.predict(model_input(validation_history))
    validation_ratio = validation_history["monthly_volume"].to_numpy() / np.maximum(
        validation_predictions, 1.0
    )
    # The model learns that Eid is normally high. This threshold is based on
    # normal validation months, then bounded to avoid overly sensitive alerts.
    ratio_threshold = max(1.5, float(np.quantile(validation_ratio, 0.99)))

    artifact = {
        "pipeline": pipeline,
        "residual_ratio_threshold": ratio_threshold,
        "feature_columns": MODEL_FEATURES,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)

    scored = score_monthly_history(history, artifact)
    y_true = scored["is_injected_anomaly"].astype(int)
    y_pred = scored["requires_review"].astype(int)
    normal_eid = scored[
        (scored["event_context"] == "eid") & (scored["is_injected_anomaly"] == 0)
    ]

    metrics: dict[str, float | int] = {
        "history_rows": int(len(scored)),
        "normal_rows": int((y_true == 0).sum()),
        "injected_anomaly_rows": int((y_true == 1).sum()),
        "flagged_rows": int(y_pred.sum()),
        "true_positive_count": int(((y_true == 1) & (y_pred == 1)).sum()),
        "false_positive_count": int(((y_true == 0) & (y_pred == 1)).sum()),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "normal_eid_months": int(len(normal_eid)),
        "normal_eid_months_flagged": int(normal_eid["requires_review"].sum()),
        "validation_mean_absolute_error": round(
            float(mean_absolute_error(validation_history["monthly_volume"], validation_predictions)), 2
        ),
    }
    threshold_path.write_text(
        json.dumps(
            {
                "volume_ratio_threshold": ratio_threshold,
                "threshold_method": "max(1.5, 99th percentile of normal validation volume ratios)",
                "metrics": metrics,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    scored.to_csv(scores_path, index=False)
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train a seasonal, context-aware monthly volume model."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--threshold-output", type=Path, default=DEFAULT_THRESHOLD)
    parser.add_argument("--scores-output", type=Path, default=DEFAULT_SCORES)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    result = train(
        arguments.input,
        arguments.model_output,
        arguments.threshold_output,
        arguments.scores_output,
    )
    print(f"Model saved to: {arguments.model_output.resolve()}")
    print(f"Threshold saved to: {arguments.threshold_output.resolve()}")
    print(f"Scores saved to: {arguments.scores_output.resolve()}")
    for key, value in result.items():
        print(f"{key}: {value}")

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ml import (  # noqa: E402
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    build_feature_windows,
    load_transactions,
    model_input,
    score_feature_windows,
)


SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPTS_DIR / "scenario2_transactions.csv"
DEFAULT_MODEL = SCRIPTS_DIR / "isolation_forest.joblib"
DEFAULT_THRESHOLD = SCRIPTS_DIR / "anomaly_threshold.json"
DEFAULT_SCORES = SCRIPTS_DIR / "scenario2_window_scores.csv"
REVIEW_GATE = {
    "minimum_cash_out_count": 10,
    "minimum_similarity_ratio": 0.75,
}


def make_pipeline() -> Pipeline:
    """Create preprocessing plus Isolation Forest as one serializable pipeline."""
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "detector",
                IsolationForest(
                    n_estimators=200,
                    contamination="auto",
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
    transactions = load_transactions(input_path)
    windows = build_feature_windows(transactions)
    normal_windows = windows[windows["is_injected_anomaly"] == 0].copy()
    if len(normal_windows) < 20:
        raise ValueError("At least 20 normal feature windows are required for training.")

    train_windows, validation_windows = train_test_split(
        normal_windows,
        test_size=0.25,
        random_state=42,
    )
    pipeline = make_pipeline()
    pipeline.fit(model_input(train_windows))

    # The 99th percentile of held-out normal activity is the alert threshold.
    validation_scores = -pipeline.score_samples(model_input(validation_windows))
    threshold = float(np.quantile(validation_scores, 0.99))

    artifact = {
        "pipeline": pipeline,
        "threshold": threshold,
        "feature_columns": MODEL_FEATURES,
        "window_frequency": "10min",
        "review_gate": REVIEW_GATE,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path)

    scored_windows = score_feature_windows(windows, artifact)
    y_true = scored_windows["is_injected_anomaly"].astype(int)
    y_pred = scored_windows["requires_review"].astype(int)
    legitimate = scored_windows[scored_windows["scenario_label"] == "legitimate_surge"]

    metrics: dict[str, float | int] = {
        "window_count": int(len(scored_windows)),
        "normal_window_count": int((y_true == 0).sum()),
        "injected_anomaly_window_count": int((y_true == 1).sum()),
        "flagged_window_count": int(y_pred.sum()),
        "true_positive_count": int(((y_true == 1) & (y_pred == 1)).sum()),
        "false_positive_count": int(((y_true == 0) & (y_pred == 1)).sum()),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "legitimate_surge_count": int(len(legitimate)),
        "legitimate_surge_flag_count": int(legitimate["requires_review"].sum()),
    }
    threshold_payload = {
        "anomaly_threshold": threshold,
        "threshold_method": "99th percentile of held-out normal-window scores",
        "review_gate": REVIEW_GATE,
        "metrics": metrics,
    }
    threshold_path.write_text(json.dumps(threshold_payload, indent=2), encoding="utf-8")
    scored_windows.to_csv(scores_path, index=False)
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train and evaluate the Scenario 2 Isolation Forest model."
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
    print(f"Window scores saved to: {arguments.scores_output.resolve()}")
    for name, value in result.items():
        print(f"{name}: {value}")

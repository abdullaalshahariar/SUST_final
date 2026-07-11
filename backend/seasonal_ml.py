"""Context-aware monthly-volume anomaly model for Scenario 2.

Unlike the short-window Isolation Forest, this model predicts what a specific
agent/provider month's volume should be after considering seasonality. A large
Eid volume is therefore compared with other Eid volumes, not ordinary months.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


CATEGORICAL_FEATURES = ["agent_id", "provider_code", "location", "event_context"]
NUMERIC_FEATURES = ["month_number", "year_index"]
MODEL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
REQUIRED_HISTORY_COLUMNS = {
    "period_start",
    "agent_id",
    "provider_code",
    "location",
    "event_context",
    "month_number",
    "year_index",
    "monthly_volume",
}


def load_monthly_history(csv_path: str | Path) -> pd.DataFrame:
    """Load a synthetic monthly agent-volume history CSV."""
    history = pd.read_csv(csv_path)
    missing = REQUIRED_HISTORY_COLUMNS.difference(history.columns)
    if missing:
        raise ValueError(f"Monthly history is missing required columns: {sorted(missing)}")

    history["period_start"] = pd.to_datetime(history["period_start"], utc=True)
    history["monthly_volume"] = pd.to_numeric(history["monthly_volume"], errors="raise")
    if (history["monthly_volume"] <= 0).any():
        raise ValueError("Monthly volume must be positive.")
    if "is_injected_anomaly" not in history:
        history["is_injected_anomaly"] = 0
    history["is_injected_anomaly"] = pd.to_numeric(
        history["is_injected_anomaly"], errors="raise"
    ).astype(int)
    return history


def model_input(history: pd.DataFrame) -> pd.DataFrame:
    """Return only context features; never include volume or evaluation labels."""
    missing = set(MODEL_FEATURES).difference(history.columns)
    if missing:
        raise ValueError(f"Monthly history is missing model columns: {sorted(missing)}")
    return history[MODEL_FEATURES].copy()


@lru_cache(maxsize=4)
def load_seasonal_model_artifact(model_path: str | Path) -> dict[str, Any]:
    artifact = joblib.load(model_path)
    required = {"pipeline", "residual_ratio_threshold", "feature_columns"}
    if not isinstance(artifact, dict) or not required.issubset(artifact):
        raise ValueError("Invalid seasonal model artifact. Train the seasonal model again.")
    return artifact


def score_monthly_history(
    history: pd.DataFrame, artifact: dict[str, Any]
) -> pd.DataFrame:
    """Predict expected volume and flag unexpectedly high monthly activity."""
    scored = history.copy()
    scored["period_start"] = pd.to_datetime(scored["period_start"], utc=True)
    predicted = artifact["pipeline"].predict(model_input(history))
    scored["expected_monthly_volume"] = predicted.clip(min=1.0)
    scored["volume_ratio"] = (
        scored["monthly_volume"] / scored["expected_monthly_volume"]
    )
    scored["volume_residual"] = (
        scored["monthly_volume"] - scored["expected_monthly_volume"]
    )
    scored["requires_review"] = (
        scored["volume_ratio"] >= float(artifact["residual_ratio_threshold"])
    )
    return scored

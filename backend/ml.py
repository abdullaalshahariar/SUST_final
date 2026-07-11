"""Feature engineering and scoring helpers for Scenario 2.

The model receives one row per provider, location, and ten-minute window. It
does not receive customer identifiers or the synthetic evaluation labels.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


WINDOW_FREQUENCY = "10min"
CATEGORICAL_FEATURES = ["provider_code", "location"]
NUMERIC_FEATURES = [
    "transaction_count",
    "cash_out_count",
    "cash_in_count",
    "log_total_amount",
    "log_average_amount",
    "amount_coefficient_variation",
    "failed_count",
    "pending_count",
    "cash_out_ratio",
    "cash_out_similarity_ratio",
]
MODEL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
REQUIRED_TRANSACTION_COLUMNS = {
    "provider_code",
    "event_at",
    "type",
    "amount",
    "location",
    "status",
}


def load_transactions(csv_path: str | Path) -> pd.DataFrame:
    """Load and validate a Scenario 2 transaction CSV."""
    transactions = pd.read_csv(csv_path)
    missing = REQUIRED_TRANSACTION_COLUMNS.difference(transactions.columns)
    if missing:
        raise ValueError(f"Transaction CSV is missing required columns: {sorted(missing)}")

    transactions["event_at"] = pd.to_datetime(
        transactions["event_at"], utc=True, errors="raise"
    )
    transactions["amount"] = pd.to_numeric(transactions["amount"], errors="raise")
    if (transactions["amount"] <= 0).any():
        raise ValueError("Transaction amounts must be positive.")

    # These are offline evaluation fields. Real API data will not contain them.
    if "is_injected_anomaly" not in transactions:
        transactions["is_injected_anomaly"] = 0
    if "scenario_label" not in transactions:
        transactions["scenario_label"] = "unlabelled"

    transactions["is_injected_anomaly"] = pd.to_numeric(
        transactions["is_injected_anomaly"], errors="raise"
    ).astype(int)
    return transactions


def build_feature_windows(transactions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate transactions into provider-location ten-minute feature rows."""
    missing = REQUIRED_TRANSACTION_COLUMNS.difference(transactions.columns)
    if missing:
        raise ValueError(f"Transactions are missing required columns: {sorted(missing)}")
    if transactions.empty:
        raise ValueError("At least one transaction is required to build ML features.")

    data = transactions.copy()
    data["event_at"] = pd.to_datetime(data["event_at"], utc=True, errors="raise")
    data["amount"] = pd.to_numeric(data["amount"], errors="raise")
    data["window_start"] = data["event_at"].dt.floor(WINDOW_FREQUENCY)
    data["is_cash_out"] = (data["type"] == "cash_out").astype(int)
    data["is_cash_in"] = (data["type"] == "cash_in").astype(int)
    data["is_failed"] = (data["status"] == "failed").astype(int)
    data["is_pending"] = (data["status"] == "pending").astype(int)

    if "is_injected_anomaly" not in data:
        data["is_injected_anomaly"] = 0
    if "scenario_label" not in data:
        data["scenario_label"] = "unlabelled"

    group_columns = ["provider_code", "location", "window_start"]
    windows = (
        data.groupby(group_columns, as_index=False)
        .agg(
            transaction_count=("amount", "size"),
            cash_out_count=("is_cash_out", "sum"),
            cash_in_count=("is_cash_in", "sum"),
            total_amount=("amount", "sum"),
            average_amount=("amount", "mean"),
            amount_standard_deviation=("amount", "std"),
            maximum_amount=("amount", "max"),
            failed_count=("is_failed", "sum"),
            pending_count=("is_pending", "sum"),
            is_injected_anomaly=("is_injected_anomaly", "max"),
        )
        .sort_values(group_columns)
        .reset_index(drop=True)
    )
    windows["amount_standard_deviation"] = windows[
        "amount_standard_deviation"
    ].fillna(0.0)
    windows["cash_out_ratio"] = (
        windows["cash_out_count"] / windows["transaction_count"]
    )
    windows["amount_coefficient_variation"] = np.where(
        windows["average_amount"] > 0,
        windows["amount_standard_deviation"] / windows["average_amount"],
        0.0,
    )
    windows["log_total_amount"] = np.log1p(windows["total_amount"])
    windows["log_average_amount"] = np.log1p(windows["average_amount"])

    similarity_rows: list[dict[str, object]] = []
    for group_key, group in data.groupby(group_columns):
        cash_outs = group.loc[group["type"] == "cash_out", "amount"]
        if len(cash_outs) < 4:
            similarity = 0.0
        else:
            median = float(cash_outs.median())
            tolerance = max(300.0, median * 0.08)
            similarity = float(((cash_outs - median).abs() <= tolerance).mean())
        similarity_rows.append(
            {
                "provider_code": group_key[0],
                "location": group_key[1],
                "window_start": group_key[2],
                "cash_out_similarity_ratio": similarity,
                "has_legitimate_surge": int(
                    (group["scenario_label"] == "legitimate_surge").any()
                ),
            }
        )
    windows = windows.merge(
        pd.DataFrame(similarity_rows), on=group_columns, how="left", validate="one_to_one"
    )

    # A window is unusual if any transaction in it was deliberately injected.
    # This label is retained only to evaluate the model after it has scored data.
    windows["scenario_label"] = np.select(
        [
            windows["is_injected_anomaly"].eq(1),
            windows["has_legitimate_surge"].eq(1),
        ],
        ["injected_unusual", "legitimate_surge"],
        default="normal",
    )
    return windows


def model_input(windows: pd.DataFrame) -> pd.DataFrame:
    """Return exactly the columns supplied to the Isolation Forest pipeline."""
    missing = set(MODEL_FEATURES).difference(windows.columns)
    if missing:
        raise ValueError(f"Feature windows are missing model columns: {sorted(missing)}")
    return windows[MODEL_FEATURES].copy()


@lru_cache(maxsize=4)
def load_model_artifact(model_path: str | Path) -> dict[str, Any]:
    """Load a previously trained model artifact for API-time scoring."""
    artifact = joblib.load(model_path)
    required = {"pipeline", "threshold", "feature_columns"}
    if not isinstance(artifact, dict) or not required.issubset(artifact):
        raise ValueError("Invalid model artifact. Train the Scenario 2 model again.")
    return artifact


def score_feature_windows(
    windows: pd.DataFrame,
    artifact: dict[str, Any],
) -> pd.DataFrame:
    """Add model scores and advisory review flags to feature windows."""
    features = model_input(windows)
    pipeline = artifact["pipeline"]
    scored = windows.copy()

    # Isolation Forest returns larger values for normal points. Negating the
    # result gives us a human-friendly score where larger means more unusual.
    scored["anomaly_score"] = -pipeline.score_samples(features)
    review_gate = artifact.get("review_gate", {})
    minimum_cash_out_count = int(review_gate.get("minimum_cash_out_count", 0))
    minimum_similarity_ratio = float(review_gate.get("minimum_similarity_ratio", 0.0))

    # The ML score identifies windows unlike normal activity. The evidence gate
    # makes the final alert specific to this scenario: repeated cash-outs with
    # similar amounts. It avoids treating a broad, legitimate demand spike as
    # the same pattern.
    scored["requires_review"] = (
        (scored["anomaly_score"] >= float(artifact["threshold"]))
        & (scored["cash_out_count"] >= minimum_cash_out_count)
        & (scored["cash_out_similarity_ratio"] >= minimum_similarity_ratio)
    )
    return scored

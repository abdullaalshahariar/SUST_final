"""Generate long-term, context-aware monthly volume history.

The data intentionally includes ordinary months around an agent baseline and
Eid months around five times that baseline. A small number of injected records
are much larger than their *contextual* expected volume for model evaluation.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timezone
from pathlib import Path


AGENTS = tuple(f"agent_{index:02d}" for index in range(1, 19))
PROVIDERS = ("bkash_sim", "nagad_sim", "rocket_sim")
LOCATIONS = (
    "Zindabazar, Sylhet",
    "Ambarkhana, Sylhet",
    "Shahjalal Uposhahar, Sylhet",
)
EID_MONTHS = {3, 11}  # Simulated seasonal calendar used only by this prototype.
FIELDNAMES = (
    "period_start",
    "agent_id",
    "provider_code",
    "location",
    "event_context",
    "month_number",
    "year_index",
    "monthly_volume",
    "is_injected_anomaly",
)
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "agent_monthly_history.csv"


def period_for(index: int) -> tuple[int, int]:
    year = 2023 + (index // 12)
    month = (index % 12) + 1
    return year, month


def generate_history(months: int = 36, seed: int = 42) -> list[dict[str, object]]:
    if months < 24:
        raise ValueError("Use at least 24 months so the model sees repeated Eid seasons.")

    rng = random.Random(seed)
    baseline = {
        (agent_id, provider_code): rng.randint(85_000, 125_000)
        for agent_id in AGENTS
        for provider_code in PROVIDERS
    }
    provider_multiplier = {"bkash_sim": 1.12, "nagad_sim": 1.0, "rocket_sim": 0.86}
    rows: list[dict[str, object]] = []

    for month_index in range(months):
        year, month = period_for(month_index)
        is_eid = month in EID_MONTHS
        event_context = "eid" if is_eid else "normal"
        seasonal_multiplier = 5.0 if is_eid else 1.0
        for agent_index, agent_id in enumerate(AGENTS):
            location = LOCATIONS[agent_index % len(LOCATIONS)]
            for provider_code in PROVIDERS:
                expected = (
                    baseline[(agent_id, provider_code)]
                    * provider_multiplier[provider_code]
                    * seasonal_multiplier
                )
                volume = int(round(expected * rng.uniform(0.88, 1.12) / 100) * 100)
                rows.append(
                    {
                        "period_start": datetime(year, month, 1, tzinfo=timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "agent_id": agent_id,
                        "provider_code": provider_code,
                        "location": location,
                        "event_context": event_context,
                        "month_number": month,
                        "year_index": month_index // 12,
                        "monthly_volume": volume,
                        "is_injected_anomaly": 0,
                    }
                )

    # Inject a few volumes far beyond the seasonal context. An Eid month may
    # normally be ~5 lakh; these cases are about 2.4x that expected Eid level.
    normal_rows = [row for row in rows if row["event_context"] == "normal"]
    eid_rows = [row for row in rows if row["event_context"] == "eid"]
    for row in rng.sample(normal_rows, 8):
        row["monthly_volume"] = int(int(row["monthly_volume"]) * rng.uniform(3.2, 4.0))
        row["is_injected_anomaly"] = 1
    for row in rng.sample(eid_rows, 8):
        row["monthly_volume"] = int(int(row["monthly_volume"]) * rng.uniform(2.1, 2.6))
        row["is_injected_anomaly"] = 1

    return rows


def write_history(output_path: Path, months: int, seed: int) -> dict[str, int]:
    rows = generate_history(months=months, seed=seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return {
        "rows": len(rows),
        "normal_rows": sum(row["is_injected_anomaly"] == 0 for row in rows),
        "injected_anomaly_rows": sum(row["is_injected_anomaly"] == 1 for row in rows),
        "eid_rows": sum(row["event_context"] == "eid" for row in rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate context-aware monthly agent volume history."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--months", type=int, default=36)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    summary = write_history(arguments.output, arguments.months, arguments.seed)
    print(f"Created: {arguments.output.resolve()}")
    for key, value in summary.items():
        print(f"{key}: {value}")

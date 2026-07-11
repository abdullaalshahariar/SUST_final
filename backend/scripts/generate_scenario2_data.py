

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROVIDERS = ("bkash_sim", "nagad_sim", "rocket_sim")
LOCATIONS = (
    "Zindabazar, Sylhet",
    "Ambarkhana, Sylhet",
    "Shahjalal Uposhahar, Sylhet",
)
FIELDNAMES = (
    "provider_code",
    "event_at",
    "type",
    "amount",
    "location",
    "status",
    "is_injected_anomaly",
    "scenario_label",
)
WINDOW_MINUTES = 10
DEFAULT_START = datetime(2026, 7, 8, tzinfo=timezone.utc)
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "scenario2_transactions.csv"


def iso_utc(value: datetime) -> str:
    """Format a timezone-aware datetime in a compact UTC representation."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def random_event_time(window_start: datetime, rng: random.Random) -> datetime:
    """Choose a time that remains inside the current ten-minute window."""
    return window_start + timedelta(seconds=rng.randint(0, 599))


def normal_transaction_count(hour: int, rng: random.Random) -> int:
    """Simulate higher activity during normal agent-shop operating hours."""
    if 9 <= hour < 21:
        return rng.choices((1, 2, 3, 4, 5), weights=(10, 25, 35, 20, 10))[0]
    return rng.choices((0, 1, 2), weights=(60, 30, 10))[0]


def normal_amount(transaction_type: str, rng: random.Random) -> int:
    """Generate a positive, right-skewed transaction amount in BDT."""
    median = 2_500 if transaction_type == "cash_out" else 2_000
    amount = rng.lognormvariate(0, 0.75) * median
    return max(100, min(25_000, int(round(amount / 50) * 50)))


def make_normal_rows(
    start: datetime,
    days: int,
    rng: random.Random,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    window_count = days * 24 * (60 // WINDOW_MINUTES)

    for window_index in range(window_count):
        window_start = start + timedelta(minutes=window_index * WINDOW_MINUTES)
        for provider_code in PROVIDERS:
            for location in LOCATIONS:
                count = normal_transaction_count(window_start.hour, rng)
                for _ in range(count):
                    transaction_type = rng.choices(
                        ("cash_out", "cash_in"), weights=(55, 45)
                    )[0]
                    status = rng.choices(
                        ("completed", "failed", "pending"),
                        weights=(96, 2, 2),
                    )[0]
                    rows.append(
                        {
                            "provider_code": provider_code,
                            "event_at": iso_utc(random_event_time(window_start, rng)),
                            "type": transaction_type,
                            "amount": normal_amount(transaction_type, rng),
                            "location": location,
                            "status": status,
                            "is_injected_anomaly": 0,
                            "scenario_label": "normal",
                        }
                    )

    return rows


def inject_legitimate_surges(
    rows: list[dict[str, object]],
    start: datetime,
    days: int,
    rng: random.Random,
) -> None:
    """Add high-volume but legitimate demand to test false-positive behaviour."""
    for day in range(days):
        day_start = start + timedelta(days=day)
        surge_specs = (
            ("bkash_sim", LOCATIONS[0], day_start.replace(hour=9, minute=20)),
            ("nagad_sim", LOCATIONS[1], day_start.replace(hour=13, minute=10)),
            ("rocket_sim", LOCATIONS[2], day_start.replace(hour=18, minute=30)),
        )

        for provider_code, location, window_start in surge_specs:
            for _ in range(10):
                transaction_type = rng.choice(("cash_out", "cash_in"))
                rows.append(
                    {
                        "provider_code": provider_code,
                        "event_at": iso_utc(random_event_time(window_start, rng)),
                        "type": transaction_type,
                        "amount": rng.randrange(500, 15_001, 50),
                        "location": location,
                        "status": "completed",
                        "is_injected_anomaly": 0,
                        "scenario_label": "legitimate_surge",
                    }
                )


def inject_unusual_windows(
    rows: list[dict[str, object]],
    start: datetime,
    days: int,
    rng: random.Random,
) -> None:
    """Inject repeated, similar cash-outs in six provider-location windows."""
    final_day = start + timedelta(days=days - 1)
    unusual_specs = (
        ("nagad_sim", LOCATIONS[0], 10, 20),
        ("bkash_sim", LOCATIONS[1], 11, 40),
        ("rocket_sim", LOCATIONS[2], 13, 0),
        ("nagad_sim", LOCATIONS[1], 14, 30),
        ("bkash_sim", LOCATIONS[2], 16, 0),
        ("rocket_sim", LOCATIONS[0], 19, 10),
    )

    for provider_code, location, hour, minute in unusual_specs:
        window_start = final_day.replace(hour=hour, minute=minute)
        for _ in range(rng.randint(12, 15)):
            rows.append(
                {
                    "provider_code": provider_code,
                    "event_at": iso_utc(random_event_time(window_start, rng)),
                    "type": "cash_out",
                    "amount": rng.randrange(4_800, 5_201, 50),
                    "location": location,
                    "status": "completed",
                    "is_injected_anomaly": 1,
                    "scenario_label": "injected_unusual",
                }
            )


def generate_dataset(
    output_path: Path,
    days: int = 3,
    seed: int = 42,
) -> dict[str, int]:
    """Generate, sort, and write the complete Scenario 2 CSV."""
    if days < 1:
        raise ValueError("days must be at least 1")

    rng = random.Random(seed)
    rows = make_normal_rows(DEFAULT_START, days, rng)
    inject_legitimate_surges(rows, DEFAULT_START, days, rng)
    inject_unusual_windows(rows, DEFAULT_START, days, rng)
    rows.sort(key=lambda row: str(row["event_at"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "total_transactions": len(rows),
        "normal_transactions": sum(
            row["scenario_label"] == "normal" for row in rows
        ),
        "legitimate_surge_transactions": sum(
            row["scenario_label"] == "legitimate_surge" for row in rows
        ),
        "injected_unusual_transactions": sum(
            row["scenario_label"] == "injected_unusual" for row in rows
        ),
        "injected_unusual_windows": 6,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic transactions for Scenario 2."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"CSV output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    summary = generate_dataset(arguments.output, arguments.days, arguments.seed)
    print(f"Created: {arguments.output.resolve()}")
    for key, value in summary.items():
        print(f"{key}: {value}")

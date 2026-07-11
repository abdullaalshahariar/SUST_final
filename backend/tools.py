from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Alert, ProviderPosition, Transaction


FORECAST_WINDOW_MINUTES = 15
ALERT_LEAD_TIME_MINUTES = 60


def calculate_liquidity_forecast(
    db: Session, position: ProviderPosition, now: datetime
) -> dict:
    """Return a transparent e-money forecast for one provider position."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    recorded_at = position.recorded_at
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)

    if position.quality_status != "fresh" or recorded_at < now - timedelta(minutes=15):
        return {
            "burn_per_minute": None,
            "minutes_to_threshold": None,
            "confidence": "low",
            "reason": "Balance data is stale; confirm the provider balance before acting.",
        }

    window_start = now - timedelta(minutes=FORECAST_WINDOW_MINUTES)
    # The demo data is deliberately small, so summing the matching values keeps
    # the calculation easy to inspect during a presentation.
    cash_ins = db.scalars(
        select(Transaction.amount).where(
            Transaction.agent_id == position.agent_id,
            Transaction.provider_code == position.provider_code,
            Transaction.type == "cash_in",
            Transaction.event_at >= window_start,
            Transaction.event_at <= now,
        )
    ).all()
    total_cash_in = sum(cash_ins)
    burn_per_minute = total_cash_in / FORECAST_WINDOW_MINUTES

    if burn_per_minute == 0:
        return {
            "burn_per_minute": 0,
            "minutes_to_threshold": None,
            "confidence": "high",
            "reason": "No recent cash-in demand is consuming this provider's e-money.",
        }

    minutes_to_threshold = max(
        0, (position.balance - position.safety_threshold) / burn_per_minute
    )
    return {
        "burn_per_minute": round(burn_per_minute, 2),
        "minutes_to_threshold": round(minutes_to_threshold, 1),
        "confidence": "high",
        "reason": "Estimate uses cash-in demand from the latest 15 simulated minutes.",
    }


def create_liquidity_alerts(db: Session, now: datetime) -> list[Alert]:
    """Create advisory alerts for provider balances likely to hit their threshold soon."""
    positions = db.scalars(select(ProviderPosition)).all()
    created: list[Alert] = []

    for position in positions:
        forecast = calculate_liquidity_forecast(db, position, now)
        minutes = forecast["minutes_to_threshold"]
        if minutes is None or minutes >= ALERT_LEAD_TIME_MINUTES:
            continue

        alert = Alert(
            agent_id=position.agent_id,
            provider_code=position.provider_code,
            type="liquidity",
            status="open",
            title=f"{provider_label(position.provider_code)} e-money shortage risk",
            evidence=(
                f"Current balance: {position.balance:,} BDT; safety threshold: "
                f"{position.safety_threshold:,} BDT; recent cash-in demand: "
                f"{forecast['burn_per_minute']:,.0f} BDT/minute; estimated time to threshold: "
                f"{minutes:g} minutes."
            ),
            recommended_action=(
                f"Confirm the {provider_label(position.provider_code)} balance and "
                "arrange support through approved channels. No transfer or conversion is performed."
            ),
            confidence=forecast["confidence"],
        )
        db.add(alert)
        created.append(alert)

    return created


def provider_label(provider_code: str) -> str:
    return {
        "bkash_sim": "bKash",
        "nagad_sim": "Nagad",
        "rocket_sim": "Rocket",
    }.get(provider_code, provider_code)
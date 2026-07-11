from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Agent, Alert, ProviderPosition, Transaction


FORECAST_WINDOW_MINUTES = 15
ALERT_LEAD_TIME_MINUTES = 60
MAX_VELOCITY_WINDOW_MINUTES = 30
OPERATIONAL_ATTENTION_BUFFER = 1.75
SHARED_CASH_ALERT_PROVIDER = "shared_cash_sim"


def _as_utc(value: datetime) -> datetime:
    """Normalise SQLite's sometimes-naive datetimes before comparing them."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _minutes_to_limit(balance: float, limit: float, burn_per_minute: float) -> float | None:
    """Return minutes until a balance reaches a limit, or None when it is not falling."""
    if burn_per_minute <= 0:
        return None
    return round(max(0.0, (balance - limit) / burn_per_minute), 2)


def calculate_cash_velocity(
    db: Session,
    agent_id: int,
    w: int = MAX_VELOCITY_WINDOW_MINUTES,
    now: datetime | None = None,
) -> dict:
    """Calculate current cash-depletion velocity from completed transactions.

    ``w`` is the look-back window in minutes and must be between 1 and 30.

    Physical cash is depleted by cash-outs and replenished by cash-ins.
    Provider e-money is depleted by cash-ins and replenished by cash-outs.
    The returned velocity is therefore a *net* burn rate, not just gross
    transaction volume.
    """
    if not 1 <= w <= MAX_VELOCITY_WINDOW_MINUTES:
        raise ValueError(
            f"w must be between 1 and {MAX_VELOCITY_WINDOW_MINUTES} minutes."
        )

    agent = db.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"Agent {agent_id} does not exist.")

    current_time = _as_utc(now or datetime.now(timezone.utc))
    window_start = current_time - timedelta(minutes=w)

    # Query the agent's completed transactions. Date filtering is applied again
    # in Python so SQLite timezone differences cannot include stale records.
    # SQLite stores the current project's DateTime values without timezone
    # information, so query with naive UTC values and normalise before use.
    database_window_start = window_start.replace(tzinfo=None)
    database_current_time = current_time.replace(tzinfo=None)
    transactions = db.scalars(
        select(Transaction).where(
            Transaction.agent_id == agent_id,
            Transaction.status == "completed",
            Transaction.event_at >= database_window_start,
            Transaction.event_at <= database_current_time,
        )
    ).all()
    transactions = [
        transaction
        for transaction in transactions
        if window_start <= _as_utc(transaction.event_at) <= current_time
    ]

    physical_cash_out = sum(
        transaction.amount for transaction in transactions if transaction.type == "cash_out"
    )
    physical_cash_in = sum(
        transaction.amount for transaction in transactions if transaction.type == "cash_in"
    )
    physical_net_burn = physical_cash_out - physical_cash_in
    physical_burn_per_minute = physical_net_burn / w

    # There can be many historical position snapshots. Keep only the newest
    # one for each provider before calculating its current e-money forecast.
    all_positions = db.scalars(
        select(ProviderPosition)
        .where(ProviderPosition.agent_id == agent_id)
        .order_by(ProviderPosition.provider_code, ProviderPosition.recorded_at.desc())
    ).all()
    latest_positions: dict[str, ProviderPosition] = {}
    for position in all_positions:
        latest_positions.setdefault(position.provider_code, position)

    provider_e_money: dict[str, dict] = {}
    for provider_code, position in latest_positions.items():
        provider_transactions = [
            transaction
            for transaction in transactions
            if transaction.provider_code == provider_code
        ]
        # A cash-in sends provider e-money to a customer; a cash-out returns
        # provider e-money to the agent. The difference is the net e-money burn.
        e_money_cash_in = sum(
            transaction.amount
            for transaction in provider_transactions
            if transaction.type == "cash_in"
        )
        e_money_cash_out = sum(
            transaction.amount
            for transaction in provider_transactions
            if transaction.type == "cash_out"
        )
        net_e_money_burn = e_money_cash_in - e_money_cash_out
        burn_per_minute = net_e_money_burn / w

        provider_e_money[provider_code] = {
            "current_balance": float(position.balance),
            "safety_threshold": float(position.safety_threshold),
            "cash_in_total": e_money_cash_in,
            "cash_out_total": e_money_cash_out,
            "net_burn_per_minute": round(burn_per_minute, 2),
            "minutes_to_safety_threshold": _minutes_to_limit(
                float(position.balance),
                float(position.safety_threshold),
                burn_per_minute,
            ),
            "minutes_to_exhaustion": _minutes_to_limit(
                float(position.balance),
                0.0,
                burn_per_minute,
            ),
            "transaction_count": len(provider_transactions),
            "quality_status": position.quality_status,
        }

    return {
        "agent_id": agent.id,
        "window_minutes": w,
        "window_start": window_start.isoformat(),
        "window_end": current_time.isoformat(),
        "completed_transaction_count": len(transactions),
        "physical_cash": {
            "current_balance": float(agent.shared_cash),
            "safety_threshold": float(agent.cash_threshold),
            "cash_out_total": physical_cash_out,
            "cash_in_total": physical_cash_in,
            "net_burn_per_minute": round(physical_burn_per_minute, 2),
            "minutes_to_safety_threshold": _minutes_to_limit(
                float(agent.shared_cash),
                float(agent.cash_threshold),
                physical_burn_per_minute,
            ),
            "minutes_to_exhaustion": _minutes_to_limit(
                float(agent.shared_cash),
                0.0,
                physical_burn_per_minute,
            ),
        },
        "provider_e_money": provider_e_money,
    }


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


def reconcile_liquidity_alerts(
    db: Session,
    now: datetime,
    positions: list[ProviderPosition] | None = None,
) -> list[Alert]:
    """Synchronise provider liquidity alerts with current synthetic balances."""
    positions = positions or db.scalars(select(ProviderPosition)).all()
    created: list[Alert] = []

    for position in positions:
        forecast = calculate_liquidity_forecast(db, position, now)
        minutes = forecast["minutes_to_threshold"]
        attention_threshold = position.safety_threshold * OPERATIONAL_ATTENTION_BUFFER
        needs_attention = (
            position.balance < attention_threshold
            or (minutes is not None and minutes < ALERT_LEAD_TIME_MINUTES)
        )
        active_alerts = db.scalars(
            select(Alert).where(
                Alert.agent_id == position.agent_id,
                Alert.provider_code == position.provider_code,
                Alert.type == "liquidity",
                Alert.status != "resolved",
            )
        ).all()

        if needs_attention and not active_alerts:
            minutes_text = f"{minutes:g} minutes" if minutes is not None else "not available"
            alert = Alert(
                agent_id=position.agent_id,
                provider_code=position.provider_code,
                type="liquidity",
                status="open",
                title=f"{provider_label(position.provider_code)} e-money requires review",
                evidence=(
                    f"Current balance: {position.balance:,} BDT; safety threshold: "
                    f"{position.safety_threshold:,} BDT; operational attention buffer: "
                    f"{attention_threshold:,.0f} BDT; estimated time to threshold: {minutes_text}."
                ),
                recipient=f"{provider_label(position.provider_code)} Provider Operations",
                owner="Sylhet Field Operations",
                recommended_action=(
                    f"Confirm the {provider_label(position.provider_code)} balance and "
                    "arrange support through approved channels. No transfer or conversion is performed."
                ),
                confidence=forecast["confidence"],
            )
            db.add(alert)
            created.append(alert)
        elif not needs_attention:
            for alert in active_alerts:
                alert.status = "resolved"
                alert.note = (
                    f"System balance check: {provider_label(position.provider_code)} e-money is "
                    f"{position.balance:,.0f} BDT, at or above the "
                    f"{OPERATIONAL_ATTENTION_BUFFER:g}x operational safety buffer."
                )

    # Shared physical cash is not a provider wallet. It uses its own synthetic
    # alert context so it can be tracked without exposing it as bKash, Nagad,
    # or Rocket e-money.
    agent_ids = {position.agent_id for position in positions}
    for agent_id in agent_ids:
        agent = db.get(Agent, agent_id)
        if agent is None:
            continue
        # Physical cash uses its explicit safety threshold. The 1.75x buffer
        # is retained for provider e-money because that balance can deplete
        # quickly through customer cash-ins.
        attention_threshold = agent.cash_threshold
        active_alerts = db.scalars(
            select(Alert).where(
                Alert.agent_id == agent.id,
                Alert.provider_code == SHARED_CASH_ALERT_PROVIDER,
                Alert.type == "cash_reserve",
                Alert.status != "resolved",
            )
        ).all()
        if agent.shared_cash < attention_threshold and not active_alerts:
            alert = Alert(
                agent_id=agent.id,
                provider_code=SHARED_CASH_ALERT_PROVIDER,
                type="cash_reserve",
                status="open",
                title="Shared physical cash requires review",
                evidence=(
                    f"Current shared cash: {agent.shared_cash:,.0f} BDT; safety threshold: "
                    f"{agent.cash_threshold:,.0f} BDT; operational attention buffer: "
                    f"{attention_threshold:,.0f} BDT."
                ),
                recipient="Central Cash Operations",
                owner="Sylhet Field Operations",
                recommended_action=(
                    "Confirm the physical cash count and arrange approved cash support. "
                    "No automatic cash movement is performed."
                ),
                confidence="high",
            )
            db.add(alert)
            created.append(alert)
        elif agent.shared_cash >= attention_threshold:
            for alert in active_alerts:
                alert.status = "resolved"
                alert.note = (
                    f"System cash check: shared physical cash is {agent.shared_cash:,.0f} BDT, "
                    "at or above its shared-cash safety threshold."
                )

    return created


def create_liquidity_alerts(db: Session, now: datetime) -> list[Alert]:
    """Compatibility wrapper used when the synthetic demo is seeded."""
    return reconcile_liquidity_alerts(db, now)


def provider_label(provider_code: str) -> str:
    return {
        "bkash_sim": "bKash",
        "nagad_sim": "Nagad",
        "rocket_sim": "Rocket",
        SHARED_CASH_ALERT_PROVIDER: "Shared Cash Reserve",
    }.get(provider_code, provider_code)

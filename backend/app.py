from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db, init_db, reset_demo_data
from models import (
    Agent,
    AgentResponse,
    Alert,
    AlertResponse,
    AlertUpdate,
    DemoResetResponse,
    HealthResponse,
    OverviewResponse,
    PositionResponse,
    Provider,
    ProviderResponse,
    ProviderPosition,
    Transaction,
    TransactionResponse,
    utc_now,
)
from tools import calculate_liquidity_forecast


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Multi-Provider Liquidity Monitor API",
    version="1.0.0",
    description=(
        "A synthetic, advisory-only API for Scenario 1. It forecasts provider "
        "e-money pressure from recent cash-in demand and supports human alert review. "
        "It never connects to real wallets, transfers money, or determines fraud."
    ),
    lifespan=lifespan,
)


def require_agent(db: Session) -> Agent:
    agent = db.scalar(select(Agent).order_by(Agent.id))
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No demo data exists. Use POST /demo/reset first.",
        )
    return agent


def alert_response(alert: Alert) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        provider_code=alert.provider_code,
        type=alert.type,
        status=alert.status,
        title=alert.title,
        evidence=alert.evidence,
        recommended_action=alert.recommended_action,
        confidence=alert.confidence,
        note=alert.note,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Confirm that the API is running."""
    return HealthResponse(status="ok")


@app.post(
    "/demo/reset",
    response_model=DemoResetResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["demo"],
)
def reset_demo() -> DemoResetResponse:
    """Rebuild the fixed synthetic Nagad shortage scenario."""
    agent_name, alerts_created = reset_demo_data()
    return DemoResetResponse(
        message="Synthetic Scenario 1 data reset successfully.",
        agent_name=agent_name,
        alerts_created=alerts_created,
    )


@app.get("/providers", response_model=list[ProviderResponse], tags=["monitoring"])
def list_providers(db: Session = Depends(get_db)) -> list[ProviderResponse]:
    """List the logically separate simulated providers."""
    return [
        ProviderResponse(code=provider.code, display_name=provider.display_name)
        for provider in db.scalars(select(Provider).order_by(Provider.code)).all()
    ]


@app.get(
    "/positions",
    response_model=list[PositionResponse],
    tags=["monitoring"],
)
def list_positions(db: Session = Depends(get_db)) -> list[PositionResponse]:
    """Return each provider balance with its explainable liquidity forecast."""
    agent = require_agent(db)
    provider_names = {
        provider.code: provider.display_name
        for provider in db.scalars(select(Provider)).all()
    }
    positions = db.scalars(
        select(ProviderPosition)
        .where(ProviderPosition.agent_id == agent.id)
        .order_by(ProviderPosition.provider_code)
    ).all()
    now = utc_now()
    return [
        PositionResponse(
            provider_code=position.provider_code,
            display_name=provider_names[position.provider_code],
            balance=position.balance,
            total_cash=agent.shared_cash,
            safety_threshold=position.safety_threshold,
            recorded_at=position.recorded_at,
            quality_status=position.quality_status,
            forecast=calculate_liquidity_forecast(db, position, now),
        )
        for position in positions
    ]


@app.get("/alerts", response_model=list[AlertResponse], tags=["alerts"])
def list_alerts(
    include_resolved: bool = Query(False, description="Include alerts already resolved by a human."),
    db: Session = Depends(get_db),
) -> list[AlertResponse]:
    """List alerts and the evidence supporting each advisory warning."""
    agent = require_agent(db)
    query = select(Alert).where(Alert.agent_id == agent.id)
    if not include_resolved:
        query = query.where(Alert.status != "resolved")
    alerts = db.scalars(query.order_by(Alert.created_at.desc())).all()
    return [alert_response(alert) for alert in alerts]


@app.patch("/alerts/{alert_id}", response_model=AlertResponse, tags=["alerts"])
def update_alert(
    alert_id: int,
    payload: AlertUpdate,
    db: Session = Depends(get_db),
) -> AlertResponse:
    """Acknowledge an alert or resolve it with a required human-review note."""
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found.")

    alert.status = payload.status.value
    alert.note = payload.note.strip() if payload.note else None
    db.commit()
    db.refresh(alert)
    return alert_response(alert)


@app.get(
    "/transactions",
    response_model=list[TransactionResponse],
    tags=["monitoring"],
)
def list_recent_transactions(
    limit: Annotated[
        int, Query(ge=1, le=100, description="Maximum number of recent synthetic transactions.")
    ] = 8,
    db: Session = Depends(get_db),
) -> list[TransactionResponse]:
    """Inspect synthetic transactions used as forecast evidence."""
    agent = require_agent(db)
    transactions = db.scalars(
        select(Transaction)
        .where(Transaction.agent_id == agent.id)
        .order_by(Transaction.event_at.desc())
        .limit(limit)
    ).all()
    return [
        TransactionResponse(
            id=transaction.id,
            provider_code=transaction.provider_code,
            type=transaction.type,
            amount=transaction.amount,
            event_at=transaction.event_at,
            location=transaction.location,
            status=transaction.status,
        )
        for transaction in transactions
    ]


@app.get("/overview", response_model=OverviewResponse, tags=["monitoring"])
def overview(db: Session = Depends(get_db)) -> OverviewResponse:
    """Return all Scenario 1 API data in one response for quick Swagger inspection."""
    agent = require_agent(db)
    return OverviewResponse(
        agent=AgentResponse.model_validate(agent),
        positions=list_positions(db),
        alerts=list_alerts(db=db),
        recent_transactions=list_recent_transactions(db=db),
    )

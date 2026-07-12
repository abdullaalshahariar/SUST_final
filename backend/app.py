from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Annotated, Literal

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionLocal, get_db, init_db, reset_demo_data
from models import (
    Agent,
    AgentResponse,
    Alert,
    AlertResponse,
    AlertUpdate,
    CoordinationProposalCreate,
    CoordinationResponse,
    CoordinationUpdate,
    DemoResetResponse,
    DemoStaleBalanceResponse,
    HealthResponse,
    InferenceTransaction,
    MetricExplanation,
    MetricsResponse,
    MonthlyVolumeFinding,
    MonthlyVolumeInferenceRecord,
    MonthlyVolumeInferenceRequest,
    MonthlyVolumeInferenceResponse,
    PositionResponse,
    Provider,
    ProviderResponse,
    ProviderPosition,
    SupportCoordination,
    Transaction,
    TransactionCreate,
    TransactionPatternFinding,
    TransactionPatternInferenceRequest,
    TransactionPatternInferenceResponse,
    TransactionResponse,
    utc_now,
)
from ml import build_feature_windows, load_model_artifact, score_feature_windows
from seasonal_ml import load_seasonal_model_artifact, score_monthly_history
from tools import (
    OPERATIONAL_ATTENTION_BUFFER,
    SHARED_CASH_ALERT_PROVIDER,
    calculate_cash_velocity,
    calculate_liquidity_forecast,
    reconcile_liquidity_alerts,
)


BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
TRANSACTION_MODEL_PATH = BACKEND_DIR / "scripts" / "isolation_forest.joblib"
SEASONAL_MODEL_PATH = BACKEND_DIR / "scripts" / "seasonal_volume_model.joblib"
TRANSACTION_METRICS_PATH = BACKEND_DIR / "scripts" / "anomaly_threshold.json"
SEASONAL_METRICS_PATH = BACKEND_DIR / "scripts" / "seasonal_volume_threshold.json"
SEASONAL_BASE_YEAR = 2023
@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # A fresh Render instance has no local SQLite data. Seed the synthetic
    # demo once so the hosted frontend is usable immediately. Existing local
    # or persistent-disk data is never overwritten at startup.
    with SessionLocal() as db:
        demo_exists = db.scalar(select(Agent.id).limit(1)) is not None
    if not demo_exists:
        reset_demo_data()
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

# Permit the separately hosted static frontend to call this public demo API.
# Render and Vercel preview/production hostnames are accepted, along with the
# common local origins used during frontend development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"https://[a-zA-Z0-9-]+\.(?:onrender\.com|vercel\.app)",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


def require_agent(db: Session) -> Agent:
    agent = db.scalar(select(Agent).order_by(Agent.id))
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No demo data exists. Use POST /demo/reset first.",
        )
    return agent


def require_selected_agent(db: Session, agent_id: int | None) -> Agent:
    """Return the requested agent, or the single demo agent when omitted."""
    if agent_id is None:
        return require_agent(db)
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} was not found.",
        )
    return agent


def utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def alert_response(alert: Alert) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        provider_code=alert.provider_code,
        type=alert.type,
        status=alert.status,
        title=alert.title,
        evidence=alert.evidence,
        recipient=alert.recipient,
        owner=alert.owner,
        recommended_action=alert.recommended_action,
        confidence=alert.confidence,
        note=alert.note,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


def coordination_response(case: SupportCoordination) -> CoordinationResponse:
    return CoordinationResponse(
        id=case.id,
        provider_code=case.provider_code,
        requester_agent_id=case.requester_agent_id,
        supporting_agent_id=case.supporting_agent_id,
        alert_id=case.alert_id,
        cash_amount=case.cash_amount,
        e_money_amount=case.e_money_amount,
        status=case.status,
        note=case.note,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Confirm that the API is running."""
    return HealthResponse(status="ok")


@app.get("/metrics", response_model=MetricsResponse, tags=["evaluation"])
def metrics() -> MetricsResponse:
    """Return explained ML evaluation metrics for the synthetic demo datasets."""
    try:
        transaction_payload = json.loads(TRANSACTION_METRICS_PATH.read_text())
        seasonal_payload = json.loads(SEASONAL_METRICS_PATH.read_text())
        transaction = transaction_payload["metrics"]
        seasonal = seasonal_payload["metrics"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Model evaluation metrics are unavailable: {error}",
        ) from error

    transaction_false_positive_rate = transaction["false_positive_count"] / max(
        transaction["normal_window_count"], 1
    )
    legitimate_surge_flag_rate = transaction["legitimate_surge_flag_count"] / max(
        transaction["legitimate_surge_count"], 1
    )
    eid_false_positive_rate = seasonal["normal_eid_months_flagged"] / max(
        seasonal["normal_eid_months"], 1
    )

    return MetricsResponse(
        scope="Offline evaluation on generated synthetic hold-out scenarios.",
        metrics=[
            MetricExplanation(
                name="Transaction-pattern precision",
                value=float(transaction["precision"]),
                unit="proportion",
                explanation=(
                    "Of all short-term transaction windows flagged for review, the "
                    "proportion that were injected unusual patterns. Higher is better."
                    "AI can make mistakes. This is advisory only."   
                ),
                source="scripts/anomaly_threshold.json",
            ),
            MetricExplanation(
                name="Transaction-pattern recall",
                value=float(transaction["recall"]),
                unit="proportion",
                explanation=(
                    "Of all injected unusual short-term patterns, the proportion the "
                    "Isolation Forest pipeline detected. Higher is better."
                    "AI can make mistakes. This is advisory only."   
                ),
                source="scripts/anomaly_threshold.json",
            ),
            MetricExplanation(
                name="Transaction-pattern false-positive rate",
                value=round(float(transaction_false_positive_rate), 4),
                unit="proportion",
                explanation=(
                    "The proportion of normal ten-minute windows incorrectly flagged "
                    "for review. Lower is better."
                    "AI can make mistakes. This is advisory only."   
                ),
                source="scripts/anomaly_threshold.json",
            ),
            MetricExplanation(
                name="Legitimate-surge flag rate",
                value=round(float(legitimate_surge_flag_rate), 4),
                unit="proportion",
                explanation=(
                    "The proportion of simulated normal high-demand surge windows that "
                    "were incorrectly flagged. Lower is better."
                    "AI can make mistakes. This is advisory only."   
                ),
                source="scripts/anomaly_threshold.json",
            ),
            MetricExplanation(
                name="Seasonal monthly-volume precision",
                value=float(seasonal["precision"]),
                unit="proportion",
                explanation=(
                    "Of monthly-volume records flagged by the seasonal model, the "
                    "proportion that were injected contextual anomalies."
                    "AI can make mistakes. This is advisory only."   
                ),
                source="scripts/seasonal_volume_threshold.json",
            ),
            MetricExplanation(
                name="Normal Eid-month flag rate",
                value=round(float(eid_false_positive_rate), 4),
                unit="proportion",
                explanation=(
                    "The proportion of normal simulated Eid months incorrectly flagged. "
                    "This checks that expected Eid demand is not treated as suspicious."
                    "AI can make mistakes. This is advisory only."   
                ),
                source="scripts/seasonal_volume_threshold.json",
            ),
            MetricExplanation(
                name="Seasonal validation MAE",
                value=float(seasonal["validation_mean_absolute_error"]),
                unit="BDT",
                explanation=(
                    "Average absolute difference between predicted and actual monthly "
                    "volume on held-out normal synthetic data. Lower is better."
                    "AI can make mistakes. This is advisory only."   
                ),
                source="scripts/seasonal_volume_threshold.json",
            ),
        ],
        caveat=(
            "These results are measured on generated synthetic scenarios, not real "
            "wallet data. They demonstrate prototype behaviour and do not establish "
            "production accuracy or fraud-detection performance."
            "AI can make mistakes. This is advisory only."   
        ),
    )


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


@app.post(
    "/demo/simulate-stale-balance",
    response_model=DemoStaleBalanceResponse,
    tags=["demo"],
)
def simulate_stale_balance(
    db: Annotated[Session, Depends(get_db)],
    provider_code: str = Query(
        "nagad_sim",
        description="Provider balance to make stale. Run POST /demo/reset to restore fresh data.",
    ),
) -> DemoStaleBalanceResponse:
    """Make one synthetic provider balance stale for an uncertainty demo.

    This endpoint does not contact a provider or modify real-world balances. It
    only changes the local demo record so GET /positions shows its safe,
    low-confidence fallback instead of calculating a forecast from stale data.
    """
    agent = require_agent(db)
    position = db.scalar(
        select(ProviderPosition).where(
            ProviderPosition.agent_id == agent.id,
            ProviderPosition.provider_code == provider_code,
        )
    )
    if position is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider position '{provider_code}' was not found for agent {agent.id}.",
        )

    position.quality_status = "stale"
    position.recorded_at = utc_now() - timedelta(minutes=16)
    db.commit()
    db.refresh(position)
    return DemoStaleBalanceResponse(
        message="Synthetic balance marked stale. GET /positions will now show low confidence.",
        agent_id=agent.id,
        provider_code=position.provider_code,
        quality_status=position.quality_status,
        recorded_at=position.recorded_at,
        next_step="Call GET /positions, then POST /demo/reset to restore fresh demo data.",
    )


@app.get("/providers", response_model=list[ProviderResponse], tags=["monitoring"])
def list_providers(db: Annotated[Session, Depends(get_db)]) -> list[ProviderResponse]:
    """List the logically separate simulated providers."""
    return [
        ProviderResponse(code=provider.code, display_name=provider.display_name)
        for provider in db.scalars(select(Provider).order_by(Provider.code)).all()
        if provider.code != SHARED_CASH_ALERT_PROVIDER
    ]


@app.get("/agents", response_model=list[AgentResponse], tags=["monitoring"])
def list_agents(db: Annotated[Session, Depends(get_db)]) -> list[AgentResponse]:
    """List synthetic agents for provider-side filtering and coordination."""
    return [
        AgentResponse(
            id=agent.id,
            name=agent.name,
            area=agent.area,
            shared_cash=agent.shared_cash,
            cash_threshold=agent.cash_threshold,
            cash_attention_threshold=agent.cash_threshold,
            cash_requires_attention=(agent.shared_cash < agent.cash_threshold),
        )
        for agent in db.scalars(select(Agent).order_by(Agent.id)).all()
    ]


@app.get("/agents/{agent_id}", response_model=AgentResponse, tags=["monitoring"])
def get_agent(agent_id: int, db: Annotated[Session, Depends(get_db)]) -> AgentResponse:
    """Return one synthetic agent for the selected dashboard workspace."""
    agent = require_selected_agent(db, agent_id)
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        area=agent.area,
        shared_cash=agent.shared_cash,
        cash_threshold=agent.cash_threshold,
        cash_attention_threshold=agent.cash_threshold,
        cash_requires_attention=(agent.shared_cash < agent.cash_threshold),
    )


@app.get(
    "/provider-coordination",
    response_model=list[CoordinationResponse],
    tags=["provider operations"],
)
def list_provider_coordination(
    db: Annotated[Session, Depends(get_db)],
    provider_code: str | None = Query(None, description="Limit cases to one provider."),
    case_status: str | None = Query(None, alias="status", description="Limit by case status."),
) -> list[CoordinationResponse]:
    """List synthetic provider support-coordination cases without wallet access."""
    query = select(SupportCoordination)
    if provider_code:
        query = query.where(SupportCoordination.provider_code == provider_code)
    if case_status:
        query = query.where(SupportCoordination.status == case_status)
    cases = db.scalars(query.order_by(SupportCoordination.created_at.desc())).all()
    return [coordination_response(case) for case in cases]


@app.post(
    "/provider-coordination/proposals",
    response_model=CoordinationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["provider operations"],
)
def create_coordination_proposal(
    payload: CoordinationProposalCreate,
    db: Annotated[Session, Depends(get_db)],
) -> CoordinationResponse:
    """Record a human-created same-provider support proposal for synthetic data.

    Creating a proposal never changes a balance. A later explicit completion is
    required, modelling provider approval and human confirmation rather than an
    automatic financial action.
    """
    if db.get(Provider, payload.provider_code) is None:
        raise HTTPException(status_code=404, detail="Provider not found.")
    requester = db.get(Agent, payload.requester_agent_id)
    supporting = db.get(Agent, payload.supporting_agent_id)
    if requester is None or supporting is None:
        raise HTTPException(status_code=404, detail="Requester or supporting agent was not found.")
    if payload.alert_id is not None:
        alert = db.get(Alert, payload.alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Linked alert was not found.")
        if alert.agent_id != requester.id or alert.provider_code != payload.provider_code:
            raise HTTPException(
                status_code=422,
                detail="The linked alert must belong to the requester and selected provider.",
            )

    case = SupportCoordination(
        provider_code=payload.provider_code,
        requester_agent_id=requester.id,
        supporting_agent_id=supporting.id,
        alert_id=payload.alert_id,
        cash_amount=payload.cash_amount,
        e_money_amount=payload.e_money_amount,
        status="proposed",
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return coordination_response(case)


@app.patch(
    "/provider-coordination/{case_id}",
    response_model=CoordinationResponse,
    tags=["provider operations"],
)
def update_coordination_case(
    case_id: int,
    payload: CoordinationUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> CoordinationResponse:
    """Complete or cancel a synthetic support case after human confirmation."""
    case = db.get(SupportCoordination, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Support coordination case not found.")
    if case.status != "proposed":
        raise HTTPException(status_code=409, detail="Only proposed cases can be updated.")

    if payload.status == "completed":
        requester = db.get(Agent, case.requester_agent_id)
        supporting = db.get(Agent, case.supporting_agent_id)
        requester_position = db.scalar(
            select(ProviderPosition).where(
                ProviderPosition.agent_id == case.requester_agent_id,
                ProviderPosition.provider_code == case.provider_code,
            )
        )
        supporting_position = db.scalar(
            select(ProviderPosition).where(
                ProviderPosition.agent_id == case.supporting_agent_id,
                ProviderPosition.provider_code == case.provider_code,
            )
        )
        if not all((requester, supporting, requester_position, supporting_position)):
            raise HTTPException(status_code=409, detail="Required synthetic balances are unavailable.")
        if requester.shared_cash < case.cash_amount:
            raise HTTPException(status_code=422, detail="Requester lacks the proposed physical cash amount.")
        if supporting_position.balance - case.e_money_amount < supporting_position.safety_threshold:
            raise HTTPException(
                status_code=422,
                detail="Supporting agent would fall below the selected provider safety threshold.",
            )

        # This deliberately models only a confirmed local simulation: requester
        # cash moves to the supporter, while the supporter contributes the same
        # amount of the *same provider's* e-money to the requester. It does not
        # call a wallet, transfer real funds, or convert between providers.
        requester.shared_cash -= case.cash_amount
        supporting.shared_cash += case.cash_amount
        requester_position.balance += case.e_money_amount
        supporting_position.balance -= case.e_money_amount
        timestamp = utc_now()
        requester_position.recorded_at = timestamp
        supporting_position.recorded_at = timestamp
        requester_position.quality_status = "fresh"
        supporting_position.quality_status = "fresh"

        # Keep an auditable, visible history entry for each agent. These use a
        # dedicated status so cash-velocity and ML endpoints do not mistake an
        # operational support settlement for a customer cash-in/cash-out.
        db.add_all(
            [
                Transaction(
                    agent_id=requester.id,
                    provider_code=case.provider_code,
                    event_at=timestamp,
                    type="support_cash_given",
                    amount=round(case.cash_amount),
                    location=requester.area,
                    status="coordination_completed",
                ),
                Transaction(
                    agent_id=requester.id,
                    provider_code=case.provider_code,
                    event_at=timestamp,
                    type="support_e_money_received",
                    amount=round(case.e_money_amount),
                    location=requester.area,
                    status="coordination_completed",
                ),
                Transaction(
                    agent_id=supporting.id,
                    provider_code=case.provider_code,
                    event_at=timestamp,
                    type="support_cash_received",
                    amount=round(case.cash_amount),
                    location=supporting.area,
                    status="coordination_completed",
                ),
                Transaction(
                    agent_id=supporting.id,
                    provider_code=case.provider_code,
                    event_at=timestamp,
                    type="support_e_money_given",
                    amount=round(case.e_money_amount),
                    location=supporting.area,
                    status="coordination_completed",
                ),
            ]
        )

        if case.alert_id is not None:
            linked_alert = db.get(Alert, case.alert_id)
            if linked_alert is not None and linked_alert.status != "resolved":
                post_support_forecast = calculate_liquidity_forecast(
                    db, requester_position, timestamp
                )
                safe_balance = (
                    requester_position.balance
                    >= requester_position.safety_threshold * OPERATIONAL_ATTENTION_BUFFER
                    and (
                        post_support_forecast["minutes_to_threshold"] is None
                        or post_support_forecast["minutes_to_threshold"]
                        >= 60
                    )
                )
                if safe_balance:
                    linked_alert.status = "resolved"
                    linked_alert.note = (
                        f"Provider-authorized synthetic support case {case.id} completed. "
                        f"The balance now meets the {OPERATIONAL_ATTENTION_BUFFER:g}x "
                        f"safety buffer. {payload.note.strip()}"
                    )
                else:
                    linked_alert.status = "acknowledged"
                    linked_alert.note = (
                        f"Provider-authorized synthetic support case {case.id} completed, "
                        "but the balance or forecast remains inside the operational "
                        f"attention zone and still requires follow-up. {payload.note.strip()}"
                    )

        # Reconcile both sides of the completed case. If supporting this case
        # leaves the second agent near its own threshold, that agent receives
        # a new provider-specific alert.
        reconcile_liquidity_alerts(
            db,
            timestamp,
            positions=[requester_position, supporting_position],
        )

    case.status = payload.status
    case.note = payload.note.strip() if payload.note else None
    db.commit()
    db.refresh(case)
    return coordination_response(case)


@app.get(
    "/positions",
    response_model=list[PositionResponse],
    tags=["monitoring"],
)
def list_positions(
    db: Annotated[Session, Depends(get_db)],
    agent_id: int | None = Query(None, description="Agent to inspect. Omit for the demo agent."),
    provider_code: str | None = Query(
        None, description="Limit the response to one provider's logically separate balance."
    ),
) -> list[PositionResponse]:
    """Return each provider balance with its explainable liquidity forecast."""
    agent = require_selected_agent(db, agent_id)
    provider_names = {
        provider.code: provider.display_name
        for provider in db.scalars(select(Provider)).all()
    }
    position_query = select(ProviderPosition).where(ProviderPosition.agent_id == agent.id)
    if provider_code is not None:
        position_query = position_query.where(ProviderPosition.provider_code == provider_code)
    positions = db.scalars(position_query.order_by(ProviderPosition.provider_code)).all()
    now = utc_now()
    responses: list[PositionResponse] = []
    for position in positions:
        forecast = calculate_liquidity_forecast(db, position, now)
        attention_threshold = position.safety_threshold * OPERATIONAL_ATTENTION_BUFFER
        responses.append(
            PositionResponse(
            provider_code=position.provider_code,
            display_name=provider_names[position.provider_code],
            balance=position.balance,
            total_cash=agent.shared_cash,
            safety_threshold=position.safety_threshold,
            recorded_at=position.recorded_at,
            quality_status=position.quality_status,
            attention_threshold=attention_threshold,
            requires_attention=(
                position.balance < attention_threshold
                or (
                    forecast["minutes_to_threshold"] is not None
                    and forecast["minutes_to_threshold"] < 60
                )
            ),
            forecast=forecast,
        )
        )
    return responses


@app.get("/alerts", response_model=list[AlertResponse], tags=["alerts"])
def list_alerts(
    db: Annotated[Session, Depends(get_db)],
    include_resolved: bool = Query(False, description="Include alerts already resolved by a human."),
    agent_id: int | None = Query(None, description="Agent to inspect. Omit for the demo agent."),
    provider_code: str | None = Query(
        None, description="Limit the response to one provider's routed alerts."
    ),
) -> list[AlertResponse]:
    """List alerts and the evidence supporting each advisory warning."""
    agent = require_selected_agent(db, agent_id)
    query = select(Alert).where(Alert.agent_id == agent.id)
    if provider_code is not None:
        query = query.where(Alert.provider_code == provider_code)
    if not include_resolved:
        query = query.where(Alert.status != "resolved")
    alerts = db.scalars(query.order_by(Alert.created_at.desc())).all()
    return [alert_response(alert) for alert in alerts]


@app.patch("/alerts/{alert_id}", response_model=AlertResponse, tags=["alerts"])
def update_alert(
    alert_id: int,
    payload: AlertUpdate,
    db: Annotated[Session, Depends(get_db)],
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
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int, Query(ge=1, le=100, description="Maximum number of recent synthetic transactions.")
    ] = 8,
    agent_id: int | None = Query(None, description="Agent to inspect. Omit for the demo agent."),
) -> list[TransactionResponse]:
    """Inspect synthetic transactions used as forecast evidence."""
    agent = require_selected_agent(db, agent_id)
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


@app.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["monitoring"],
)
def create_transaction(
    payload: TransactionCreate,
    db: Annotated[Session, Depends(get_db)],
) -> TransactionResponse:
    """Insert one synthetic transaction for the demo agent."""
    agent = require_agent(db)
    provider = db.get(Provider, payload.provider_code)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found.",
        )

    transaction = Transaction(
        agent_id=agent.id,
        provider_code=payload.provider_code,
        event_at=payload.event_at,
        type=payload.type,
        amount=payload.amount,
        location=payload.location,
        status=payload.status,
    )
    db.add(transaction)
    reconcile_liquidity_alerts(db, utc_now())
    db.commit()
    db.refresh(transaction)

    return TransactionResponse(
        id=transaction.id,
        provider_code=transaction.provider_code,
        type=transaction.type,
        amount=transaction.amount,
        event_at=transaction.event_at,
        location=transaction.location,
        status=transaction.status,
    )


@app.get("/cash_reserve_analysis", tags=["monitoring"])
def cash_reserve_analysis(
    db: Annotated[Session, Depends(get_db)],
    w: Annotated[
        int,
        Query(
            ge=1,
            le=30,
            description="Look-back window in minutes for cash-velocity analysis.",
        ),
    ] = 15,
    agent_id: int | None = Query(None, description="Agent to inspect. Omit for the demo agent."),
) -> dict:
    """Return shared-cash and provider e-money exhaustion estimates as JSON."""
    agent = require_selected_agent(db, agent_id)
    return calculate_cash_velocity(db=db, agent_id=agent.id, w=w)


@app.post(
    "/inference/transaction-pattern",
    response_model=TransactionPatternInferenceResponse,
    tags=["ML inference"],
)
def infer_transaction_pattern(
    payload: TransactionPatternInferenceRequest,
) -> TransactionPatternInferenceResponse:
    """Return unusual ten-minute cash-out patterns and the evidence for each."""
    try:
        artifact = load_model_artifact(TRANSACTION_MODEL_PATH)
        transactions = pd.DataFrame(
            [transaction.model_dump(mode="json") for transaction in payload.transactions]
        )
        windows = build_feature_windows(transactions)
        scored = score_feature_windows(windows, artifact)
    except (FileNotFoundError, ValueError, OSError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Transaction-pattern model is unavailable: {error}",
        ) from error

    gate = artifact.get("review_gate", {})
    minimum_cash_out_count = int(gate.get("minimum_cash_out_count", 0))
    minimum_similarity = float(gate.get("minimum_similarity_ratio", 0.0))
    findings: list[TransactionPatternFinding] = []
    for _, window in scored[scored["requires_review"]].iterrows():
        similarity_percent = round(float(window["cash_out_similarity_ratio"]) * 100)
        findings.append(
            TransactionPatternFinding(
                anomaly_type="short_term_transaction_pattern",
                provider_code=str(window["provider_code"]),
                location=str(window["location"]),
                window_start=window["window_start"].to_pydatetime(),
                anomaly_score=round(float(window["anomaly_score"]), 4),
                transaction_count=int(window["transaction_count"]),
                cash_out_count=int(window["cash_out_count"]),
                cash_out_similarity_ratio=round(
                    float(window["cash_out_similarity_ratio"]), 4
                ),
                reasons=[
                    (
                        f"The Isolation Forest score {float(window['anomaly_score']):.4f} "
                        f"exceeds the threshold {float(artifact['threshold']):.4f}."
                    ),
                    (
                        f"{int(window['cash_out_count'])} cash-outs occurred in one "
                        f"ten-minute window (minimum: {minimum_cash_out_count})."
                    ),
                    (
                        f"{similarity_percent}% of cash-out amounts were similar "
                        f"(minimum: {round(minimum_similarity * 100)}%)."
                    ),
                ],
                recommended_action=(
                    "Unusual activity detected. The transactions require review. "
                    "This may be normal demand and requires human review before action."
                    " AI can make mistakes; this is for advisory purposes only."
                ),
            )
        )

    return TransactionPatternInferenceResponse(
        model="isolation_forest",
        evaluated_window_count=len(scored),
        unusual_activity=findings,
        message=(
            f"Found {len(findings)} unusual transaction pattern(s) requiring review. "
            "AI can make mistakes; this is for advisory purposes only."
            if findings
            else "No unusual short-term transaction pattern was found."
        ),
    )


@app.post(
    "/inference/monthly-volume",
    response_model=MonthlyVolumeInferenceResponse,
    tags=["ML inference"],
)
def infer_monthly_volume(
    payload: MonthlyVolumeInferenceRequest,
) -> MonthlyVolumeInferenceResponse:
    """Return monthly volumes far above the agent's seasonal expectation."""
    try:
        artifact = load_seasonal_model_artifact(SEASONAL_MODEL_PATH)
        records = []
        for record in payload.records:
            period = record.period_start
            records.append(
                {
                    "period_start": period.isoformat(),
                    "agent_id": record.agent_id,
                    "provider_code": record.provider_code,
                    "location": record.location,
                    "event_context": record.event_context,
                    "month_number": period.month,
                    "year_index": max(0, period.year - SEASONAL_BASE_YEAR),
                    "monthly_volume": record.monthly_volume,
                }
            )
        scored = score_monthly_history(pd.DataFrame(records), artifact)
    except (FileNotFoundError, ValueError, OSError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Monthly-volume model is unavailable: {error}",
        ) from error

    ratio_threshold = float(artifact["residual_ratio_threshold"])
    findings: list[MonthlyVolumeFinding] = []
    for _, row in scored[scored["requires_review"]].iterrows():
        findings.append(
            MonthlyVolumeFinding(
                anomaly_type="unexpected_monthly_volume",
                agent_id=str(row["agent_id"]),
                provider_code=str(row["provider_code"]),
                location=str(row["location"]),
                period_start=row["period_start"].to_pydatetime(),
                event_context=str(row["event_context"]),
                actual_monthly_volume=round(float(row["monthly_volume"]), 2),
                expected_monthly_volume=round(
                    float(row["expected_monthly_volume"]), 2
                ),
                volume_ratio=round(float(row["volume_ratio"]), 2),
                reasons=[
                    (
                        f"Actual volume is {float(row['volume_ratio']):.2f}x the "
                        f"expected {row['event_context']} volume for this agent/provider."
                    ),
                    (
                        f"Actual monthly volume: {float(row['monthly_volume']):,.0f} BDT; "
                        f"expected volume: {float(row['expected_monthly_volume']):,.0f} BDT."
                    ),
                    f"The review threshold is {ratio_threshold:.2f}x expected volume.",
                ],
                recommended_action=(
                    "Confirm the operational context with the agent. The seasonal "
                    "context was considered, but the volume is still unusually high."
                ),
            )
        )

    return MonthlyVolumeInferenceResponse(
        model="seasonal_random_forest_regressor",
        evaluated_record_count=len(scored),
        unusual_activity=findings,
        message=(
            f"Found {len(findings)} unexpected monthly-volume pattern(s) requiring review."
            f" AI can make mistakes, this is for advisory purposes only."
            if findings
            else "No unexpected monthly-volume pattern was found."
        ),
    )


@app.get(
    "/inference/transaction-pattern/database",
    response_model=TransactionPatternInferenceResponse,
    tags=["ML inference"],
)
def infer_transaction_pattern_from_database(
    db: Annotated[Session, Depends(get_db)],
    w: Annotated[
        int,
        Query(
            ge=1,
            le=30,
            description="Recent database look-back window in minutes.",
        ),
    ] = 30,
    agent_id: Annotated[
        int | None,
        Query(description="Agent to analyse. Omit to use the demo agent."),
    ] = None,
) -> TransactionPatternInferenceResponse:
    """Score recent completed SQLite transactions with the saved Isolation Forest."""
    agent = require_selected_agent(db, agent_id)
    now = utc_now()
    window_start = now - timedelta(minutes=w)
    database_start = window_start.replace(tzinfo=None)
    database_end = utc_datetime(now).replace(tzinfo=None)
    database_transactions = db.scalars(
        select(Transaction)
        .where(
            Transaction.agent_id == agent.id,
            Transaction.status.in_(("completed", "failed", "pending")),
            Transaction.event_at >= database_start,
            Transaction.event_at <= database_end,
        )
        .order_by(Transaction.event_at)
    ).all()

    payload_transactions = [
        InferenceTransaction(
            provider_code=transaction.provider_code,
            event_at=utc_datetime(transaction.event_at),
            type=transaction.type,
            amount=transaction.amount,
            location=transaction.location,
            status=transaction.status,
        )
        for transaction in database_transactions
        if transaction.type in {"cash_in", "cash_out"}
        and transaction.status in {"completed", "failed", "pending"}
    ]
    if not payload_transactions:
        return TransactionPatternInferenceResponse(
            model="isolation_forest",
            evaluated_window_count=0,
            unusual_activity=[],
            message=f"No supported transactions were found for agent {agent.id} in the last {w} minutes.",
        )

    return infer_transaction_pattern(
        TransactionPatternInferenceRequest(transactions=payload_transactions)
    )


@app.get(
    "/inference/monthly-volume/database",
    response_model=MonthlyVolumeInferenceResponse,
    tags=["ML inference"],
)
def infer_monthly_volume_from_database(
    db: Annotated[Session, Depends(get_db)],
    event_context: Annotated[
        Literal["normal", "eid"],
        Query(description="Seasonal context for the selected month."),
    ] = "normal",
    year: Annotated[int | None, Query(ge=2023, le=2100)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
    agent_id: Annotated[
        int | None,
        Query(description="Agent to analyse. Omit to use the demo agent."),
    ] = None,
) -> MonthlyVolumeInferenceResponse:
    """Aggregate one month of SQLite data and score it with the seasonal model."""
    agent = require_selected_agent(db, agent_id)
    now = utc_now()
    selected_year = year or now.year
    selected_month = month or now.month
    month_start = datetime(selected_year, selected_month, 1, tzinfo=timezone.utc)
    if selected_month == 12:
        next_month_start = datetime(selected_year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month_start = datetime(selected_year, selected_month + 1, 1, tzinfo=timezone.utc)

    database_transactions = db.scalars(
        select(Transaction)
        .where(
            Transaction.agent_id == agent.id,
            Transaction.status == "completed",
            Transaction.event_at >= month_start.replace(tzinfo=None),
            Transaction.event_at < next_month_start.replace(tzinfo=None),
        )
        .order_by(Transaction.event_at)
    ).all()
    grouped_volumes: dict[tuple[str, str], float] = {}
    for transaction in database_transactions:
        key = (transaction.provider_code, transaction.location)
        grouped_volumes[key] = grouped_volumes.get(key, 0.0) + transaction.amount

    if not grouped_volumes:
        return MonthlyVolumeInferenceResponse(
            model="seasonal_random_forest_regressor",
            evaluated_record_count=0,
            unusual_activity=[],
            message=(
                f"No completed transactions were found for agent {agent.id} in "
                f"{month_start.strftime('%B %Y')}."
            ),
        )

    records = [
        MonthlyVolumeInferenceRecord(
            # The model's synthetic history uses agent_01, agent_02, etc.
            # This mapping keeps the demo-agent category consistent at inference time.
            agent_id=f"agent_{agent.id:02d}",
            provider_code=provider_code,
            location=location,
            period_start=month_start,
            event_context=event_context,
            monthly_volume=volume,
        )
        for (provider_code, location), volume in grouped_volumes.items()
    ]
    return infer_monthly_volume(MonthlyVolumeInferenceRequest(records=records))

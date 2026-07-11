from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import pandas as pd
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
    MonthlyVolumeFinding,
    MonthlyVolumeInferenceRequest,
    MonthlyVolumeInferenceResponse,
    PositionResponse,
    Provider,
    ProviderResponse,
    ProviderPosition,
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
from tools import calculate_cash_velocity, calculate_liquidity_forecast


BACKEND_DIR = Path(__file__).resolve().parent
TRANSACTION_MODEL_PATH = BACKEND_DIR / "scripts" / "isolation_forest.joblib"
SEASONAL_MODEL_PATH = BACKEND_DIR / "scripts" / "seasonal_volume_model.joblib"
SEASONAL_BASE_YEAR = 2023


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


@app.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["monitoring"],
)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
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
    w: Annotated[
        int,
        Query(
            ge=1,
            le=30,
            description="Look-back window in minutes for cash-velocity analysis.",
        ),
    ] = 15,
    db: Session = Depends(get_db),
) -> dict:
    """Return shared-cash and provider e-money exhaustion estimates as JSON."""
    agent = require_agent(db)
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
                    "Unusual activity detected and  the transactions requires review. "
                    "This may be normal demand and requires human review before action."
                    "AI can make mistakes, this is for advisory purposes only."
                ),
            )
        )

    return TransactionPatternInferenceResponse(
        model="isolation_forest",
        evaluated_window_count=len(scored),
        unusual_activity=findings,
        message=(
            f"Found {len(findings)} unusual transaction pattern(s) requiring review. AI can make mistakes, this is for advisory purposes only."
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

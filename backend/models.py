from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return the current UTC time for synthetic records."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Provider(Base):
    __tablename__ = "providers"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    shared_cash: Mapped[float] = mapped_column(Float, nullable=False)
    cash_threshold: Mapped[int] = mapped_column(Integer, nullable=False)


class ProviderPosition(Base):
    __tablename__ = "provider_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    provider_code: Mapped[str] = mapped_column(ForeignKey("providers.code"), nullable=False)
    balance: Mapped[float] = mapped_column(Float, nullable=False)
    safety_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(20), default="fresh", nullable=False)


class Transaction(Base):
    """A synthetic provider transaction. It intentionally contains no customer identifier."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    provider_code: Mapped[str] = mapped_column(ForeignKey("providers.code"), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # cash_in or cash_out
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="completed", nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    provider_code: Mapped[str] = mapped_column(ForeignKey("providers.code"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertActionStatus(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertUpdate(BaseModel):
    """The only alert state transitions exposed by this prototype."""

    status: AlertActionStatus = Field(
        description="Set the alert to acknowledged or resolved."
    )
    note: str | None = Field(
        default=None,
        max_length=500,
        description="Required when resolving an alert; records the human review outcome.",
    )

    @model_validator(mode="after")
    def resolution_requires_note(self):
        if self.status is AlertActionStatus.RESOLVED and not (self.note or "").strip():
            raise ValueError("A short resolution note is required when resolving an alert.")
        return self


# Explicit API response schemas make Swagger documentation a clear contract.
class HealthResponse(BaseModel):
    status: str


class DemoResetResponse(BaseModel):
    message: str
    agent_name: str
    alerts_created: int


class LiquidityForecastResponse(BaseModel):
    burn_per_minute: float | None
    minutes_to_threshold: float | None
    confidence: str
    reason: str


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    area: str
    shared_cash: float
    cash_threshold: int


class PositionResponse(BaseModel):
    provider_code: str
    display_name: str
    balance: float
    total_cash: float
    safety_threshold: int
    recorded_at: datetime
    quality_status: str
    forecast: LiquidityForecastResponse


class ProviderResponse(BaseModel):
    code: str
    display_name: str


class AlertResponse(BaseModel):
    id: int
    provider_code: str
    type: str
    status: AlertStatus
    title: str
    evidence: str
    recommended_action: str
    confidence: str
    note: str | None
    created_at: datetime
    updated_at: datetime


class TransactionResponse(BaseModel):
    id: int
    provider_code: str
    type: str
    amount: int
    event_at: datetime
    location: str
    status: str


class TransactionCreate(BaseModel):
    """Fields accepted when simulating a new transaction.

    The database generates ``id`` when the transaction is inserted.
    """

    provider_code: str = Field(min_length=1, max_length=30)
    type: str = Field(min_length=1, max_length=20)
    amount: int = Field(gt=0)
    event_at: datetime
    location: str = Field(min_length=1, max_length=150)
    status: str = Field(min_length=1, max_length=30)


# Stateless ML inference schemas. Requests are analysed in memory only and are
# never inserted into the SQLite database.
class InferenceTransaction(BaseModel):
    provider_code: str = Field(min_length=1, max_length=30)
    event_at: datetime
    type: Literal["cash_in", "cash_out"]
    amount: int = Field(gt=0)
    location: str = Field(min_length=1, max_length=150)
    status: Literal["completed", "failed", "pending"]


class TransactionPatternInferenceRequest(BaseModel):
    transactions: list[InferenceTransaction] = Field(
        min_length=1,
        max_length=10_000,
        description="Transactions to analyse. They are scored but never stored.",
    )


class TransactionPatternFinding(BaseModel):
    anomaly_type: Literal["short_term_transaction_pattern"]
    provider_code: str
    location: str
    window_start: datetime
    anomaly_score: float
    transaction_count: int
    cash_out_count: int
    cash_out_similarity_ratio: float
    reasons: list[str]
    recommended_action: str


class TransactionPatternInferenceResponse(BaseModel):
    model: Literal["isolation_forest"]
    evaluated_window_count: int
    unusual_activity: list[TransactionPatternFinding]
    message: str


class MonthlyVolumeInferenceRecord(BaseModel):
    agent_id: str = Field(min_length=1, max_length=100)
    provider_code: str = Field(min_length=1, max_length=30)
    location: str = Field(min_length=1, max_length=150)
    period_start: datetime
    event_context: Literal["normal", "eid"]
    monthly_volume: float = Field(gt=0)


class MonthlyVolumeInferenceRequest(BaseModel):
    records: list[MonthlyVolumeInferenceRecord] = Field(
        min_length=1,
        max_length=5_000,
        description="Monthly volumes to score. They are never stored.",
    )


class MonthlyVolumeFinding(BaseModel):
    anomaly_type: Literal["unexpected_monthly_volume"]
    agent_id: str
    provider_code: str
    location: str
    period_start: datetime
    event_context: Literal["normal", "eid"]
    actual_monthly_volume: float
    expected_monthly_volume: float
    volume_ratio: float
    reasons: list[str]
    recommended_action: str


class MonthlyVolumeInferenceResponse(BaseModel):
    model: Literal["seasonal_random_forest_regressor"]
    evaluated_record_count: int
    unusual_activity: list[MonthlyVolumeFinding]
    message: str


class OverviewResponse(BaseModel):
    agent: AgentResponse
    positions: list[PositionResponse]
    alerts: list[AlertResponse]
    recent_transactions: list[TransactionResponse]

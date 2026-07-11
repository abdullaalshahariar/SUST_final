from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pydantic import BaseModel, ConfigDict, Field, field_validator
from enum import Enum
from typing import Annotated

class Base(DeclarativeBase):
    pass


# class Provider(Base):
#     __tablename__ = "providers"

#     code: Mapped[str] = mapped_column(String(30), primary_key=True)
#     display_name: Mapped[str] = mapped_column(String(80), nullable=False)
#     is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

# /trsnsactions Enum
class Provider(str, Enum):
    BKASH = "bkash"
    NAGAD = "nagad"
    ROCKET = "rocket"

class TransactionType(str, Enum):
    CASHOUT = "cashout"
    CASHIN = "cashin"

class Status(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class TransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(min_length=1, max_length=64)
    agent_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    provider: Provider
    transaction_type: TransactionType
    amount: float = Field(gt=0)
    timestamp: datetime
    location: str = Field(min_length=1, max_length=200)
    status: Status

    @field_validator("transaction_id", "agent_id", "customer_id", "location")
    @classmethod
    def strip_and_reject_blank(cls, value: str):
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

class TransactionResponse(BaseModel):
    transaction_id: str
    agent_id: str
    timestamp: datetime

class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)



# class Agent(Base):
#     __tablename__ = "agents"

#     id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
#     name: Mapped[str] = mapped_column(String(100), nullable=False)
#     area: Mapped[str] = mapped_column(String(100), nullable=False)
#     shared_cash_threshold: Mapped[int] = mapped_column(
#         Integer, default=20_000, nullable=False
#     )
#     status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
#     created_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True),
#         default=lambda: datetime.now(timezone.utc),
#         nullable=False,
#     )

# class AgentStatus(str, Enum):
#     ACTIVE = "active"
#     UNAVAILABLE = "unavailable"
#     CLOSED = "closed"


# AgentName = Annotated[str, Field(min_length=2, max_length=100)]
# AreaName = Annotated[str, Field(min_length=2, max_length=100)]
# NonNegativeMoney = Annotated[int, Field(ge=0)]


# class AgentCreate(BaseModel):
#     name: AgentName
#     area: AreaName
#     shared_cash_threshold: NonNegativeMoney = 20_000
#     status: AgentStatus = AgentStatus.ACTIVE


# class AgentResponse(AgentCreate):
#     model_config = ConfigDict(from_attributes=True)

#     id: int
#     created_at: datetime
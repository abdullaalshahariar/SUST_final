from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
from typing import Annotated

class Base(DeclarativeBase):
    pass


class Provider(Base):
    __tablename__ = "providers"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    shared_cash_threshold: Mapped[int] = mapped_column(
        Integer, default=20_000, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

class AgentStatus(str, Enum):
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    CLOSED = "closed"


AgentName = Annotated[str, Field(min_length=2, max_length=100)]
AreaName = Annotated[str, Field(min_length=2, max_length=100)]
NonNegativeMoney = Annotated[int, Field(ge=0)]


class AgentCreate(BaseModel):
    name: AgentName
    area: AreaName
    shared_cash_threshold: NonNegativeMoney = 20_000
    status: AgentStatus = AgentStatus.ACTIVE


class AgentResponse(AgentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
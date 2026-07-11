from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models import Agent, Alert, Base, Provider, ProviderPosition, Transaction, utc_now


BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_PATH = DATA_DIR / "mvp.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def reset_demo_data() -> tuple[str, int]:
    """Recreate the fixed, synthetic Scenario 1 dataset."""
    from tools import create_liquidity_alerts

    # The database contains synthetic demo data only. Recreate its schema so a
    # previous prototype schema cannot leak into this deterministic scenario.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    now = utc_now()

    with SessionLocal() as db:
        db.add_all(
            [
                Provider(code="bkash_sim", display_name="bKash (simulated)"),
                Provider(code="nagad_sim", display_name="Nagad (simulated)"),
                Provider(code="rocket_sim", display_name="Rocket (simulated)"),
            ]
        )
        agent = Agent(
            name="Zindabazar Super Agent",
            area="Sylhet",
            shared_cash=70_000,
            cash_threshold=20_000,
        )
        db.add(agent)
        db.flush()

        db.add_all(
            [
                ProviderPosition(agent_id=agent.id, provider_code="bkash_sim", balance=45_000, safety_threshold=10_000, recorded_at=now, quality_status="fresh"),
                ProviderPosition(agent_id=agent.id, provider_code="nagad_sim", balance=13_000, safety_threshold=10_000, recorded_at=now, quality_status="fresh"),
                ProviderPosition(agent_id=agent.id, provider_code="rocket_sim", balance=30_000, safety_threshold=10_000, recorded_at=now, quality_status="fresh"),
            ]
        )

        # These five cash-ins total 3,750 BDT in 15 minutes: 250 BDT/minute.
        for minutes_ago, amount in ((1, 750), (3, 750), (6, 750), (10, 750), (14, 750)):
            db.add(
                Transaction(
                    agent_id=agent.id,
                    provider_code="nagad_sim",
                    event_at=now - timedelta(minutes=minutes_ago),
                    type="cash_in",
                    amount=amount,
                    location="Zindabazar, Sylhet",
                    status="completed",
                )
            )

        db.flush()
        alerts = create_liquidity_alerts(db, now)
        db.commit()
        return agent.name, len(alerts)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
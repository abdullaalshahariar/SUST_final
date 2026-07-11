import csv
from calendar import monthrange
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models import Agent, Alert, Base, Provider, ProviderPosition, Transaction, utc_now


BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_PATH = DATA_DIR / "mvp.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
SCENARIO2_DATA_PATH = BACKEND_DIR / "scripts" / "scenario2_transactions.csv"

DEMO_AGENT_AREAS = (
    "Zindabazar, Sylhet",
    "Ambarkhana, Sylhet",
    "Shahjalal Uposhahar, Sylhet",
)

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


def _seed_demo_agents(db: Session, now: datetime) -> list[Agent]:
    """Create agents whose IDs match the synthetic seasonal-model categories."""
    agents = [
        Agent(
            name="Zindabazar Super Agent" if index == 1 else f"Sylhet Demo Agent {index:02d}",
            area=DEMO_AGENT_AREAS[(index - 1) % len(DEMO_AGENT_AREAS)],
            shared_cash=70_000 if index == 1 else 65_000 + (index % 5) * 5_000,
            cash_threshold=20_000,
        )
        for index in range(1, 19)
    ]
    db.add_all(agents)
    db.flush()

    positions: list[ProviderPosition] = []
    for agent in agents:
        for provider_code, balance in (
            ("bkash_sim", 45_000),
            ("nagad_sim", 13_000 if agent.id == 1 else 35_000),
            ("rocket_sim", 30_000),
        ):
            positions.append(
                ProviderPosition(
                    agent_id=agent.id,
                    provider_code=provider_code,
                    balance=balance,
                    safety_threshold=10_000,
                    recorded_at=now,
                    quality_status="fresh",
                )
            )
    db.add_all(positions)
    return agents


def _seed_scenario2_history(db: Session, agents: list[Agent], now: datetime) -> int:
    """Import thousands of generated Scenario 2 rows and distribute them by agent."""
    if not SCENARIO2_DATA_PATH.exists():
        return 0

    count = 0
    with SCENARIO2_DATA_PATH.open(newline="", encoding="utf-8") as source:
        current_month_index = now.year * 12 + (now.month - 1)
        for index, row in enumerate(csv.DictReader(source)):
            source_time = datetime.fromisoformat(row["event_at"].replace("Z", "+00:00"))
            # Spread the large training-style dataset across the 36 completed
            # months before the current month. This gives every agent useful
            # history without turning a few days of data into one huge month.
            historical_month_index = current_month_index - 36 + (index % 36)
            year, month_zero_index = divmod(historical_month_index, 12)
            month = month_zero_index + 1
            event_at = source_time.replace(
                year=year,
                month=month,
                day=min(source_time.day, monthrange(year, month)[1]),
            )
            # A block of 36 rows gives each agent records across every month.
            agent = agents[(index // 36) % len(agents)]
            db.add(
                Transaction(
                    agent_id=agent.id,
                    provider_code=row["provider_code"],
                    event_at=event_at,
                    type=row["type"],
                    amount=int(row["amount"]),
                    # Each imported row belongs to the assigned agent's outlet.
                    # Keeping one consistent area per agent makes seasonal
                    # provider/location comparisons meaningful.
                    location=agent.area,
                    status=row["status"],
                )
            )
            count += 1
    return count


def _seed_current_demo_events(db: Session, agents: list[Agent], now: datetime) -> int:
    """Add current-time records so API demos work without editing the database."""
    transaction_count = 0

    # Scenario 1: agent 1's Nagad e-money burns at 250 BDT/minute.
    for minutes_ago, amount in ((1, 750), (3, 750), (6, 750), (10, 750), (14, 750)):
        db.add(
            Transaction(
                agent_id=agents[0].id,
                provider_code="nagad_sim",
                event_at=now - timedelta(minutes=minutes_ago),
                type="cash_in",
                amount=amount,
                location="Zindabazar, Sylhet",
                status="completed",
            )
        )
        transaction_count += 1

    # Scenario 2: agent 2 has a short-term pattern entirely inside one
    # ten-minute bucket, so the ML feature window consistently sees all 12.
    current_bucket_start = now.replace(
        minute=(now.minute // 10) * 10,
        second=0,
        microsecond=0,
    )
    pattern_bucket_start = (
        current_bucket_start - timedelta(minutes=10)
        if now - current_bucket_start < timedelta(minutes=3)
        else current_bucket_start
    )
    for index in range(12):
        db.add(
            Transaction(
                agent_id=agents[1].id,
                provider_code="nagad_sim",
                event_at=pattern_bucket_start + timedelta(seconds=60 + index * 10),
                type="cash_out",
                amount=5_000,
                location="Ambarkhana, Sylhet",
                status="completed",
            )
        )
        transaction_count += 1

    # Scenario 3: agent 3 has an unusually high volume for the current month.
    db.add(
        Transaction(
            agent_id=agents[2].id,
            provider_code="bkash_sim",
            event_at=now - timedelta(minutes=5),
            type="cash_out",
            amount=1_000_000,
            location="Shahjalal Uposhahar, Sylhet",
            status="completed",
        )
    )
    return transaction_count + 1


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
        agents = _seed_demo_agents(db, now)
        _seed_scenario2_history(db, agents, now)
        _seed_current_demo_events(db, agents, now)

        db.flush()
        alerts = create_liquidity_alerts(db, now)
        db.commit()
        return agents[0].name, len(alerts)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

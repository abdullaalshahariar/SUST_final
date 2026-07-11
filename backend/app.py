from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from sqlalchemy import select

from db import SessionLocal, init_db
from models import Agent, AgentCreate, AgentResponse, Provider


SIMULATED_PROVIDERS = [
    ("bkash_sim", "bKash (simulated)"),
    ("nagad_sim", "Nagad (simulated)"),
    ("rocket_sim", "Rocket (simulated)"),
]


def seed_providers() -> None:
    with SessionLocal() as db:
        for code, display_name in SIMULATED_PROVIDERS:
            if db.get(Provider, code) is None:
                db.add(
                    Provider(
                        code=code,
                        display_name=display_name,
                        is_active=True,
                    )
                )
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_providers()
    yield


app = FastAPI(
    title="Liquidity Monitor",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/providers")
def list_providers():
    with SessionLocal() as db:
        providers = db.scalars(
            select(Provider).order_by(Provider.code)
        ).all()

        return [
            {
                "code": provider.code,
                "display_name": provider.display_name,
                "is_active": provider.is_active,
            }
            for provider in providers
        ]
    
@app.post(
    "/agents",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent(payload: AgentCreate):
    with SessionLocal() as db:
        agent = Agent(
            name=payload.name.strip(),
            area=payload.area.strip(),
            shared_cash_threshold=payload.shared_cash_threshold,
            status=payload.status,
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)
        return agent
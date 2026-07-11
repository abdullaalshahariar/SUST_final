from fastapi import FastAPI, HTTPException, status
from sqlalchemy.exc import IntegrityError

from db import SessionLocal, init_db
from models import Transaction, TransactionRequest, TransactionResponse
from contextlib import asynccontextmanager


# SIMULATED_PROVIDERS = [
#     ("bkash_sim", "bKash (simulated)"),
#     ("nagad_sim", "Nagad (simulated)"),
#     ("rocket_sim", "Rocket (simulated)"),
# ]


# def seed_providers() -> None:
#     with SessionLocal() as db:
#         for code, display_name in SIMULATED_PROVIDERS:
#             if db.get(Provider, code) is None:
#                 db.add(
#                     Provider(
#                         code=code,
#                         display_name=display_name,
#                         is_active=True,
#                     )
#                 )
#         db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Liquidity Monitor",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/transactions",
          response_model=TransactionResponse,
          status_code=status.HTTP_201_CREATED
          )
async def create_transaction(payload: TransactionRequest):
    with SessionLocal() as db:
        transaction = Transaction(
            transaction_id=payload.transaction_id,
            agent_id=payload.agent_id,
            customer_id=payload.customer_id,
            provider=payload.provider.value,
            transaction_type=payload.transaction_type.value,
            amount=payload.amount,
            timestamp=payload.timestamp,
            location=payload.location,
            status=payload.status.value,
        )

        try:
            with SessionLocal.begin() as db:
                db.add(transaction)
                db.flush()  # runs the INSERT now, before the transaction commits
                db.commit()
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A transaction with this transaction_id already exists.",
            )
        
        return TransactionResponse(
            transaction_id=transaction.transaction_id,
            agent_id=transaction.agent_id,
            timestamp=transaction.timestamp,
        )

# @app.get("/providers")
# def list_providers():
#     with SessionLocal() as db:
#         providers = db.scalars(
#             select(Provider).order_by(Provider.code)
#         ).all()

#         return [
#             {
#                 "code": provider.code,
#                 "display_name": provider.display_name,
#                 "is_active": provider.is_active,
#             }
#             for provider in providers
#         ]
    
# @app.post(
#     "/agents",
#     response_model=AgentResponse,
#     status_code=status.HTTP_201_CREATED,
# )
# def create_agent(payload: AgentCreate):
#     with SessionLocal() as db:
#         agent = Agent(
#             name=payload.name.strip(),
#             area=payload.area.strip(),
#             shared_cash_threshold=payload.shared_cash_threshold,
#             status=payload.status,
#         )
#         db.add(agent)
#         db.commit()
#         db.refresh(agent)
#         return agent


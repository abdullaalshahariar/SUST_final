# Multi-Provider Agent Liquidity Monitor

This is a synthetic, advisory-only backend for multi-provider mobile-finance
agents. It keeps bKash, Nagad, and Rocket balances logically separate while
showing shared physical cash, predicted liquidity pressure, unusual activity,
and human-review alert coordination.

It does not connect to real wallets, access customer credentials, transfer
money, block users, or make fraud decisions.

## Run the backend

```bash
cd backend
../venv/bin/uvicorn app:app --reload
```

Open Swagger at `http://127.0.0.1:8000/docs`, then call `POST /demo/reset`.

## Architecture

```text
SQLite transactions and positions
        │
        ├─ deterministic cash-velocity calculation → liquidity alert
        ├─ Isolation Forest → unusual ten-minute transaction pattern
        └─ Seasonal Random Forest → unexpected monthly volume
        │
FastAPI JSON endpoints → human review and resolution workflow
```

All data is generated and synthetic. ML models are trained offline from the
CSV generators in `backend/scripts/` and saved as `.joblib` artifacts. At
runtime, database inference endpoints score current SQLite data; they do not
retrain the models automatically.

## Measured metrics

Call `GET /metrics` in Swagger to see the latest values and plain-English
definitions. The endpoint reads the saved evaluation files produced during
training.

| Metric | Current result | Meaning |
|---|---:|---|
| Transaction-pattern precision | 1.00 | Every flagged injected short-term pattern was a true injected anomaly in this synthetic evaluation. |
| Transaction-pattern recall | 1.00 | The short-term model detected every injected unusual window in this synthetic evaluation. |
| Transaction-pattern false-positive rate | 0.00 | No normal ten-minute window was incorrectly flagged in this synthetic evaluation. |
| Legitimate-surge flag rate | 0.00 | No simulated normal high-demand surge was incorrectly flagged. |
| Seasonal monthly-volume precision | 1.00 | Every flagged injected monthly-volume anomaly was a true injected anomaly in this synthetic evaluation. |
| Normal Eid-month flag rate | 0.00 | No normal simulated Eid month was incorrectly flagged. |
| Seasonal validation MAE | 12,061.77 BDT | Average prediction error on held-out normal synthetic monthly-volume data; lower is better. |

These metrics are not claims of real-world fraud-detection accuracy. They are
measured only on generated synthetic scenarios and are used to demonstrate
model behaviour, false-positive awareness, and seasonal context handling.

## Main demonstration endpoints

```text
POST /demo/reset
POST /demo/simulate-stale-balance?provider_code=nagad_sim
GET  /positions
GET  /agents/{agent_id}
GET  /agents
GET  /cash_reserve_analysis?w=15
GET  /alerts
PATCH /alerts/{alert_id}
GET  /inference/transaction-pattern/database?agent_id=2&w=30
GET  /inference/monthly-volume/database?agent_id=3&year=2026&month=7&event_context=normal
GET  /metrics
GET  /provider-coordination
POST /provider-coordination/proposals
PATCH /provider-coordination/{case_id}
```

# 12-Hour MVP Plan: Multi-Provider Agent Liquidity Monitor

## 1. Outcome and scope

Build a **simulated decision-support dashboard** for an agent/outlet that serves multiple, logically separate providers. It shows:

- shared physical cash and each provider's separate e-money position;
- projected liquidity pressure in the next 20, 60, and 180 minutes;
- unusual transaction activity that **requires review**;
- a case workflow with acknowledgement, assignment, escalation, notes, and resolution;
- lower confidence when a provider feed is stale or invalid.

This MVP performs **no real transaction, transfer, wallet conversion, blocking, or fraud decision**. Provider names and all data are simulated.

### Build priorities

| Priority | Must work in the demo |
|---|---|
| P0 | Seed one agent, three simulated providers, cash/positions, and transactions directly into SQLite. |
| P0 | Dashboard projects a provider or cash shortage and explains the evidence. |
| P0 | At least one unusual-activity alert is generated and says `requires_review`, never `fraud`. |
| P0 | Alert can be acknowledged, assigned, escalated, and resolved with notes. |
| P0 | A stale/missing provider feed visibly lowers confidence and recommends review. |
| P1 | Filters by provider, agent, area, time, and alert status. |
| P1 | Isolation Forest anomaly scoring and model metrics. |
| P2 | Bengali/Banglish alert text, charts, Docker, and authentication. |

Do **not** build real provider integrations, authentication, an LLM, complex permissions, or a full forecasting service in the first 12 hours.

## 2. Architecture

```text
Browser dashboard
       │ REST/JSON
       ▼
FastAPI application
 ├─ router: dashboard / transactions / positions / alerts / cases / dev
 ├─ service: liquidity forecast, anomaly score, alert creation
 ├─ repository: SQLAlchemy + SQLite
 └─ seed: deterministic simulated events and scenarios
       │
       ▼
SQLite: backend/data/mvp.db
```

Use a request-time calculation for the forecast and anomaly score. Persist the resulting alert and its evidence. This avoids queues, Redis, Celery, and scheduled workers for the MVP.

## 3. Recommended project structure

Replace the empty flat backend placeholders with this small package structure.

```text
SUST_final/
├── MVP_BUILD_PLAN.md
├── README.md
├── docker-compose.yml                    # optional: add only after local run works
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                       # FastAPI app and router registration
│   │   ├── database.py                   # engine, SessionLocal, init_db
│   │   ├── enums.py                      # all API/domain enums below
│   │   ├── orm_models.py                 # SQLAlchemy tables
│   │   ├── schemas.py                    # Pydantic request/response models
│   │   ├── dependencies.py               # get_db, validation helpers
│   │   ├── routers/
│   │   │   ├── dashboard.py
│   │   │   ├── transactions.py
│   │   │   ├── positions.py
│   │   │   ├── alerts.py
│   │   │   ├── cases.py
│   │   │   └── dev.py                    # seed/reset; development only
│   │   ├── services/
│   │   │   ├── liquidity.py
│   │   │   ├── anomalies.py
│   │   │   ├── alerts.py
│   │   │   └── simulation.py
│   │   └── seed.py
│   ├── data/                             # ignored by Git except .gitkeep
│   │   └── mvp.db
│   └── tests/
│       ├── test_liquidity.py
│       └── test_api.py
└── frontend/
    ├── index.html
    ├── style.css
    └── script.js                         # fetches API; vanilla JS is enough
```

Suggested dependencies: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `pydantic`, `scikit-learn`, and `pytest`. Use `sqlite:///./data/mvp.db` and configure SQLite `check_same_thread=False`.

## 4. SQLite data model

Store all timestamps as UTC ISO-8601 text (`2026-07-11T10:30:00Z`). SQLite does not enforce native enums, so validate all enum values in Pydantic and optionally add `CHECK` constraints in SQLAlchemy.

### Tables

| Table | Purpose | Key fields |
|---|---|---|
| `providers` | Simulated provider catalogue | `code`, `display_name`, `is_active` |
| `agents` | Outlet and shared-cash identity | `id`, `name`, `area`, `shared_cash_threshold`, `status` |
| `provider_positions` | Time-series provider e-money position | `agent_id`, `provider_code`, `e_money_balance`, `safety_threshold`, `recorded_at`, `quality_status` |
| `cash_snapshots` | Time-series shared physical cash | `agent_id`, `physical_cash`, `recorded_at`, `quality_status` |
| `transactions` | Simulated immutable transaction events | `id`, `agent_id`, `provider_code`, `event_at`, `type`, `amount`, `account_hash` |
| `alerts` | Human-review operational alert | `id`, `agent_id`, `provider_code`, `type`, `severity`, `status`, `confidence`, `recommended_action` |
| `alert_evidence` | Evidence displayed in the UI | `alert_id`, `key`, `value_text`, `value_number`, `message` |
| `cases` | Ownership and lifecycle for one alert | `id`, `alert_id`, `owner_role`, `assignee`, `status`, `priority` |
| `case_notes` | Append-only human notes | `case_id`, `author`, `body`, `created_at` |
| `model_runs` | Optional reproducibility for the ML model | `id`, `model_name`, `trained_at`, `train_rows`, `metrics_json` |

### Important relationships and indexes

```text
agents 1 ── * provider_positions
agents 1 ── * cash_snapshots
agents 1 ── * transactions
agents 1 ── * alerts
alerts 1 ── * alert_evidence
alerts 1 ── 0..1 cases
cases 1 ── * case_notes
```

Create these indexes from the start:

```sql
CREATE INDEX ix_tx_agent_time ON transactions(agent_id, event_at DESC);
CREATE INDEX ix_tx_provider_time ON transactions(provider_code, event_at DESC);
CREATE INDEX ix_position_agent_provider_time
  ON provider_positions(agent_id, provider_code, recorded_at DESC);
CREATE INDEX ix_cash_agent_time ON cash_snapshots(agent_id, recorded_at DESC);
CREATE INDEX ix_alert_status_time ON alerts(status, created_at DESC);
CREATE UNIQUE INDEX ux_open_alert_dedupe
  ON alerts(agent_id, provider_code, type, status)
  WHERE status IN ('new', 'acknowledged', 'assigned', 'escalated');
```

`account_hash` and `device_hash` are generated fake identifiers, not real identities. Do not store phone numbers, PINs, OTPs, or credentials.

## 5. API enums (`app/enums.py`)

```python
from enum import Enum


class ProviderCode(str, Enum):
    BKASH = "bkash_sim"
    NAGAD = "nagad_sim"
    ROCKET = "rocket_sim"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    CLOSED = "closed"


class TransactionType(str, Enum):
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"
    PAYMENT = "payment"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    REVERSAL = "reversal"


class TransactionStatus(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"
    REVERSED = "reversed"
    REJECTED = "rejected"


class DataQualityStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"
    CONFLICTING = "conflicting"


class AlertType(str, Enum):
    PROVIDER_LIQUIDITY_PRESSURE = "provider_liquidity_pressure"
    SHARED_CASH_PRESSURE = "shared_cash_pressure"
    UNUSUAL_TRANSACTION_ACTIVITY = "unusual_transaction_activity"
    DATA_QUALITY = "data_quality"
    AGENT_UNAVAILABLE = "agent_unavailable"


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    ASSIGNED = "assigned"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OwnerRole(str, Enum):
    AGENT = "agent"
    FIELD_OFFICER = "field_officer"
    PROVIDER_OPERATIONS = "provider_operations"
    RISK_REVIEW = "risk_review"
    MANAGER = "manager"


class CasePriority(str, Enum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


class CaseStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class LanguageCode(str, Enum):
    EN = "en"
    BN = "bn"
    BANGLISH = "banglish"
```

## 6. Pydantic API contracts (`app/schemas.py`)

Use Pydantic v2. Money is represented as non-negative `float` for the prototype; in a production financial system use integer minor units or `Decimal`.

```python
from datetime import datetime
from typing import Annotated, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    AgentStatus, AlertSeverity, AlertStatus, AlertType, CasePriority,
    CaseStatus, ConfidenceLevel, DataQualityStatus, LanguageCode, OwnerRole,
    ProviderCode, TransactionStatus, TransactionType,
)

Money = Annotated[float, Field(ge=0, le=10_000_000)]
PositiveAmount = Annotated[float, Field(gt=0, le=10_000_000)]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ProviderResponse(APIModel):
    code: ProviderCode
    display_name: str
    is_active: bool


class AgentCreate(APIModel):
    name: str = Field(min_length=2, max_length=100)
    area: str = Field(min_length=2, max_length=100)
    shared_cash_threshold: Money = 20_000
    status: AgentStatus = AgentStatus.ACTIVE


class AgentResponse(AgentCreate):
    id: int
    created_at: datetime


class ProviderPositionCreate(APIModel):
    agent_id: int = Field(gt=0)
    provider_code: ProviderCode
    e_money_balance: Money
    safety_threshold: Money = 10_000
    recorded_at: datetime
    quality_status: DataQualityStatus = DataQualityStatus.FRESH
    source_event_id: str | None = Field(default=None, max_length=80)


class ProviderPositionResponse(ProviderPositionCreate):
    id: int
    age_minutes: float = Field(ge=0)


class CashSnapshotCreate(APIModel):
    agent_id: int = Field(gt=0)
    physical_cash: Money
    recorded_at: datetime
    quality_status: DataQualityStatus = DataQualityStatus.FRESH


class CashSnapshotResponse(CashSnapshotCreate):
    id: int
    age_minutes: float = Field(ge=0)


class TransactionCreate(APIModel):
    id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    agent_id: int = Field(gt=0)
    provider_code: ProviderCode
    event_at: datetime
    type: TransactionType
    amount: PositiveAmount
    status: TransactionStatus = TransactionStatus.COMPLETED
    account_hash: str | None = Field(default=None, max_length=64)
    device_hash: str | None = Field(default=None, max_length=64)
    channel: str = Field(default="agent_counter", max_length=40)
    source_event_id: str | None = Field(default=None, max_length=80)

    @field_validator("account_hash", "device_hash")
    @classmethod
    def hashes_must_not_look_like_phone_numbers(cls, value: str | None):
        if value and value.replace("+", "").isdigit():
            raise ValueError("Use a synthetic hash, not a phone number or identifier")
        return value


class TransactionResponse(TransactionCreate):
    created_at: datetime


class ForecastPoint(APIModel):
    horizon_minutes: int = Field(gt=0)
    projected_physical_cash: float
    projected_provider_balance: float | None = None
    shortage_risk: bool
    expected_shortage_at: datetime | None = None
    confidence: ConfidenceLevel


class EvidenceItem(APIModel):
    key: str = Field(min_length=1, max_length=60)
    message: str = Field(min_length=1, max_length=300)
    value_number: float | None = None
    value_text: str | None = Field(default=None, max_length=120)


class AlertResponse(APIModel):
    id: int
    agent_id: int
    provider_code: ProviderCode | None = None
    type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    title: str
    message: str
    confidence: ConfidenceLevel
    confidence_score: float = Field(ge=0, le=1)
    recommended_action: str
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceItem]


class AlertListQuery(APIModel):
    agent_id: int | None = Field(default=None, gt=0)
    provider_code: ProviderCode | None = None
    status: AlertStatus | None = None
    severity: AlertSeverity | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class AlertStatusUpdate(APIModel):
    status: AlertStatus
    actor: str = Field(min_length=2, max_length=80)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def resolution_requires_note(self):
        if self.status in {AlertStatus.RESOLVED, AlertStatus.DISMISSED} and not self.note:
            raise ValueError("A resolution or dismissal needs a note")
        return self


class CaseCreate(APIModel):
    alert_id: int = Field(gt=0)
    owner_role: OwnerRole
    assignee: str | None = Field(default=None, max_length=80)
    priority: CasePriority = CasePriority.P2
    language: LanguageCode = LanguageCode.EN


class CaseUpdate(APIModel):
    owner_role: OwnerRole | None = None
    assignee: str | None = Field(default=None, max_length=80)
    priority: CasePriority | None = None
    status: CaseStatus | None = None


class CaseNoteCreate(APIModel):
    author: str = Field(min_length=2, max_length=80)
    body: str = Field(min_length=1, max_length=1000)


class CaseNoteResponse(CaseNoteCreate):
    id: int
    created_at: datetime


class CaseResponse(APIModel):
    id: int
    alert_id: int
    owner_role: OwnerRole
    assignee: str | None
    priority: CasePriority
    status: CaseStatus
    created_at: datetime
    updated_at: datetime
    notes: list[CaseNoteResponse] = []


class DashboardResponse(APIModel):
    agent: AgentResponse
    latest_cash: CashSnapshotResponse | None
    latest_positions: list[ProviderPositionResponse]
    forecasts: list[ForecastPoint]
    open_alerts: list[AlertResponse]
    data_quality: DataQualityStatus
    generated_at: datetime


class SimulationSeedRequest(APIModel):
    seed: int = Field(default=20260711, ge=1)
    days: int = Field(default=7, ge=1, le=31)
    agent_count: int = Field(default=3, ge=1, le=20)
    include_liquidity_scenario: bool = True
    include_unusual_activity_scenario: bool = True
    include_stale_feed_scenario: bool = True


class SimulationSeedResponse(APIModel):
    agents_created: int
    transactions_created: int
    positions_created: int
    cash_snapshots_created: int
    scenario_summary: dict[str, int]
```

## 7. Endpoint specification

All success responses are JSON. Invalid input returns FastAPI's `422`; unknown resources return `404`; duplicate transaction ID returns `409`.

| Method and path | Request | Response | Behaviour |
|---|---|---|---|
| `GET /health` | — | `{ "status": "ok" }` | Used before the demo. |
| `GET /providers` | — | `list[ProviderResponse]` | Return simulated providers. |
| `POST /agents` | `AgentCreate` | `AgentResponse`, `201` | Create a demo outlet. |
| `GET /agents/{agent_id}` | — | `AgentResponse` | Outlet metadata. |
| `POST /positions` | `ProviderPositionCreate` | `ProviderPositionResponse`, `201` | Insert a provider position snapshot. |
| `POST /cash-snapshots` | `CashSnapshotCreate` | `CashSnapshotResponse`, `201` | Insert shared cash snapshot. |
| `POST /transactions` | `TransactionCreate` | `TransactionResponse`, `201` | Persist event; calculate/recalculate relevant alerts. |
| `GET /transactions` | `agent_id`, optional `provider_code`, `from`, `to`, `limit` | `list[TransactionResponse]` | Transaction feed for drill-down. |
| `GET /dashboard/{agent_id}` | optional `at` | `DashboardResponse` | Main page; position, forecast, quality, active alerts. |
| `GET /agents/{agent_id}/forecast` | optional `provider_code`, `horizons=20,60,180` | `list[ForecastPoint]` | Explicit forecast endpoint. |
| `GET /alerts` | `AlertListQuery` query parameters | `list[AlertResponse]` | Alert queue and filters. |
| `GET /alerts/{alert_id}` | — | `AlertResponse` | Evidence for one alert. |
| `PATCH /alerts/{alert_id}/status` | `AlertStatusUpdate` | `AlertResponse` | Acknowledge, assign state, escalate, resolve, dismiss. |
| `POST /cases` | `CaseCreate` | `CaseResponse`, `201` | Create one case for an alert. |
| `GET /cases/{case_id}` | — | `CaseResponse` | Case and notes. |
| `PATCH /cases/{case_id}` | `CaseUpdate` | `CaseResponse` | Assign owner and update lifecycle. |
| `POST /cases/{case_id}/notes` | `CaseNoteCreate` | `CaseNoteResponse`, `201` | Append an audit note. |
| `POST /dev/seed` | `SimulationSeedRequest` | `SimulationSeedResponse` | Seed SQLite; development/demo only. |
| `POST /dev/reset` | — | `{ "deleted": true }` | Delete only the local simulated database; development/demo only. |

### Required endpoint behaviours

1. `POST /transactions` never changes a real balance. It stores a simulated event only.
2. A new cash-out or provider position may create/update a liquidity alert; do not create duplicate open alerts of the same type/provider.
3. Data quality is `STALE` when a latest snapshot is older than 15 minutes in the simulated timeline; it is `MISSING` when no position is available.
4. `PATCH /alerts/{id}/status` should add the supplied note to the case when a case exists. If it does not exist, retain the status change and record the actor in the alert audit fields.
5. `POST /cases` should set alert status to `ASSIGNED`; `CaseStatus.ESCALATED` should set alert status to `ESCALATED`; resolving a case should require a note and set its alert to `RESOLVED`.

## 8. Analytics method to implement

### Liquidity forecast (P0; deterministic and explainable)

For every agent/provider, query completed transactions in the latest 60 simulated minutes:

```text
cash_out_rate = sum(CASH_OUT amounts in lookback) / 60
cash_in_rate  = sum(CASH_IN amounts in lookback) / 60
net_cash_burn_per_minute = max(cash_out_rate - cash_in_rate, 0)

projected_shared_cash(h) = current_shared_cash - h * net_cash_burn_per_minute
projected_provider_balance(h) = current_provider_balance - h * provider_net_outflow_rate
```

Create `SHARED_CASH_PRESSURE` when projected cash goes below `agents.shared_cash_threshold`. Create `PROVIDER_LIQUIDITY_PRESSURE` when a provider position goes below its `safety_threshold`. Estimate `expected_shortage_at` only if the relevant burn rate is greater than zero.

Confidence starts at `HIGH` and is downgraded:

- `MEDIUM` if one required feed is 5–15 minutes old;
- `LOW` if any required feed is stale, missing, or conflicting;
- `LOW` if fewer than 10 completed transactions are available in the 60-minute lookback.

Evidence for every liquidity alert must include current balance, threshold, cash-out rate, cash-in rate, horizon, source age, and confidence reason.

### Anomaly detection (P1; add only after P0 works)

Build a feature vector per completed transaction:

```text
log1p(amount), hour_of_day, transaction_type,
count_same_agent_15m, total_cashout_agent_15m,
count_same_account_15m, repeated_amount_count_15m,
time_since_agent_previous_txn, provider_balance_to_threshold_ratio
```

Train `sklearn.ensemble.IsolationForest(contamination=0.03, random_state=20260711)` on normal simulated transactions only. Persist `anomaly_score`, but display it as `unusualness_score`. Create an `UNUSUAL_TRANSACTION_ACTIVITY` alert when the score crosses the selected threshold or when a transparent backup rule triggers (for example, 5+ same-amount cash-outs from the same account in 15 minutes).

The anomaly alert should show rule-derived evidence, not claim that the model proves fraud. Example:

> Unusual cash-out pattern requires review: 7 transactions of 10,000 BDT from the same simulated account in 15 minutes; this is above the outlet's normal frequency.

## 9. Synthetic data seeded directly into SQLite

Do not use CSV files. `POST /dev/seed` or `python -m app.seed` writes deterministic records directly through SQLAlchemy.

Seed a small but visually convincing scenario:

- 3 agents in different areas; 3 simulated providers per agent;
- 7 days of normal history (roughly 1,000–3,000 transactions is enough);
- a cash-out peak between 16:00–19:00;
- Scenario A: at the main demo agent, `nagad_sim` has a strong cash-out surge in the final hour. Its position projects below threshold in 20 minutes while total balances may appear healthy;
- Scenario B: 7 repeated 10,000 BDT cash-outs by one fake `account_hash` in 15 minutes;
- Scenario C: `rocket_sim` latest position is 25 minutes old, causing low forecast confidence;
- scenario tags are used only for local testing/metrics, never shown as a fraud label.

Use a fixed random seed so every demo starts with the same expected alerts. A `--reset` option or `/dev/reset` makes reseeding reliable.

## 10. Twelve-hour implementation timeline

| Clock | Deliverable | Definition of done |
|---|---|---|
| 00:00–00:30 | Scaffold and local run | Requirements installed; `uvicorn app.main:app --reload` serves `/docs` and `/health`. |
| 00:30–01:45 | Database and enums | SQLAlchemy tables, indexes, Pydantic models, `init_db`, and providers seeded. |
| 01:45–03:00 | Simulator and seed endpoint | `/dev/reset` then `/dev/seed` populates SQLite with deterministic agents, positions, cash, transactions, and all three scenarios. |
| 03:00–04:30 | Ingestion and dashboard API | Transaction/position/snapshot endpoints work; `/dashboard/{id}` returns current data. |
| 04:30–05:45 | Liquidity rules and evidence | 20/60/180-minute forecast, expected shortage time, quality downgrade, and deduplicated alerts work. |
| 05:45–06:45 | Alert/case workflow | List/detail/status update/case creation/notes work from Swagger UI. |
| 06:45–08:15 | Simple frontend | One dashboard with provider cards, cash card, alert list, alert detail/evidence, and case action buttons. |
| 08:15–09:15 | ML anomaly layer | Isolation Forest or transparent fallback rule creates one “requires review” alert. Skip model tuning if it is unreliable. |
| 09:15–10:00 | Tests and validation | Test forecast, stale feed, duplicate transaction, alert lifecycle, and seed flow. |
| 10:00–10:45 | Documentation | README setup, architecture image/diagram, data-simulation note, metrics, risks and limits. |
| 10:45–11:30 | Demo rehearsal | Reset, seed, open dashboard, walk through scenario and case lifecycle twice. |
| 11:30–12:00 | Buffer | Fix visual/API defects; prepare a backup screen recording or screenshots. |

### Cut line if time is short

At 06:45, freeze the backend. If the frontend is not ready, demonstrate through FastAPI Swagger (`/docs`) and a minimal HTML page. If ML is not ready by 09:15, use the repeated-transaction rule and state that it is a transparent anomaly indicator. A working, explainable rule is preferable to an unverified model.

## 11. Demo script and acceptance checklist

1. Call `/dev/reset`, then `/dev/seed`.
2. Open the main agent dashboard: show shared cash, the three separate provider balances, and data freshness.
3. Select the `nagad_sim` liquidity alert: explain that total value is not the decision variable; its separate provider position is predicted to cross threshold in about 20 minutes.
4. Open its evidence: current balance, demand rate, threshold, forecast horizon, and confidence.
5. Acknowledge it and create/assign a case to `provider_operations`; add a note and escalate it.
6. Open the unusual activity alert: show repeated same-value cash-outs and use the wording “requires review.”
7. Show the stale `rocket_sim` feed and low confidence fallback.
8. State the limitation: all data, providers, balances, and actions are simulated; no payment action or fraud determination occurs.

Before presenting, confirm:

- [ ] `GET /health` returns 200.
- [ ] Fresh reset/seed takes less than 10 seconds.
- [ ] Main dashboard has at least two alerts, including one liquidity and one unusual-activity alert.
- [ ] Every alert has a recommended safe next step and evidence.
- [ ] A stale feed gives `low` confidence.
- [ ] Case status and note visibly persist after refresh.
- [ ] README has exactly one startup command and one demo-seeding command.

# 12-Hour MVP Plan: Multi-Provider Agent Liquidity Monitor

> **Repository alignment:** this plan uses the existing flat `backend/` and
> `frontend/` scaffold. The listed files are currently placeholders; implement
> the MVP in them rather than replacing the project with a new package layout.

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
| P1 | Filters by provider, agent, area, time, and alert status; Bengali/Banglish alert text. |
| P2 | Charts, Docker, and an optional Isolation Forest comparison experiment. |

Do **not** build real provider integrations, authentication, an LLM, complex permissions, or a full forecasting service in the first 12 hours. A deterministic, explainable rule-based anomaly detector is the default MVP.

## 2. Architecture

```text
Browser dashboard (`frontend/index.html`, vanilla JS)
       │ REST/JSON
       ▼
FastAPI application (`backend/app.py`)
 ├─ endpoints: dashboard / transactions / positions / alerts / cases / dev
 ├─ analytics helpers: liquidity, anomaly rules, alert creation (`backend/tools.py`)
 ├─ SQLAlchemy models and Pydantic contracts (`backend/models.py`)
 ├─ database session, schema creation, deterministic seeding (`backend/db.py`)
 └─ optional static explanation templates (`backend/prompts.py`; no LLM calls)
       │
       ▼
SQLite: `backend/data/mvp.db`
```

Use request-time calculations for forecasts and anomaly rules, then persist resulting alerts and evidence. Every calculation receives an explicit simulated `as_of` time (the latest seeded event by default), never the machine clock. This avoids queues, Redis, Celery, scheduled workers, and production integrations.

## 3. Project structure to implement

Keep the checked-in structure below. Add `backend/data/.gitkeep` and an optional
`backend/tests/` directory, but do not introduce a second application hierarchy.

```text
SUST_final/
├── plan.md
├── README.md
├── docker-compose.yml                    # fill only after local run works
├── backend/
│   ├── app.py                             # FastAPI app, routes, dependency wiring
│   ├── db.py                              # engine, sessions, init/reset/seed helpers
│   ├── models.py                          # SQLAlchemy tables, enums, Pydantic schemas
│   ├── tools.py                           # forecasting, anomaly rules, alert/case services
│   ├── prompts.py                         # fixed human-readable alert templates only
│   ├── llm.py                             # intentionally unused in MVP; no LLM integration
│   ├── requirements.txt
│   ├── Dockerfile                         # optional after local run works
│   ├── data/.gitkeep                      # generated `mvp.db` is gitignored
│   └── tests/                             # add focused pytest tests if time permits
│       ├── test_liquidity.py
│       └── test_api.py
└── frontend/
    ├── index.html
    ├── style.css
    ├── script.js                          # fetches API; vanilla JS is enough
    ├── nginx.conf                         # optional static-container configuration
    └── Dockerfile                         # optional after local run works
```

Suggested dependencies: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `pydantic`, and `pytest`. Add `scikit-learn` only if the optional comparison experiment is implemented. Resolve the SQLite path from `backend/db.py` so it always points to `backend/data/mvp.db`, and configure SQLite `check_same_thread=False`.

## 4. SQLite data model

Store all timestamps as UTC ISO-8601 text (`2026-07-11T10:30:00Z`). The seed establishes and returns a `simulated_as_of` time; dashboard and forecast endpoints use that value unless their optional `at` parameter is supplied. SQLite does not enforce native enums, so validate all enum values in Pydantic and optionally add `CHECK` constraints in SQLAlchemy.

### Tables

| Table | Purpose | Key fields |
|---|---|---|
| `providers` | Simulated provider catalogue | `code`, `display_name`, `is_active` |
| `agents` | Outlet and shared-cash identity | `id`, `name`, `area`, `shared_cash_threshold`, `status` |
| `provider_positions` | Time-series provider e-money position | `agent_id`, `provider_code`, `e_money_balance`, `safety_threshold`, `recorded_at`, `quality_status` |
| `cash_snapshots` | Time-series shared physical cash | `agent_id`, `physical_cash`, `recorded_at`, `quality_status` |
| `transactions` | Simulated immutable transaction events | `id`, `agent_id`, `provider_code`, `event_at`, `type`, `amount`, `status`, `account_hash`, `device_hash` |
| `alerts` | Human-review operational alert | `id`, `agent_id`, nullable `provider_code`, `type`, `severity`, `status`, `title`, `message`, `confidence`, `confidence_score`, `recommended_action`, `created_at`, `updated_at` |
| `alert_evidence` | Evidence displayed in the UI | `alert_id`, `key`, `value_text`, `value_number`, `message` |
| `alert_events` | Append-only operational audit trail | `id`, `alert_id`, `actor`, `from_status`, `to_status`, `note`, `created_at` |
| `cases` | Ownership and lifecycle for one alert | `id`, unique `alert_id`, `owner_role`, `assignee`, `status`, `priority`, `created_at`, `updated_at` |
| `case_notes` | Append-only human notes | `case_id`, `author`, `body`, `created_at` |
| `model_runs` | Optional reproducibility for the ML model | `id`, `model_name`, `trained_at`, `train_rows`, `metrics_json` |

### Important relationships and indexes

```text
agents 1 ── * provider_positions
agents 1 ── * cash_snapshots
agents 1 ── * transactions
agents 1 ── * alerts
alerts 1 ── * alert_evidence
alerts 1 ── * alert_events
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
CREATE UNIQUE INDEX ux_open_provider_alert_dedupe
  ON alerts(agent_id, provider_code, type)
  WHERE provider_code IS NOT NULL
    AND status IN ('new', 'acknowledged', 'assigned', 'escalated');
CREATE UNIQUE INDEX ux_open_shared_alert_dedupe
  ON alerts(agent_id, type)
  WHERE provider_code IS NULL
    AND status IN ('new', 'acknowledged', 'assigned', 'escalated');
```

`account_hash` and `device_hash` are generated fake identifiers, not real identities. Do not store phone numbers, PINs, OTPs, or credentials.

## 5. API enums (`backend/models.py`)

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

## 6. Pydantic API contracts (`backend/models.py`)

Use Pydantic v2. Money is represented as non-negative `float` for the prototype; in a production financial system use integer minor units or `Decimal`.

```python
from datetime import datetime
from typing import Annotated, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    actor: str = Field(min_length=2, max_length=80)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def resolution_requires_note(self):
        if self.status in {CaseStatus.RESOLVED, CaseStatus.CLOSED} and not self.note:
            raise ValueError("Resolving or closing a case needs a note")
        return self


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
    simulated_as_of: datetime
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
    simulated_as_of: datetime
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
| `GET /dashboard/{agent_id}` | optional `at` | `DashboardResponse` | Main page; position, forecast, quality, active alerts. Defaults `at` to the seed's `simulated_as_of`, never wall-clock time. |
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
2. A new transaction or provider position may create/update a relevant liquidity alert; do not create duplicate open alerts of the same type/provider.
3. Data quality is `STALE` when a latest snapshot is older than 15 minutes in the simulated timeline; it is `MISSING` when no position is available.
4. Every alert or case state change writes an `alert_events` record containing the actor, old and new status, note, and timestamp.
5. `POST /cases` should set alert status to `ASSIGNED`; `CaseStatus.ESCALATED` should set alert status to `ESCALATED`; resolving a case requires the `CaseUpdate.note` and sets its alert to `RESOLVED`.

## 8. Analytics method to implement

### Liquidity forecast (P0; deterministic and explainable)

For the shared-cash forecast, query all completed transactions for the agent in the latest 60 simulated minutes. For a provider forecast, query only that provider's completed transactions in the same window:

```text
cash_out_rate = sum(CASH_OUT amounts in lookback) / 60
cash_in_rate  = sum(CASH_IN amounts in lookback) / 60
shared_cash_burn_per_minute = max(cash_out_rate - cash_in_rate, 0)
provider_e_money_burn_per_minute = max(cash_in_rate - cash_out_rate, 0)

projected_shared_cash(h) = current_shared_cash - h * shared_cash_burn_per_minute
projected_provider_balance(h) = current_provider_balance - h * provider_e_money_burn_per_minute
```

For this simulation, `CASH_OUT` means the outlet gives physical cash and receives provider e-money; `CASH_IN` means the outlet receives physical cash and supplies provider e-money. Treat payments, transfers, and reversals as neutral unless explicit, documented simulation effects are added. This makes cash and provider-balance pressure logically distinct.

Create `SHARED_CASH_PRESSURE` when projected cash goes below `agents.shared_cash_threshold`. Create `PROVIDER_LIQUIDITY_PRESSURE` when a provider position goes below its `safety_threshold`. Estimate `expected_shortage_at` only if the relevant burn rate is greater than zero.

Confidence starts at `HIGH` and is downgraded:

- `MEDIUM` if the forecast's required cash, position, or transaction feed is 5–15 minutes old;
- `LOW` if a required feed is stale, missing, or conflicting;
- `LOW` if fewer than 10 completed transactions are available in the 60-minute lookback.

Evidence for every liquidity alert must include current balance, threshold, cash-out rate, cash-in rate, horizon, source age, and confidence reason.

### Anomaly detection (P0; transparent rules)

Create an `UNUSUAL_TRANSACTION_ACTIVITY` alert when either rule is met:

- **Velocity rule:** more than 10 transactions for one provider in three minutes.
- **Repetition rule:** at least four transactions of the exact same amount in ten minutes; the seeded demo uses seven 10,000 BDT cash-outs from one simulated account in 15 minutes.

Persist the matching rule, window, count, amount where relevant, and affected simulated identifier as alert evidence. If there is spare time, add an Isolation Forest comparison experiment in `backend/tools.py`; it must remain optional and its output must be labelled `unusualness_score`, never fraud.

The anomaly alert should show rule-derived evidence, not claim that the model proves fraud. Example:

> Unusual cash-out pattern requires review: 7 transactions of 10,000 BDT from the same simulated account in 15 minutes; this is above the outlet's normal frequency.

### Validation metrics (P0)

Compute these deterministic metrics from the seed's hidden scenario tags and show them in the README or a small dashboard panel:

| Metric | Measurement |
|---|---|
| Shortage detection lead time | Simulated minutes between alert creation and the known seeded threshold-crossing time. |
| Anomaly precision and recall | Compare rule-created alerts with the synthetic anomaly tags; normal traffic incorrectly flagged counts as a false positive. |
| API latency | Measure the median and p95 response time of `GET /dashboard/{agent_id}` over 20 local requests after seeding. |

Record the seed, `simulated_as_of`, data volume, and measurement method with the results so the figures are reproducible.

## 9. Synthetic data seeded directly into SQLite

Do not use CSV files. `POST /dev/seed`, implemented in `backend/app.py` and backed by helpers in `backend/db.py`, writes deterministic records directly through SQLAlchemy.

Seed a small but visually convincing scenario:

- 3 agents in different areas; 3 simulated providers per agent;
- 7 days of normal history (roughly 1,000–3,000 transactions is enough);
- a cash-out peak between 16:00–19:00;
- Scenario A: at the main demo agent, `nagad_sim` has a strong cash-in surge in the final hour. Its separate e-money position projects below threshold in 20 minutes while total balances may appear healthy;
- Scenario B: 7 repeated 10,000 BDT cash-outs by one fake `account_hash` in 15 minutes;
- Scenario C: `rocket_sim` latest position is 25 minutes old, causing low forecast confidence;
- scenario tags are used only for local testing/metrics, never shown as a fraud label.

Use a fixed random seed so every demo starts with the same expected alerts. A `--reset` option or `/dev/reset` makes reseeding reliable.

## 10. Twelve-hour implementation timeline

| Clock | Deliverable | Definition of done |
|---|---|---|
| 00:00–00:30 | Scaffold and local run | Fill `backend/requirements.txt`; `uvicorn app:app --app-dir backend --reload` serves `/docs` and `/health`. |
| 00:30–01:45 | Database and enums | SQLAlchemy tables, indexes, Pydantic models, `init_db`, and providers seeded. |
| 01:45–03:00 | Simulator and seed endpoint | `/dev/reset` then `/dev/seed` populates SQLite with deterministic agents, positions, cash, transactions, and all three scenarios. |
| 03:00–04:30 | Ingestion and dashboard API | Transaction/position/snapshot endpoints work; `/dashboard/{id}` returns current data. |
| 04:30–05:45 | Liquidity rules and evidence | 20/60/180-minute forecast, expected shortage time, quality downgrade, and deduplicated alerts work. |
| 05:45–06:45 | Alert/case workflow | List/detail/status update/case creation/notes work from Swagger UI. |
| 06:45–08:15 | Simple frontend | One dashboard with provider cards, cash card, alert list, alert detail/evidence, and case action buttons. |
| 08:15–09:15 | Rule-based anomaly layer | Velocity and repetition rules create one “requires review” alert. Add Isolation Forest only if all P0 work is complete. |
| 09:15–10:00 | Tests and validation | Test forecast, stale feed, duplicate transaction, alert lifecycle, and seed flow. |
| 10:00–10:45 | Documentation | README setup, architecture image/diagram, data-simulation note, metrics, risks and limits. |
| 10:45–11:30 | Demo rehearsal | Reset, seed, open dashboard, walk through scenario and case lifecycle twice. |
| 11:30–12:00 | Buffer | Fix visual/API defects; prepare a backup screen recording or screenshots. |

### Cut line if time is short

At 06:45, freeze the backend. If the frontend is not ready, demonstrate through FastAPI Swagger (`/docs`) and a minimal HTML page. If the optional ML comparison is not ready by 09:15, omit it and use the repeated-transaction rule as the transparent anomaly indicator. A working, explainable rule is preferable to an unverified model.

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

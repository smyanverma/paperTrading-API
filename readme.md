# 📈 PaperTrade — Async Paper Trading Engine

A backend-only paper trading platform built to explore **distributed systems problems** — not order-matching algorithms. Users buy and sell stocks at live market prices with a simulated $100,000 balance; every trade is processed asynchronously, cached reads stay fast under load, and the whole system is containerized end-to-end.

No trading algorithms. No order books. Just the hard, real infrastructure problems: race conditions, eventual consistency, cache invalidation, and async task execution — the same class of problems you'd hit building payment systems, webhook platforms, or trading infra in production.

---

## Why this project exists

Most portfolio projects either lean on algorithmic complexity (LeetCode-in-a-webapp) or bolt infrastructure on top of trivial CRUD just to check boxes. This one does the opposite on purpose: **the business logic is deliberately simple** (buy at current price, sell at current price, update a balance) so that 100% of the engineering effort goes into making that simple operation *correct and reliable under concurrency* — which is exactly the skill set that matters in distributed backend systems.

---

## Architecture

```
                         ┌─────────────┐
                         │   Client    │
                         └──────┬──────┘
                                │ JWT Bearer Token
                                ▼
                    ┌───────────────────────┐
                    │   Django REST API      │  (stateless, horizontally scalable)
                    │   /login /signup       │
                    │   /transact /trades/id │
                    │   /pnl /balance        │
                    └─────┬─────────────┬────┘
                           │             │
              read/write   │             │  enqueue task
                           ▼             ▼
                  ┌────────────┐   ┌──────────────┐
                  │ PostgreSQL │   │    Redis      │◄──── cache-aside reads
                  │  (source   │   │ (broker + PnL │      (P&L, short TTL)
                  │  of truth) │   │     cache)    │
                  └─────┬──────┘   └──────┬────────┘
                        │                 │
                        │        ┌────────┴────────┐
                        │        ▼                 ▼
                        │  ┌───────────┐    ┌──────────────┐
                        └─►│  Celery   │    │  Celery Beat │
                           │  Worker   │    │  (scheduler) │
                           │ (executes │    │ triggers price│
                           │  trades)  │    │refresh every  │
                           └───────────┘    │    60s        │
                                             └──────┬────────┘
                                                     ▼
                                            ┌────────────────┐
                                            │  Finnhub API    │
                                            │ (live stock     │
                                            │    prices)      │
                                            └────────────────┘
```

Every service above runs in its own Docker container, wired together via Docker Compose, and talks to every other service **only** through Postgres or Redis — never through direct function calls. That decoupling is the whole point: the API layer, the execution layer, and the scheduling layer can fail, restart, or scale independently of each other.

---

## What's actually interesting here (engineering deep-dive)

### 🔄 Fully async trade execution — not a blocking write
`POST /transact` does **not** execute the trade in the request/response cycle. It validates the request, writes a `Trade` row with status `PENDING`, hands off execution to a Celery worker, and returns `202 Accepted` immediately with a trade ID. The client polls `GET /trades/<id>` to watch the trade move from `PENDING → COMPLETED / FAILED`.

This means the HTTP layer never blocks on a database write burst — under load, the API stays responsive while a pool of workers absorbs the actual execution work, and worker replicas can be scaled independently of API replicas.

### 🔒 Row-level locking to eliminate race conditions
Two concurrent sell requests for the same holding — hitting two different workers at the same instant — could theoretically oversell shares that don't exist. Every trade execution wraps its critical section in:

```python
with transaction.atomic():
    profile = UserProfile.objects.select_for_update().get(pk=trade.profile_id)
    portfolio_item = PortfolioItem.objects.select_for_update().get_or_create(...)
```

`select_for_update()` takes a row-level lock at the database, so a second concurrent request against the *same* portfolio row physically waits at Postgres until the first transaction commits or rolls back. Combined with `transaction.atomic()`, a balance deduction and a share increment either **both** happen or **neither** does — no partial-write states, no oversold positions, no double-spent cash.

### 🗄 Cache-aside reads with write-triggered invalidation
The `/pnl` endpoint is the highest-read, most expensive-to-compute endpoint in the system — it joins every holding a user has against live prices and calculates unrealized P&L. Rather than recomputing this on every request:

- On read: check Redis for `pnl:user_<id>` → cache hit returns instantly, no DB touched at all
- On miss: compute fresh from Postgres, store in Redis with a short TTL
- On write: the moment a trade completes inside the Celery worker, it explicitly **deletes** that user's cached P&L key — forcing the next read to recompute against fresh data instead of serving something stale

This is the same cache-aside + invalidate-on-write pattern used in production systems handling far more traffic than this project ever will — implemented here at a scale small enough to actually reason about and demo cleanly.

### ⏱ Scheduled background jobs via Celery Beat
Stock prices aren't hardcoded or fetched synchronously on every trade (which would rate-limit fast under any real load). A Celery Beat schedule fires a `refresh_stock_prices` task every 60 seconds, which pulls live quotes from the Finnhub API and writes them into Postgres. Every trade execution and every P&L calculation then reads from that continuously-refreshed source — decoupling "get a live price" from "process a trade" entirely.

Per-ticker fetches are individually wrapped in try/except, so one failing or rate-limited ticker never blocks the rest of the batch from updating — a small but deliberate failure-isolation choice.

### 🔑 Stateless JWT authentication
Auth is fully stateless — no server-side session store, no per-request database lookup to validate identity. Each access token is a signed, self-contained claim (`user_id` embedded in the payload); Django's auth layer verifies the signature and expiry cryptographically before a view ever runs, then resolves `request.user` from that claim. This keeps the API layer horizontally scalable — any replica can authenticate any request without needing to share session state with any other replica.

### 🐳 Fully containerized, multi-service Docker Compose stack
Five services, one command:

| Service | Image | Role |
|---|---|---|
| `web` | custom (Dockerfile) | Django/DRF API |
| `worker` | **same** image, different command | Celery worker — executes trades |
| `beat` | **same** image, different command | Celery Beat — schedules price refresh |
| `db` | `postgres:16` | Source of truth |
| `redis` | `redis:7` | Celery broker + P&L cache |

`web`, `worker`, and `beat` are built from the **exact same codebase** — the only difference is the container's startup command. This mirrors how you'd actually deploy this to Kubernetes: identical images, separate Deployments, independently scalable based on completely different load characteristics (API traffic vs. queue depth).

---

## Tech Stack

- **Backend:** Django, Django REST Framework
- **Auth:** `djangorestframework-simplejwt` (stateless JWT)
- **Database:** PostgreSQL
- **Cache & Message Broker:** Redis
- **Async Task Queue:** Celery (workers + Beat scheduler)
- **External Data:** Finnhub API (live stock quotes)
- **Containerization:** Docker, Docker Compose

**Coming next:** AWS (RDS, ElastiCache, ALB, EKS), Kubernetes with HPA on queue depth, GitHub Actions CI/CD, Prometheus/Grafana monitoring, and Locust load testing to validate all of the above under real concurrent traffic.

---

## API Overview

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/signup/` | — | Create a user (starts with $100,000 simulated balance) |
| `POST` | `/api/login/` | — | Obtain JWT access + refresh tokens |
| `POST` | `/api/login/refresh/` | — | Refresh an access token |
| `GET` | `/api/balance/` | JWT | Check current cash balance |
| `POST` | `/api/transact/` | JWT | Submit a buy/sell order → `202` + trade ID (async) |
| `GET` | `/api/trades/<id>/` | JWT | Poll trade status (`PENDING` / `COMPLETED` / `FAILED`) |
| `GET` | `/api/pnl/` | JWT | Cached, per-user unrealized profit & loss across all holdings |

---

## Running it locally

```bash
git clone <this-repo>
cd paperTrading
docker-compose up --build
```

That single command brings up Postgres, Redis, the Django API, a Celery worker, and Celery Beat together. The API is then available at `http://localhost:8000/api/`.

---


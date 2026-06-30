# approval-service

A production-ready backend service for **content approval workflows**. Clients
submit content (a publication, scenario, edit, or external item) for review and
the service records the final decision (`approved` / `rejected` / `cancelled`),
with a full audit trail and an event stream for downstream integrations.

External entities (`sourceId`, `reviewerUserIds`, `workspace_id`, users) are
opaque identifiers — neighbouring services are out of scope.

- **Stack:** Python · FastAPI · SQLAlchemy · Alembic · PostgreSQL (SQLite for local)
- **Runs with one command:** `docker-compose up`
- **Tested:** 46 pytest cases covering the full spec

See [DESIGN.md](DESIGN.md) for the data model, idempotency mechanism, event
architecture, and trade-offs.

---

## 1. Quick start (Docker)

```bash
docker-compose up --build
```

This starts PostgreSQL, waits for it to be healthy, **applies migrations
automatically** (`alembic upgrade head`), and serves the API on
**http://localhost:8000**.

- OpenAPI docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness (checks DB): http://localhost:8000/ready

Stop and wipe the database volume:

```bash
docker-compose down -v
```

## 2. Run locally without Docker (SQLite)

No external dependencies — the default `DATABASE_URL` is a local SQLite file.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     |  Unix: source .venv/bin/activate
pip install -r requirements-dev.txt

alembic upgrade head
uvicorn app.main:app --reload
```

To run locally against PostgreSQL instead, set the DSN:

```bash
export DATABASE_URL=postgresql+psycopg2://approval:approval@localhost:5432/approval
alembic upgrade head
uvicorn app.main:app
```

## 3. Run the tests

The test-suite runs entirely on SQLite (no Docker/Postgres needed):

```bash
pip install -r requirements-dev.txt
pytest
```

Coverage includes: create / read / list, approve / reject / cancel, workspace
isolation, idempotency, double-final-decision (409), invalid state transitions,
missing permissions (401/403), missing resources (404), audit trail, outbox
events, secret/PII redaction, and reproducible Alembic migrations.

---

## 4. Authentication (local stub)

A real deployment would validate a signed JWT from the platform identity
service. For local/dev this service trusts three request headers:

| Header            | Example                                   | Meaning                          |
|-------------------|-------------------------------------------|----------------------------------|
| `X-User-Id`       | `usr_admin`                               | Acting user                      |
| `X-Workspace-Id`  | `ws_1`                                     | Caller's workspace               |
| `X-Permissions`   | `approval:read,approval:create`           | Comma-separated permission list  |

Rules:

- Missing `X-User-Id` or `X-Workspace-Id` → **401**.
- `X-Workspace-Id` **must equal** the `{workspace_id}` in the URL path, otherwise
  **403** (first line of workspace isolation).
- The endpoint's required permission must be present in `X-Permissions`, else **403**.

### Permission matrix

| Action               | Endpoint                                  | Required permission |
|----------------------|-------------------------------------------|---------------------|
| Read / list          | `GET .../approval-requests[/{id}]`        | `approval:read`     |
| Create               | `POST .../approval-requests`              | `approval:create`   |
| Approve / Reject     | `POST .../{id}/approve` `/reject`         | `approval:decide`   |
| Cancel               | `POST .../{id}/cancel`                    | `approval:cancel`   |

---

## 5. API & curl examples

Base path: `/api/v1/workspaces/{workspace_id}/approval-requests`

A convenience variable for the examples:

```bash
AUTH=(-H "X-User-Id: usr_admin" -H "X-Workspace-Id: ws_1" \
      -H "X-Permissions: approval:read,approval:create,approval:decide,approval:cancel")
BASE=http://localhost:8000/api/v1/workspaces/ws_1/approval-requests
```

### Health / readiness

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### Create a request

`Idempotency-Key` is optional; sending the same key + body again replays the
original response instead of creating a duplicate.

```bash
curl -X POST "$BASE" "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 9f1c-create-001" \
  -d '{
    "sourceType": "publication",
    "sourceId": "pub_123",
    "title": "Instagram reel draft",
    "description": "Needs final approval",
    "reviewerUserIds": ["usr_1", "usr_2"]
  }'
```

→ `201 Created`

```json
{
  "id": "1b9d...",
  "workspaceId": "ws_1",
  "sourceType": "publication",
  "sourceId": "pub_123",
  "title": "Instagram reel draft",
  "description": "Needs final approval",
  "reviewerUserIds": ["usr_1", "usr_2"],
  "status": "pending",
  "decisionComment": null,
  "decisionReason": null,
  "decidedBy": null,
  "createdBy": "usr_admin",
  "createdAt": "2026-06-30T10:00:00+00:00",
  "updatedAt": "2026-06-30T10:00:00+00:00"
}
```

### List requests (with optional filter & pagination)

```bash
curl "$BASE" "${AUTH[@]}"
curl "$BASE?status=pending&limit=20&offset=0" "${AUTH[@]}"
```

→ `{ "items": [...], "total": 1, "limit": 50, "offset": 0 }`

### Get one request

```bash
curl "$BASE/<request_id>" "${AUTH[@]}"
```

### Approve

```bash
curl -X POST "$BASE/<request_id>/approve" "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d '{ "comment": "Approved" }'
```

### Reject

```bash
curl -X POST "$BASE/<request_id>/reject" "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d '{ "reason": "Brand tone is wrong" }'
```

### Cancel

```bash
curl -X POST "$BASE/<request_id>/cancel" "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d '{ "reason": "Draft was removed" }'
```

A request that is already `approved`/`rejected`/`cancelled` cannot change again —
any further decision returns **409 Conflict**.

---

## 6. Observability

Every request and every state change is logged as a single JSON line including
`request_id`, `workspace_id`, `user_id`, the action and the result. Secrets and
PII (emails, URLs, signed/provider URLs, bearer tokens, JWTs, and obviously-named
secret fields) are redacted from logs and domain events. The response header
`X-Request-Id` correlates client requests with log lines.

## 7. Project layout

```
approval-service/
├── app/
│   ├── api/          # FastAPI routers (health, approval-requests)
│   ├── core/         # config, db, auth stub, logging, sanitization, enums
│   ├── events/       # in-process event bus + outbox dispatcher
│   ├── models/       # SQLAlchemy models
│   ├── schemas/      # Pydantic schemas
│   ├── services/     # business logic (approval state machine, idempotency)
│   └── main.py       # app factory + middleware
├── migrations/       # Alembic env + versions
├── tests/            # pytest suite (SQLite)
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh     # alembic upgrade head && uvicorn
├── requirements.txt
├── requirements-dev.txt
├── README.md
└── DESIGN.md
```

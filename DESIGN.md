# DESIGN — approval-service

## 1. Service boundaries

The service owns exactly one bounded context: **the lifecycle of an approval
request and its final decision.**

It does **not** own, fetch, or persist anything about the content being approved.
All external entities are stored as opaque identifiers:

- `sourceId` — the content under review (publication, scenario, edit, …)
- `reviewerUserIds` — who may review
- `workspace_id`, `created_by`, `decided_by` — tenancy / actors

Consequences:

- The service never holds provider URLs, storage keys, signed URLs, tokens, or
  raw provider payloads, so it cannot leak them. Free-text fields (`title`,
  `description`, decision `comment`/`reason`) are the only place a client could
  *accidentally* embed such data; everything written to **logs and events** is
  therefore passed through a redactor (see §6).
- Authorization (who may act) is delegated to an upstream identity service; here
  it is a header-based stub (see README §4) with a clean dependency seam so the
  real JWT validator drops in without touching business logic.

## 2. Data model

Four tables. UUIDs are stored as `String(36)`, JSON via SQLAlchemy's portable
`JSON` type, and timestamps as timezone-aware `DateTime` — all chosen so the
identical schema works on both PostgreSQL and SQLite.

### `approval_requests` — the aggregate root

| Column              | Type           | Notes                                              |
|---------------------|----------------|----------------------------------------------------|
| `id` (PK)           | String(36)     | UUID                                               |
| `workspace_id`      | String(255)    | indexed; tenancy key                               |
| `source_type`       | String(50)     | `publication` \| `scenario` \| `edit` \| `external`|
| `source_id`         | String(255)    | opaque content id                                  |
| `title`             | String(500)    |                                                    |
| `description`       | Text (null)    |                                                    |
| `reviewer_user_ids` | JSON           | list of user ids                                   |
| `status`            | String(50)     | `pending`/`approved`/`rejected`/`cancelled`        |
| `decision_comment`  | Text (null)    | set on approve                                     |
| `decision_reason`   | Text (null)    | set on reject/cancel                               |
| `decided_by`        | String(255)    | actor of the final decision                        |
| `created_by`        | String(255)    |                                                    |
| `created_at`        | DateTime(tz)   |                                                    |
| `updated_at`        | DateTime(tz)   |                                                    |

Indexes: `workspace_id`, `status`, and composite `(workspace_id, status)` for the
common "list pending in my workspace" query.

### `approval_events` — append-only audit trail

One row per **successful** state change (who / what / when / before → after).

| Column            | Type         | Notes                                  |
|-------------------|--------------|----------------------------------------|
| `id` (PK)         | String(36)   |                                        |
| `workspace_id`    | String(255)  | indexed                                |
| `request_id` (FK) | String(36)   | → `approval_requests.id`, `ON DELETE CASCADE` |
| `action`          | String(50)   | `created`/`approved`/`rejected`/`cancelled` |
| `actor_user_id`   | String(255)  |                                        |
| `previous_status` | String(50)   | null for `created`                     |
| `new_status`      | String(50)   |                                        |
| `event_metadata`  | JSON (null)  | sanitized context (e.g. comment/reason)|
| `created_at`      | DateTime(tz) |                                        |

### `outbox_events` — transactional outbox

Domain events written in the **same transaction** as the state change.

| Column           | Type          | Notes                                  |
|------------------|---------------|----------------------------------------|
| `id` (PK)        | String(36)    |                                        |
| `workspace_id`   | String(255)   | indexed                                |
| `aggregate_type` | String(100)   | `approval_request`                     |
| `aggregate_id`   | String(36)    | the request id                         |
| `event_type`     | String(100)   | `approval_request.created` etc.        |
| `payload`        | JSON          | already-sanitized event body           |
| `created_at`     | DateTime(tz)  |                                        |
| `published_at`   | DateTime(tz)  | indexed; null = not yet published      |

### `idempotency_keys`

| Column            | Type        | Notes                                          |
|-------------------|-------------|------------------------------------------------|
| `id` (PK)         | String(36)  |                                                |
| `workspace_id`    | String(255) | part of uniqueness                             |
| `idempotency_key` | String(255) | client-supplied                                |
| `request_hash`    | String(64)  | SHA-256 of the canonical request body          |
| `response_status` | Integer     | stored response status                         |
| `response_body`   | JSON        | stored response, replayed verbatim             |
| `request_id`      | String(36)  | the created request                            |
| `created_at`      | DateTime(tz)|                                                |
| **Unique**        |             | `(workspace_id, idempotency_key)`              |

## 3. Workspace isolation

Defence in depth, two independent layers:

1. **Request layer** — the auth dependency requires `X-Workspace-Id` to equal the
   `{workspace_id}` path segment; a mismatch is `403` before any data is touched.
2. **Data layer** — *every* query is filtered by `workspace_id`. A request id
   from another workspace simply isn't found (`404`), never disclosed.

Idempotency keys are likewise unique **per workspace**, so the same key string in
two workspaces yields two independent requests.

## 4. State machine & finality

```
                approve  ─▶ approved   (final)
pending ────────reject   ─▶ rejected   (final)
                cancel   ─▶ cancelled  (final)
```

`pending` is the only non-final state. Any decision attempted on a request that
is already in a final state returns **409 Conflict** and writes nothing — this
single rule simultaneously guarantees "no second final decision" and "no invalid
transition". Verified by tests for every approve/reject/cancel combination.

## 5. Idempotency

**Mechanism chosen: `Idempotency-Key` request header** (industry-standard, used
by Stripe/others), applied to the only naturally non-idempotent operation —
**create**.

- The client sends `Idempotency-Key: <opaque>`.
- The service stores `(workspace_id, key)` with a SHA-256 hash of the canonical
  request body and the serialized 201 response.
- A **replay with the same key + same body** returns the original response
  verbatim (with `Idempotency-Replayed: true`) — no duplicate row.
- A **replay with the same key + different body** is a client error → `409`.
- The request, its audit row, its outbox event and the idempotency record all
  commit in **one transaction**. A unique constraint on `(workspace_id, key)`
  closes the concurrent-duplicate race: the loser catches the `IntegrityError`,
  rolls back, and returns the winner's stored response.

The decision endpoints don't need keys: state finality already makes a repeated
approve/reject/cancel a safe `409` rather than a duplicate.

## 6. Events & integrations (event-ready)

**Transactional outbox + in-process event bus.**

- On every state change the service inserts an `outbox_events` row inside the
  business transaction. If the transaction rolls back, no event is produced —
  state and events can never diverge.
- After commit, a dispatcher publishes unpublished rows to an `EventBus` and
  stamps `published_at`. Publishing is at-least-once: a failure leaves rows
  unpublished for a later sweep (in production the dispatcher runs on a
  background worker/poller; here it runs inline after each request).
- Business logic only ever calls `event_bus.publish(event)`. Swapping the
  default `InProcessEventBus` (which currently just logs) for a Kafka or RabbitMQ
  producer is a one-class change with **zero edits to the service layer or the
  outbox** — that is the extensibility seam the spec asks for.

Event types emitted: `approval_request.{created,approved,rejected,cancelled}`.

## 7. Data safety (no secret/PII leakage)

`app/core/sanitization.py` recursively redacts before anything reaches **logs**
or **events**:

- emails → `[REDACTED_EMAIL]`
- `http(s)` URLs, incl. signed/provider URLs → `[REDACTED_URL]`
- JWTs and `Bearer …` tokens → `[REDACTED_TOKEN]`
- values under sensitive keys (`token`, `password`, `secret`, `authorization`,
  `signed_url`, `storage_key`, `provider_url`, `provider_payload`, …) → `[REDACTED]`

Because the service stores only opaque ids and never enriches with provider
data, API responses cannot contain infrastructure secrets by construction.
The free-text fields a client itself submits (`title`, `description`,
`comment`, `reason`) are echoed back verbatim in responses (they *are* the
content under review), but are redacted everywhere they fan out to logs and
events.

## 8. Logging & observability

Structured JSON logs (`app/core/logging.py`). A middleware assigns a
`request_id` (honouring an inbound `X-Request-Id`), propagates it plus
`workspace_id`/`user_id` via `contextvars`, returns it as the `X-Request-Id`
response header, and logs one `request.handled` line per request with method,
path, status and duration. State changes log a `approval.state_change` line.

## 9. Known trade-offs & compromises

- **Synchronous SQLAlchemy.** Chosen for operational simplicity and rock-solid
  Alembic/driver behaviour; FastAPI runs the sync handlers in a threadpool. For
  very high concurrency an async stack (asyncpg) would be the next step.
- **Inline outbox dispatch.** Events are dispatched right after commit in the
  request path rather than by a separate worker. This keeps the deployment a
  single process; the dispatcher (`dispatch_pending`) is already written to be
  lifted into a background poller unchanged.
- **Header-based auth stub.** Intentional per the spec — trivially swapped for
  real JWT verification at the `get_principal` dependency.
- **Status/source enums stored as strings**, validated in the application layer
  rather than as native DB enums, to keep one migration that is byte-for-byte
  reproducible across PostgreSQL and SQLite.
- **No soft-delete / history of edits to `title`/`description`.** Requests are
  immutable after creation except for the single decision transition; the audit
  trail captures every status change. Editing content was out of scope.
- **Idempotency stored indefinitely.** A TTL/cleanup job for old idempotency
  keys would be added for production retention hygiene.
```

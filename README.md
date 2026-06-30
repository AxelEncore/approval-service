# approval-service

Production-ready backend-сервис для **процессов согласования контента**. Клиенты
отправляют контент (публикацию, сценарий, правку или внешний объект) на ревью, а
сервис фиксирует итоговое решение (`approved` / `rejected` / `cancelled`) с полным
audit trail и потоком событий для смежных интеграций.

Внешние сущности (`sourceId`, `reviewerUserIds`, `workspace_id`, пользователи) —
это непрозрачные идентификаторы; соседние сервисы вне области реализации.

- **Стек:** Python · FastAPI · SQLAlchemy · Alembic · PostgreSQL (SQLite для локального запуска)
- **Запуск одной командой:** `docker-compose up`
- **Покрытие тестами:** 46 кейсов pytest по всему ТЗ

Модель данных, механизм идемпотентности, архитектура событий и компромиссы
описаны в [DESIGN.md](DESIGN.md).

---

## 1. Быстрый старт (Docker)

```bash
docker-compose up --build
```

Поднимается PostgreSQL, дожидается healthcheck, **автоматически применяются
миграции** (`alembic upgrade head`), и API становится доступен на
**http://localhost:8000**.

- OpenAPI-документация: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness (проверяет БД): http://localhost:8000/ready

Остановить и удалить том с данными БД:

```bash
docker-compose down -v
```

## 2. Локальный запуск без Docker (SQLite)

Без внешних зависимостей — по умолчанию `DATABASE_URL` указывает на локальный файл SQLite.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     |  Unix: source .venv/bin/activate
pip install -r requirements-dev.txt

alembic upgrade head
uvicorn app.main:app --reload
```

Чтобы локально работать с PostgreSQL, задайте DSN:

```bash
export DATABASE_URL=postgresql+psycopg2://approval:approval@localhost:5432/approval
alembic upgrade head
uvicorn app.main:app
```

## 3. Запуск тестов

Тесты полностью работают на SQLite (Docker/Postgres не нужны):

```bash
pip install -r requirements-dev.txt
pytest
```

Покрытие включает: создание / чтение / список, approve / reject / cancel,
workspace isolation, идемпотентность, повторное финальное решение (409),
невалидные переходы состояний, отсутствие прав (401/403), несуществующие ресурсы
(404), audit trail, события outbox, маскирование секретов/PII и воспроизводимость
миграций Alembic.

---

## 4. Аутентификация (локальная заглушка)

В реальном развёртывании здесь была бы проверка подписанного JWT от платформенного
сервиса идентификации. Для локального запуска сервис доверяет трём заголовкам:

| Заголовок         | Пример                                    | Назначение                       |
|-------------------|-------------------------------------------|----------------------------------|
| `X-User-Id`       | `usr_admin`                               | Действующий пользователь         |
| `X-Workspace-Id`  | `ws_1`                                     | Workspace вызывающего            |
| `X-Permissions`   | `approval:read,approval:create`           | Список прав через запятую         |

Правила:

- Отсутствие `X-User-Id` или `X-Workspace-Id` → **401**.
- `X-Workspace-Id` **должен совпадать** с `{workspace_id}` в URL, иначе **403**
  (первый рубеж изоляции workspace).
- Требуемое для эндпоинта право должно присутствовать в `X-Permissions`, иначе **403**.

### Матрица прав

| Действие             | Эндпоинт                                  | Требуемое право     |
|----------------------|-------------------------------------------|---------------------|
| Чтение / список      | `GET .../approval-requests[/{id}]`        | `approval:read`     |
| Создание             | `POST .../approval-requests`              | `approval:create`   |
| Approve / Reject     | `POST .../{id}/approve` `/reject`         | `approval:decide`   |
| Cancel               | `POST .../{id}/cancel`                    | `approval:cancel`   |

---

## 5. API и примеры curl

Базовый путь: `/api/v1/workspaces/{workspace_id}/approval-requests`

Удобные переменные для примеров:

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

### Создание заявки

`Idempotency-Key` опционален; повторная отправка того же ключа и тела вернёт
исходный ответ, не создавая дубль.

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

### Список заявок (с фильтром и пагинацией)

```bash
curl "$BASE" "${AUTH[@]}"
curl "$BASE?status=pending&limit=20&offset=0" "${AUTH[@]}"
```

→ `{ "items": [...], "total": 1, "limit": 50, "offset": 0 }`

### Получение одной заявки

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

Заявка, которая уже находится в статусе `approved`/`rejected`/`cancelled`, не может
измениться повторно — любое следующее решение вернёт **409 Conflict**.

---

## 6. Наблюдаемость (observability)

Каждый запрос и каждое изменение состояния логируется одной строкой JSON с
`request_id`, `workspace_id`, `user_id`, действием и результатом. Секреты и PII
(email, URL, в том числе signed/provider URL, bearer-токены, JWT и поля с
очевидно секретными именами) маскируются в логах и доменных событиях. Заголовок
ответа `X-Request-Id` связывает клиентские запросы с логами.

## 7. Структура проекта

```
approval-service/
├── app/
│   ├── api/          # роутеры FastAPI (health, approval-requests)
│   ├── core/         # конфиг, БД, auth-заглушка, логирование, санитизация, enum'ы
│   ├── events/       # in-process event bus + диспетчер outbox
│   ├── models/       # SQLAlchemy-модели
│   ├── schemas/      # Pydantic-схемы
│   ├── services/     # бизнес-логика (state machine согласования, идемпотентность)
│   └── main.py       # фабрика приложения + middleware
├── migrations/       # Alembic env + versions
├── tests/            # набор pytest (SQLite)
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh     # alembic upgrade head && uvicorn
├── requirements.txt
├── requirements-dev.txt
├── README.md
└── DESIGN.md
```

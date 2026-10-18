# HTTP API

Префикс `/api/`. Кроме отмеченных публичных путей нужен заголовок `Authorization: Token <ключ>`. Время в запросах и ответах — ISO 8601 с часовым поясом, в ответах оно в UTC. Деньги — целые копейки в полях с суффиксом `_kopecks`.

Ошибка домена: `{"code": "<код>", "detail": "<текст>"}`. Ошибка полей: `{"code": "validation_error", "detail": "...", "fields": {...}}`. Нет токена — `401` `not_authenticated`. Чужие бронь и машина отвечают так же, как несуществующие: `404` `not_found`.

| Метод | Путь | Кто | Успех | Основные ошибки |
|---|---|---|---|---|
| GET | `/api/health/` | публичный | 200 `{"status": "ok"}` | — |
| POST | `/api/auth/register/` | публичный | 201 `{email, token}` | 400 дубль почты, слабый пароль |
| POST | `/api/auth/login/` | публичный | 200 `{token}` | 400 `invalid_credentials` |
| GET | `/api/me/` | водитель | 200 почта и машины | 401 |
| GET | `/api/vehicles/` | водитель | 200 | 401 |
| POST | `/api/vehicles/` | водитель | 201 `{id, plate}` | 400 `invalid_plate`, 409 `plate_taken` |
| DELETE | `/api/vehicles/{id}/` | водитель | 204 | 404, 409 `vehicle_in_use` |
| GET | `/api/spots/` | публичный | 200 `[{id, code, status}]` | — |
| GET | `/api/bookings/?status=` | водитель | 200 страница | 400 неизвестный статус, 401 |
| POST | `/api/bookings/` | водитель | 201 | 400, 404, 409 `booking_conflict` |
| POST | `/api/bookings/{id}/cancel/` | водитель | 200 | 404, 409 `booking_not_cancellable` |
| GET | `/api/visits/` | водитель | 200 страница, счёт внутри визита | 401 |
| GET | `/api/invoices/` | водитель | 200 страница | 401 |
| POST | `/api/gate/enter/` | публичный | 201 визит | 400 `invalid_plate`, 409 `double_entry`, `no_free_place` |
| POST | `/api/gate/exit/` | публичный | 200 визит и счёт | 409 `no_active_visit`, `exit_not_after_entry` |

`status` места: `free`, `booked`, `occupied`. Страницы броней, визитов и счетов по 20 записей, от новых к старым: `count`, `next`, `previous`, `results`.

Демо после старта: `demo@example.com`, пароль из `DEMO_PASSWORD` (в `.env.example` это `ParkDemo-2026`), машина `A000AA`, места `P01`–`P12`.

## Сквозной сценарий

Сервер на `http://localhost:8000`. Бронь начинается «сейчас», чтобы шлагбаум попал в окно заезда. Выезд сразу после заезда тарифицирует начатую минуту.

```bash
BASE=http://localhost:8000
EMAIL="flow-$(date +%s)@example.com"

curl -s -X POST "$BASE/api/auth/register/" \
  -H 'Content-Type: application/json' \
  -d "{\"email\": \"$EMAIL\", \"password\": \"secret-pass\"}"

# подставить token из ответа
TOKEN=...

curl -s -X POST "$BASE/api/vehicles/" \
  -H "Authorization: Token $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"plate": "а 777 аа"}'

# id машины из ответа
VEHICLE=...

curl -s "$BASE/api/spots/"

# id свободного места
SPOT=...

START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
END=$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)

curl -s -X POST "$BASE/api/bookings/" \
  -H "Authorization: Token $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"vehicle\": $VEHICLE, \"spot\": $SPOT, \"starts_at\": \"$START\", \"ends_at\": \"$END\"}"

curl -s -X POST "$BASE/api/gate/enter/" \
  -H 'Content-Type: application/json' \
  -d '{"plate": "A777AA"}'

sleep 1

curl -s -X POST "$BASE/api/gate/exit/" \
  -H 'Content-Type: application/json' \
  -d '{"plate": "A777AA"}'

curl -s "$BASE/api/visits/" -H "Authorization: Token $TOKEN"
curl -s "$BASE/api/invoices/" -H "Authorization: Token $TOKEN"

curl -s -X POST "$BASE/api/gate/exit/" \
  -H 'Content-Type: application/json' \
  -d '{"plate": "A777AA"}'
```

Последний выезд — `409` и `"code": "no_active_visit"`.

## Сокет схемы

`ws://<хост>/ws/spots/`. Токен не нужен: табло публичное. Origin должен быть из `ALLOWED_HOSTS`, иначе соединение закрывается. Через nginx это `ws://localhost:8080/ws/spots/`.

Сервер шлёт только `{"type": "spots.changed"}`. В сообщении нет мест и броней. После подключения и после каждого такого сообщения клиент заново запрашивает `GET /api/spots`. Список по HTTP остаётся единственным источником правды.

Тот же сигнал уходит после брони, отмены, заезда, выезда и снятия хотя бы одной просроченной брони, а также каждые 15 секунд: часть смен на схеме наступает по часам и ничего не пишет в базу.

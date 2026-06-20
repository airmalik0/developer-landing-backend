# Developer Landing Backend

Бэкенд-сервис для лендинг-презентации разработчика: REST API формы обратной
связи с валидацией, rate limiting, логированием, **обязательной AI-интеграцией**
(анализ обращения + классификация + черновик ответа) с graceful fallback,
email-уведомлениями, Swagger-документацией, слоистой архитектурой и
мини-лендингом с рабочей формой.

> Полный цикл, который реализует сервис:
> **запрос → валидация → rate-limit → бизнес-логика → AI → отправка email → ответ**

| | |
|---|---|
| 🔗 Live | https://developer-landing-backend-gamma.vercel.app |
| 📚 Swagger | https://developer-landing-backend-gamma.vercel.app/docs |
| 🧩 OpenAPI | https://developer-landing-backend-gamma.vercel.app/openapi.json |
| 💻 GitHub | https://github.com/airmalik0/developer-landing-backend |

> На проде ключи не заданы → AI работает в fallback, email пропускается, а
> файловое хранилище на Vercel эфемерно. Чтобы включить «живые» AI + email +
> персистентные метрики, задайте переменные окружения (см. раздел «Деплой»).

---

## 1. Как запустить проект

### Локально (Python 3.10+)

```bash
# 1. Клонировать
git clone https://github.com/airmalik0/developer-landing-backend.git
cd developer-landing-backend

# 2. Зависимости (uv — быстрее; либо обычный venv + pip)
uv venv --python 3.12
uv pip install -r requirements-dev.txt
#   или:  python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt

# 3. Переменные окружения
cp .env.example .env        # заполните при необходимости (без ключей сервис тоже работает)

# 4. Запуск
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Откройте:
- лендинг с формой — http://localhost:8000/
- Swagger — http://localhost:8000/docs

### Тесты

```bash
.venv/bin/python -m pytest
```

### Настройка переменных окружения

Все ключи опциональны — без них сервис **продолжает работать** (AI уходит в
fallback, email пишется в лог). Полный список — в [`.env.example`](.env.example).

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `STORAGE_BACKEND` | `file` (локально) или `redis` (Upstash, прод) | `file` |
| `RATE_LIMIT_MAX_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | защита от спама | `5` / `60` |
| `ANTHROPIC_API_KEY` | ключ Anthropic для AI-функции | — |
| `ANTHROPIC_MODEL` | модель | `claude-haiku-4-5` |
| `RESEND_API_KEY`, `OWNER_EMAIL`, `FROM_EMAIL` | отправка email через Resend | — |
| `UPSTASH_REDIS_REST_URL` / `..._TOKEN` | Redis для прод-хранилища | — |
| `CORS_ORIGINS` | разрешённые источники (через запятую) | `*` |

---

## 2. Стек технологий

- **Язык / фреймворк:** Python 3.12, **FastAPI** (async, авто-Swagger/OpenAPI,
  валидация на Pydantic v2).
- **AI:** **Anthropic Claude Haiku** (`claude-haiku-4-5`) через official Python SDK,
  structured output через *forced tool-use*.
- **Email:** **Resend** (письмо владельцу + копия пользователю).
- **Хранилище:** файловое (JSON/JSONL) локально, **Upstash Redis** на проде —
  за единым интерфейсом `Store`.
- **Сервер:** Uvicorn локально; **Vercel** (serverless ASGI) на проде.
- **Тесты:** pytest + Starlette `TestClient`.

**Почему так:** FastAPI даёт Swagger и строгую валидацию из коробки и идеально
ложится на слоистую архитектуру. Haiku — самая дешёвая и быстрая модель Anthropic,
которой более чем достаточно для триажа обращений. Resend — простейшая реальная
доставка email без поднятия SMTP. Файловое хранилище закрывает требование ТЗ для
локального запуска, а Redis — корректный паттерн для эфемерной ФС Vercel
(см. раздел 7).

---

## 3. Архитектура

Слоистая структура **Controllers → Services → Repositories**: контроллеры тонкие,
бизнес-логика в сервисах, доступ к данным — за интерфейсом репозитория.

```
app/
  main.py            FastAPI-фабрика: CORS, request-logging, error-handler, роуты, статика
  config.py          pydantic-settings (.env) — единая точка конфигурации
  schemas/           Pydantic-модели запросов/ответов
  api/routes/        contact · health · metrics        ← контроллеры (тонкие)
  services/          contact_service · ai_service · email_service   ← бизнес-логика
  repositories/      base (Store) · file_store · redis_store · factory   ← доступ к данным
  core/              logging · errors (исключения + глобальные обработчики)
  middleware/        request_logging (request_id, IP, статус, latency)
api/index.py         ASGI-entrypoint для Vercel
frontend/            index.html + static (лендинг с формой)
tests/               pytest: валидация, rate-limit, AI-fallback, health, metrics
docs/                спецификация дизайна
examples/            Postman-коллекция + .http-файл
```

**Паттерны проектирования:**

- **Repository** — `Store` (ABC) скрывает, где лежат логи/статистика/rate-limit;
  две реализации (`FileStore`, `RedisStore`) переключаются переменной окружения.
  Это даёт одинаковый код локально и на serverless и закрывает требование «работа
  с хранилищем».
- **Service layer** — `ContactService` оркеструет полный цикл; `AIService` и
  `EmailService` инкапсулируют внешние интеграции с изолированным fallback.
- **Factory** — `get_store()` выбирает бэкенд по конфигурации.
- **Dependency-light DI** — сервисы принимают зависимости в конструкторе, что
  делает их тривиально тестируемыми (моки в тестах не понадобились — fallback
  самодостаточен).
- **Middleware + centralized error handling** — единый JSON-формат ошибок и
  сквозное логирование с `request_id`.

---

## 4. Реализация API

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/api/contact` | Отправка формы (полный цикл) |
| `GET`  | `/api/health`  | Статус сервиса + сконфигурированные возможности |
| `GET`  | `/api/metrics` | Агрегированная статистика обращений |
| `GET`  | `/docs`        | Swagger UI |
| `GET`  | `/openapi.json`| OpenAPI-схема |
| `GET`  | `/`            | Лендинг с формой |

### `POST /api/contact`

**Валидация** (Pydantic): `name` (2–100), `email` (формат), `phone`
(международный паттерн), `comment` (5–2000); строки тримятся и санитизируются.

**Пример запроса:**

```bash
curl -X POST http://localhost:8000/api/contact \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Малик Юлдашев",
    "email": "malik@example.com",
    "phone": "+998 90 123 45 67",
    "comment": "Здравствуйте! Хотим обсудить разработку backend-сервиса."
  }'
```

**Ответ `201 Created`:**

```json
{
  "id": "659198ef0b9442a7b3a2dffbc02a4a9a",
  "received_at": "2026-06-20T11:11:51.654103+00:00",
  "name": "Малик Юлдашев",
  "email": "malik@example.com",
  "analysis": {
    "sentiment": "neutral",
    "category": "Сотрудничество",
    "priority": "medium",
    "summary": "Запрос на разработку backend-сервиса.",
    "suggested_reply": "Здравствуйте, Малик! Спасибо за обращение...",
    "source": "ai"
  },
  "email_status": { "owner": "sent", "user": "sent" },
  "message": "Спасибо! Ваше обращение принято."
}
```

### Обработка ошибок и статус-коды

Единый формат: `{"error": {"type", "message", "details?}}`.

| Код | Когда | Тип |
|---|---|---|
| `201` | обращение принято и обработано | — |
| `422` | ошибка валидации | `validation_error` |
| `429` | превышен лимит (заголовок `Retry-After`) | `rate_limit_exceeded` |
| `500` | непредвиденная ошибка (трейс — в лог, клиенту безопасный JSON) | `internal_error` |

Сбой отправки email **не валит** запрос: контакт уже сохранён, статус доставки
возвращается в `email_status` (`sent` / `failed` / `skipped`).

**Примеры запросов:** [`examples/api.http`](examples/api.http) и
[`examples/postman_collection.json`](examples/postman_collection.json).

---

## 5. AI-интеграция

**Что и зачем.** Один вызов Claude Haiku при каждом обращении выполняет сразу
три из перечисленных в ТЗ AI-сценариев: **анализ тональности** + **классификацию
типа запроса** + **генерацию черновика ответа** (плюс приоритет и краткое
summary). Результат используется и в письме владельцу, и в ответе API, и
показывается на лендинге.

**Надёжность через structured output.** Вызов делается с *forced tool-use*
(`tool_choice = record_analysis`) — модель обязана вернуть строго
типизированный JSON, который валидируется в Pydantic-модель `AIAnalysis`. Это
надёжнее, чем парсить свободный текст.

**Graceful fallback.** Если ключа нет, либо вызов упал/превысил таймаут —
`AIService` ловит **любое** исключение и возвращает безопасный результат с
`source = "fallback"` (нейтральная тональность, шаблонный ответ). Сервис никогда
не падает из-за AI. См. [`app/services/ai_service.py`](app/services/ai_service.py).

**Промпты.**

- *System:* «You are an assistant for a software developer's website. You triage
  inbound contact-form messages. Always answer by calling the record_analysis
  tool. Write the summary and suggested_reply in the same language as the message.»
- *User:* `Sender name: <name>` + текст сообщения.
- *Tool `record_analysis`* — JSON-схема с enum-полями `sentiment`/`priority` и
  свободной `category` (с примерами категорий в описании).

---

## 6. Что сделано с помощью AI (Claude Code)

Проект целиком разрабатывался в паре с Claude Code (агент Anthropic):

- **Генерация кода:** каркас FastAPI, слоистая структура, реализации `FileStore`/
  `RedisStore`, сервисы, middleware, тесты, фронтенд, конфиги Vercel — сгенерированы
  ассистентом по согласованному дизайну.
- **Промпты:** ход работы — «спроектировать бэкенд для лендинга по ТЗ», далее
  уточнение развилок (стек, AI-провайдер, email, хранилище, деплой) и пошаговая
  реализация со сквозной проверкой.
- **Что правил вручную / по итогам проверки:**
  - аннотация возврата роута `/` ломала генерацию `response_model` у FastAPI —
    добавлен `response_model=None`;
  - для Haiku 4.5 сознательно **не** передаются `thinking`/`effort` (на Haiku они
    дают 400) — это учтено в `AIService`;
  - хранилище вынесено за интерфейс `Store`, потому что у Vercel эфемерная ФС
    (см. раздел 7) — ключевое архитектурное решение, а не просто «файлы».
- **Проверка:** все эндпоинты прогнаны вживую (`curl`), 8 тестов pytest зелёные,
  лендинг проверен скриншотом в браузере.

---

## 7. Хранение данных

За единым интерфейсом `Store` — две реализации, переключаются `STORAGE_BACKEND`:

| | `file` (локально, по умолчанию) | `redis` (Upstash, прод) |
|---|---|---|
| **Логи обращений** | `data/contacts.jsonl` (JSON на строку) | список Redis (capped) |
| **Статистика** | `data/metrics.json` (атомарная запись) | hash Redis (`HINCRBY`) |
| **Rate limiting** | `data/ratelimit.json` (sliding window) | `INCR` + `EXPIRE` (fixed window) |
| **Логи запросов** | `logs/requests.log` (ротация) + stdout | stdout (Vercel Runtime Logs) |

**Почему два бэкенда.** ТЗ разрешает файловое хранилище, и оно реализовано как
дефолт для локального запуска. Но **Vercel — serverless с эфемерной файловой
системой**: писать можно только в `/tmp`, и это не шарится между инстансами. Чтобы
rate-limit и метрики реально персистились на проде, хранилище вынесено за интерфейс
`Repository` и добавлен **Redis-бэкенд (Upstash)** — корректный serverless-паттерн.
Файловые записи атомарны (`os.replace`) и защищены блокировкой, чтобы краш во время
записи не повредил данные.

---

## Безопасность

- **Валидация и санитизация** входных данных на Pydantic; HTML-экранирование
  пользовательского текста в письмах и в DOM на фронтенде (нет XSS).
- **Rate limiting устойчив к подделке IP:** идентичность клиента берётся из
  заголовков прокси (`X-Forwarded-For`/`X-Real-IP`) только за доверенным edge
  (авто-включается на Vercel); иначе — из TCP-пира, который клиент подделать не
  может. Подделка `X-Forwarded-For` не обходит лимит (есть тест).
- **Защита от спам-релея:** копия письма уходит на неподтверждённый адрес
  пользователя, поэтому она дополнительно ограничена **по получателю**
  (`EMAIL_RECIPIENT_MAX`) — форму нельзя использовать для рассылки спама на
  чужой email.
- **Безопасные ошибки:** клиенту — общий JSON без внутренних деталей, полный
  трейс — только в лог.
- **CORS** настраивается через `CORS_ORIGINS`. Дефолт `*` безопасен для этого
  публичного API (без авторизации и cookie, `allow_credentials=false`); для
  своего домена задайте список в проде.

## Деплой на Vercel

Сервис — единая serverless-функция (`api/index.py` экспортирует FastAPI-`app`);
`vercel.json` перенаправляет все пути на неё (API + Swagger + статика лендинга).

```bash
# один раз: подключить проект
vercel link

# прод-переменные окружения (для реальных AI/email/Redis)
vercel env add ANTHROPIC_API_KEY production
vercel env add RESEND_API_KEY production
vercel env add OWNER_EMAIL production
# для Redis-хранилища на проде:
vercel env add STORAGE_BACKEND production      # значение: redis
#   UPSTASH_REDIS_REST_URL / _TOKEN добавляются автоматически
#   при установке Upstash из Vercel Marketplace

# деплой
vercel --prod
```

Без ключей деплой тоже работает: AI → fallback, email → пропуск. Для прод-хранилища
поставьте Upstash Redis (Vercel Marketplace → Upstash, бесплатный тариф) и задайте
`STORAGE_BACKEND=redis`.

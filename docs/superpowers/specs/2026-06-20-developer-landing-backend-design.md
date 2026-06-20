# Developer Landing Backend — Design Spec

**Date:** 2026-06-20
**Status:** Approved (all key decisions confirmed with the user)

## Goal

Backend service for a developer's landing presentation: a REST API for the
contact form with validation, email notifications, rate limiting, request
logging, a mandatory AI enrichment step with a graceful fallback, Swagger docs,
a layered architecture, a small landing frontend, and a live deployment.

## Confirmed decisions

| Area      | Choice |
|-----------|--------|
| Language  | Python 3.12 |
| Framework | FastAPI (auto Swagger/OpenAPI, Pydantic validation, async) |
| AI        | Anthropic `claude-haiku-4-5`, structured output via forced tool-use |
| Email     | Resend (owner notification + copy to the user) |
| Storage   | Repository abstraction: `file` (local default) / `redis` (Upstash, prod) |
| Frontend  | Single-page landing with a working contact form |
| Deploy    | Vercel (one serverless function serves API + Swagger + static) |

## Request lifecycle (the full cycle required by the brief)

```
POST /api/contact
  → CORS + request-logging middleware (request_id, latency, status)
  → Pydantic validation (name, email, phone, comment)
  → Rate limit per client IP (429 + Retry-After on breach)
  → AIService.analyze(comment)        Anthropic Haiku, forced tool-use
        sentiment | category | priority | summary | suggested_reply
        graceful fallback: no key / timeout / error → neutral default, source="fallback"
  → Store.save_contact(record) + Store.bump_metrics(...)
  → EmailService: owner notification (incl. AI analysis + draft reply) + user copy
  → 201 Created: created record with AI block + per-recipient email_status
```

## Layered architecture (Controllers → Services → Repositories)

```
app/
  main.py            FastAPI app, CORS, global error handler, router wiring, static
  config.py          pydantic-settings (.env), env-var driven
  schemas/           Pydantic request/response models
  api/routes/        contact · health · metrics        (thin controllers)
  services/          contact_service · ai_service · email_service   (business logic)
  repositories/      base (interfaces) · file_store · redis_store · factory
  core/              logging · rate_limit · errors (custom exceptions + handlers)
  middleware/        request_logging
api/index.py         Vercel ASGI entrypoint
frontend/            index.html + static (landing with the form)
tests/               pytest: validation, rate-limit, AI fallback, health, metrics
```

## Endpoints

| Method | Path           | Purpose |
|--------|----------------|---------|
| POST   | `/api/contact` | Submit the contact form (the full cycle above) |
| GET    | `/api/health`  | Liveness + configured capabilities |
| GET    | `/api/metrics` | Aggregated statistics |
| GET    | `/docs`        | Swagger UI (built into FastAPI) |
| GET    | `/openapi.json`| OpenAPI schema |
| GET    | `/`            | Landing page |

## Error handling / status codes

- `422` — validation errors (customised JSON body)
- `429` — rate limit exceeded (`Retry-After` header)
- `500` — global catch-all, safe JSON, full traceback to the log
- Email failure does **not** fail the request (the contact is already stored);
  it is reported in `email_status`.

## AI function

One Anthropic Haiku call via forced tool-use returns strict JSON:
`sentiment` + request `category` + `priority` + one-line `summary` + a ready
`suggested_reply`. This covers three of the AI scenarios the brief lists
(sentiment analysis, request classification, auto-reply generation) in a single
request. The fallback path is fully isolated — the service runs without a key.

## Storage on Vercel (the tricky bit)

The brief allows file storage; Vercel is serverless with an **ephemeral
filesystem** (only `/tmp` is writable and it is not shared across instances).
The storage layer therefore sits behind a `Store` interface with two
implementations, switched via `STORAGE_BACKEND`:

- `file` — local default: logs in `logs/`, `data/metrics.json`,
  `data/ratelimit.json`, `data/contacts.jsonl`.
- `redis` — Upstash over HTTP: correct serverless pattern for rate-limit and
  metrics; request logs additionally go to stdout (Vercel Runtime Logs).

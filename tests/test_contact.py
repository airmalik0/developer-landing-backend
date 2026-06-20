"""End-to-end tests for the contact API (validation, AI fallback, rate limit)."""

from __future__ import annotations

from tests.conftest import VALID_PAYLOAD


def test_submit_success(make_client):
    client = make_client()
    res = client.post("/api/contact", json=VALID_PAYLOAD)
    assert res.status_code == 201

    body = res.json()
    assert body["id"]
    assert body["name"] == VALID_PAYLOAD["name"]
    # No API key in tests → AI degrades gracefully.
    assert body["analysis"]["source"] == "fallback"
    assert body["analysis"]["sentiment"] in {"positive", "neutral", "negative"}
    assert body["analysis"]["suggested_reply"]
    # No Resend key → emails skipped, not failed.
    assert body["email_status"] == {"owner": "skipped", "user": "skipped"}
    assert "X-Request-ID" in res.headers


def test_validation_rejects_bad_email(make_client):
    client = make_client()
    payload = {**VALID_PAYLOAD, "email": "not-an-email"}
    res = client.post("/api/contact", json=payload)
    assert res.status_code == 422
    assert res.json()["error"]["type"] == "validation_error"


def test_validation_rejects_short_comment(make_client):
    client = make_client()
    payload = {**VALID_PAYLOAD, "comment": "hi"}
    res = client.post("/api/contact", json=payload)
    assert res.status_code == 422


def test_validation_rejects_bad_phone(make_client):
    client = make_client()
    payload = {**VALID_PAYLOAD, "phone": "abc"}
    res = client.post("/api/contact", json=payload)
    assert res.status_code == 422


def test_rate_limit(make_client):
    client = make_client(RATE_LIMIT_MAX_REQUESTS="2")
    assert client.post("/api/contact", json=VALID_PAYLOAD).status_code == 201
    assert client.post("/api/contact", json=VALID_PAYLOAD).status_code == 201

    blocked = client.post("/api/contact", json=VALID_PAYLOAD)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["type"] == "rate_limit_exceeded"
    assert "Retry-After" in blocked.headers


def test_rate_limit_not_bypassed_by_spoofed_xff(make_client):
    # trust_proxy is off locally → client identity is the socket peer, so a
    # forged X-Forwarded-For must NOT reset the per-IP limit.
    client = make_client(RATE_LIMIT_MAX_REQUESTS="2")
    assert (
        client.post("/api/contact", json=VALID_PAYLOAD, headers={"X-Forwarded-For": "1.1.1.1"}).status_code
        == 201
    )
    assert (
        client.post("/api/contact", json=VALID_PAYLOAD, headers={"X-Forwarded-For": "2.2.2.2"}).status_code
        == 201
    )
    assert (
        client.post("/api/contact", json=VALID_PAYLOAD, headers={"X-Forwarded-For": "3.3.3.3"}).status_code
        == 429
    )


def test_health(make_client):
    client = make_client()
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["storage_backend"] == "file"
    assert body["ai_configured"] is False
    assert body["email_configured"] is False


def test_metrics_increment(make_client):
    client = make_client()
    client.post("/api/contact", json=VALID_PAYLOAD)
    client.post("/api/contact", json=VALID_PAYLOAD)

    res = client.get("/api/metrics")
    assert res.status_code == 200
    body = res.json()
    assert body["totals"]["total"] == 2
    assert body["by_sentiment"]["neutral"] == 2  # fallback => neutral
    assert body["ai"]["fallback"] == 2


def test_landing_served(make_client):
    client = make_client()
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]

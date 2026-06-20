"""Vercel serverless entrypoint.

Vercel's `@vercel/python` runtime detects the module-level ASGI ``app`` object
and serves it. All routing (API, Swagger, static frontend) is handled inside the
FastAPI application — `vercel.json` rewrites every path to this function.
"""

from app.main import app  # noqa: F401  (re-exported for the Vercel runtime)

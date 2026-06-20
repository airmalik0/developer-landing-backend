"""POST /api/contact — the contact-form controller (thin)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.middleware.request_logging import get_client_ip
from app.schemas.contact import ContactResponse
from app.schemas.contact import ContactRequest
from app.services.contact_service import ContactService

router = APIRouter(tags=["contact"])

# A sync handler so FastAPI runs it in a threadpool — the blocking Anthropic /
# Resend / file-IO calls then don't stall the event loop.


@router.post(
    "/contact",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit the contact form",
    responses={
        201: {"description": "Submission accepted and processed"},
        422: {"description": "Validation error"},
        429: {"description": "Rate limit exceeded"},
    },
)
def submit_contact(payload: ContactRequest, request: Request) -> ContactResponse:
    service = ContactService()
    return service.handle(payload, get_client_ip(request))

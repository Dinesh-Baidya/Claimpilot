"""
End-to-end workflow unit tests for ClaimPilot Concierge handler.
Uses mocked Context to verify card transitions, session data continuity,
idempotency, and validation handling without external dependencies.
"""
import asyncio
import json
import logging
from datetime import datetime
from uuid import uuid4
import pytest
from unittest.mock import MagicMock, patch

from uagents_core.contrib.protocols.chat import ChatMessage, TextContent, MetadataContent
from agents.concierge import handle_chat_message, state_machine


class MockContext:
    """Mock uAgents Context to record outbound messages and logging."""
    def __init__(self):
        self.sent_messages = []
        self.logger = logging.getLogger("mock_ctx")

    async def send(self, recipient: str, msg: ChatMessage):
        self.sent_messages.append((recipient, msg))


def create_msg(content) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=content if isinstance(content, list) else [content]
    )


def extract_metadata_content(chat_msg: ChatMessage):
    for item in chat_msg.content:
        if isinstance(item, MetadataContent):
            return item
    return None


@pytest.fixture(autouse=True)
def mock_external_services():
    """Mock Open-Meteo weather client and LLM drafter client to ensure deterministic, fast test execution."""
    with patch("agents.concierge.weather_client.get_weather_assessment") as mock_weather, \
         patch("agents.concierge.drafter.client", None):
        mock_weather.return_value = {
            "ok": True,
            "plausibility": "LOW",
            "plausibility_label": "Benign Operational Weather",
            "metrics": {
                "wind_gusts_kmh": 14.2,
                "visibility_meters": 10000,
                "weather_condition": "Clear Sky"
            },
            "rebuttal_text": "Departure weather at CDG was benign (wind 14 km/h, visibility 10000m).",
            "attribution": "Open-Meteo.com (CC BY 4.0)"
        }
        yield mock_weather


def test_workflow_initial_greeting_returns_intake_form():
    """Sending plain text input returns the welcome message and intake form card."""
    async def _run():
        ctx = MockContext()
        sender = "passenger_address_1"
        msg = create_msg(TextContent(type="text", text="Hello"))

        await handle_chat_message(ctx, sender, msg)

        assert len(ctx.sent_messages) == 1
        recipient, response = ctx.sent_messages[0]
        assert recipient == sender
        assert "Welcome to **ClaimPilot**" in response.content[0].text

        meta = extract_metadata_content(response)
        assert meta is not None
        assert "SUBMIT_INTAKE" in meta.metadata.get("card_payload", "")

    asyncio.run(_run())


def test_workflow_intake_submission_returns_evidence_not_form():
    """
    Submitting intake with agent mention returns the statutory evidence card,
    NOT the intake form again (Primary Bug Fix Verification).
    """
    async def _run():
        ctx = MockContext()
        sender = "passenger_address_2"
        session_id = f"cp_test_{uuid4().hex[:8]}"

        intake_payload = {
            "action": "SUBMIT_INTAKE",
            "session_id": session_id,
            "flight_number": "AF1680",
            "flight_date": "2026-10-25",
            "booking_ref": "PNR789",
            "passenger_name": "Alex Morgan",
            "passenger_email": "alex@example.com",
            "disruption_type": "CANCELLATION",
            "notice_days": "0",
            "airline_reason": "Technical malfunction",
            "approved": True
        }
        raw_text = f"@claimpilot_agent {json.dumps(intake_payload)}"
        msg = create_msg(TextContent(type="text", text=raw_text))

        await handle_chat_message(ctx, sender, msg)

        # Agent sends progress narration then evidence detail card
        assert len(ctx.sent_messages) == 2

        detail_recipient, detail_msg = ctx.sent_messages[1]
        assert detail_recipient == sender
        narration_text = detail_msg.content[0].text
        assert "Statutory Evaluation Complete for AF1680" in narration_text
        assert "250 EUR" in narration_text
        assert "Cash" in narration_text

        meta = extract_metadata_content(detail_msg)
        assert meta is not None
        card_payload = meta.metadata.get("card_payload", "")
        assert "ClaimPilot Audit" in card_payload
        assert "PROCEED_TO_DRAFT" in card_payload
        assert session_id in card_payload

        # Verify session state was saved in SQLite
        session = state_machine.get_session(session_id)
        assert session is not None
        assert session["state"] == "EVALUATED"
        assert session["data"]["flight_number"] == "AF1680"
        assert session["data"]["amount"] == 250

    asyncio.run(_run())


def test_workflow_draft_action_retrieves_session_and_builds_review_card():
    """Proceed to draft retrieves case data and presents human review card."""
    async def _run():
        ctx = MockContext()
        sender = "passenger_address_3"
        session_id = f"cp_test_{uuid4().hex[:8]}"

        case_data = {
            "flight_number": "AF1680",
            "flight_date": "2026-10-25",
            "passenger_name": "Alex Morgan",
            "passenger_email": "alex@example.com",
            "booking_ref": "PNR789",
            "origin": "CDG",
            "destination": "LHR",
            "disruption_type": "CANCELLATION",
            "amount": 250,
            "currency": "EUR",
            "statutory_citation": "Article 7(1)(a) of Regulation (EC) No 261/2004",
            "rebuttal_text": "Departure weather at CDG was benign."
        }
        state_machine.get_or_create_session(session_id)
        state_machine.update_session(session_id, "EVALUATED", case_data)

        proceed_msg = create_msg(TextContent(
            type="text",
            text=f"@claimpilot {json.dumps({'action': 'PROCEED_TO_DRAFT', 'session_id': session_id})}"
        ))

        await handle_chat_message(ctx, sender, proceed_msg)

        assert len(ctx.sent_messages) == 1
        recipient, response = ctx.sent_messages[0]
        assert "Formal Statutory Notice Generated" in response.content[0].text
        assert "Human-in-the-Loop Approval Gate" in response.content[0].text

        meta = extract_metadata_content(response)
        assert meta is not None
        card_payload = meta.metadata.get("card_payload", "")
        assert "APPROVE_AND_DISPATCH" in card_payload
        assert session_id in card_payload

        session = state_machine.get_session(session_id)
        assert session["state"] == "AWAITING_APPROVAL"
        assert "letter_text" in session["data"]

    asyncio.run(_run())


def test_workflow_approval_dispatch_and_idempotency():
    """Approval dispatches claim once, and duplicate submission is blocked idempotently."""
    async def _run():
        ctx = MockContext()
        sender = "passenger_address_4"
        session_id = f"cp_test_{uuid4().hex[:8]}"
        claim_id = f"CP{uuid4().hex[:6].upper()}"

        case_data = {
            "claim_id": claim_id,
            "flight_number": "6E205",
            "flight_date": "2026-10-25",
            "passenger_name": "Dinesh",
            "passenger_email": "dinesh@example.com",
            "booking_ref": f"PNR_{claim_id}",
            "amount": 7500,
            "currency": "INR",
            "verdict": {"regime": "DGCA_CAR_M_IV"}
        }
        state_machine.get_or_create_session(session_id)
        state_machine.update_session(session_id, "AWAITING_APPROVAL", case_data)

        approve_msg = create_msg(TextContent(
            type="text",
            text=f"@claimpilot {json.dumps({'action': 'APPROVE_AND_DISPATCH', 'claim_id': claim_id, 'session_id': session_id})}"
        ))

        # First dispatch
        await handle_chat_message(ctx, sender, approve_msg)
        assert len(ctx.sent_messages) == 1
        assert "Officially Dispatched" in ctx.sent_messages[0][1].content[0].text

        session = state_machine.get_session(session_id)
        assert session["state"] == "MONITORING"

        # Second dispatch (attempt duplicate)
        ctx.sent_messages.clear()
        await handle_chat_message(ctx, sender, approve_msg)
        assert len(ctx.sent_messages) == 1
        assert "Idempotent Guard Active" in ctx.sent_messages[0][1].content[0].text

    asyncio.run(_run())


def test_workflow_validation_missing_flight_number():
    """Submitting intake form without a flight number produces a helpful validation message."""
    async def _run():
        ctx = MockContext()
        sender = "passenger_address_5"
        session_id = f"cp_test_{uuid4().hex[:8]}"

        invalid_payload = {
            "action": "SUBMIT_INTAKE",
            "session_id": session_id,
            "flight_number": "",  # Missing flight number
            "booking_ref": "XYZ123"
        }
        msg = create_msg(TextContent(type="text", text=json.dumps(invalid_payload)))

        await handle_chat_message(ctx, sender, msg)

        assert len(ctx.sent_messages) == 1
        response = ctx.sent_messages[0][1]
        assert "Validation Notice" in response.content[0].text
        assert "Flight number is required" in response.content[0].text

    asyncio.run(_run())


def test_workflow_cancellation_action():
    """User cancelling a claim updates session state without sending notices."""
    async def _run():
        ctx = MockContext()
        sender = "passenger_address_6"
        session_id = f"cp_test_{uuid4().hex[:8]}"

        state_machine.get_or_create_session(session_id)
        state_machine.update_session(session_id, "AWAITING_APPROVAL", {"flight_number": "AF1680"})

        cancel_msg = create_msg(TextContent(
            type="text",
            text=json.dumps({"action": "CANCEL_CLAIM", "session_id": session_id})
        ))

        await handle_chat_message(ctx, sender, cancel_msg)

        assert len(ctx.sent_messages) == 1
        assert "Claim cancelled by user" in ctx.sent_messages[0][1].content[0].text
        session = state_machine.get_session(session_id)
        assert session["state"] == "CANCELLED"

    asyncio.run(_run())

"""
Unit tests for parse_incoming_selection in ClaimPilot Concierge.
Verifies robust JSON extraction, agent mention handling, metadata selection,
and graceful fallback for plain text and malformed payloads.
"""
import json
from datetime import datetime
from uuid import uuid4
import pytest

from uagents_core.contrib.protocols.chat import ChatMessage, TextContent, MetadataContent
from agents.concierge import parse_incoming_selection


def create_msg(content) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=content if isinstance(content, list) else [content]
    )


def test_parser_pure_json():
    """Valid JSON payload without mention."""
    payload = {"action": "SUBMIT_INTAKE", "flight_number": "AF1680", "booking_ref": "XYZ123"}
    msg = create_msg(TextContent(type="text", text=json.dumps(payload)))
    action, data = parse_incoming_selection(msg)
    assert action == "SUBMIT_INTAKE"
    assert data["flight_number"] == "AF1680"
    assert data["booking_ref"] == "XYZ123"


def test_parser_agent_mention_prefixed_json():
    """JSON preceded by an ASI:One agent mention (@agent1...)."""
    agent_mention = "@agent1qg4wkryvl6syggf4vhkhvvp2cxnptfd9h3tp0kv93v8q7x8w993eq59m7as"
    payload = {
        "flight_number": "QTR50",
        "flight_date": "2026-10-25",
        "booking_ref": "AB12CD",
        "passenger_name": "Dinesh",
        "passenger_email": "dinesh@example.com",
        "disruption_type": "CANCELLATION",
        "notice_days": "0",
        "airline_reason": "was cancelled due to Middle East airspace restrictions.",
        "action": "SUBMIT_INTAKE",
        "approved": True
    }
    raw_text = f"{agent_mention} {json.dumps(payload)}"
    msg = create_msg(TextContent(type="text", text=raw_text))

    action, data = parse_incoming_selection(msg)
    assert action == "SUBMIT_INTAKE"
    assert data["flight_number"] == "QTR50"
    assert data["booking_ref"] == "AB12CD"
    assert data["passenger_name"] == "Dinesh"
    assert data["notice_days"] == "0"
    assert data["approved"] is True


def test_parser_submit_intake_preserves_all_fields():
    """Verify all fields from intake form submission are preserved in payload."""
    payload = {
        "action": "SUBMIT_INTAKE",
        "session_id": "cp_test123",
        "flight_number": "BA249",
        "flight_date": "2026-11-01",
        "booking_ref": "PNR789",
        "passenger_name": "Sarah Connor",
        "passenger_email": "sarah@example.com",
        "disruption_type": "DELAY",
        "notice_days": "3",
        "airline_reason": "Hydraulic failure"
    }
    msg = create_msg(TextContent(type="text", text=f"@claimpilot {json.dumps(payload)}"))
    action, data = parse_incoming_selection(msg)

    assert action == "SUBMIT_INTAKE"
    for key, value in payload.items():
        assert data[key] == value


def test_parser_implicit_intake_from_flight_number():
    """Payload with flight_number but omitted action defaults to SUBMIT_INTAKE."""
    payload = {"flight_number": "LH102", "booking_ref": "LMN456"}
    msg = create_msg(TextContent(type="text", text=json.dumps(payload)))
    action, data = parse_incoming_selection(msg)

    assert action == "SUBMIT_INTAKE"
    assert data["flight_number"] == "LH102"


def test_parser_metadata_json_string_selection():
    """Structured selection passed as JSON string in MetadataContent."""
    selection = {"action": "PROCEED_TO_DRAFT", "session_id": "cp_abc"}
    meta = MetadataContent(type="metadata", metadata={"selection": json.dumps(selection)})
    msg = create_msg(meta)

    action, data = parse_incoming_selection(msg)
    assert action == "PROCEED_TO_DRAFT"
    assert data["session_id"] == "cp_abc"


def test_parser_metadata_approval_selection():
    """Approval action selection passed in MetadataContent."""
    selection = {"action": "APPROVE_AND_DISPATCH", "claim_id": "CP1234", "session_id": "cp_xyz"}
    meta = MetadataContent(type="metadata", metadata={"selection": json.dumps(selection)})
    msg = create_msg(meta)

    action, data = parse_incoming_selection(msg)
    assert action == "APPROVE_AND_DISPATCH"
    assert data["claim_id"] == "CP1234"
    assert data["session_id"] == "cp_xyz"


def test_parser_ordinary_text_input():
    """Plain user text message without any JSON."""
    msg = create_msg(TextContent(type="text", text="Hello, can you help me claim compensation?"))
    action, data = parse_incoming_selection(msg)

    assert action == "TEXT_INPUT"
    assert data["text"] == "Hello, can you help me claim compensation?"


def test_parser_text_with_invalid_braces():
    """Text that includes curly braces but is not valid JSON."""
    msg = create_msg(TextContent(type="text", text="My flight {CDG to LHR} was delayed by 5 hours."))
    action, data = parse_incoming_selection(msg)

    assert action == "TEXT_INPUT"
    assert "CDG to LHR" in data["text"]


def test_parser_malformed_json():
    """Malformed JSON string handled without throwing exceptions."""
    raw_text = "@agent1... {flight_number: QTR50, broken_json"
    msg = create_msg(TextContent(type="text", text=raw_text))

    action, data = parse_incoming_selection(msg)
    assert action == "TEXT_INPUT"
    assert raw_text in data["text"]


def test_parser_missing_or_unexpected_action():
    """Valid JSON dict with unknown or missing action."""
    payload = {"custom_field": "test_value"}
    msg = create_msg(TextContent(type="text", text=json.dumps(payload)))

    action, data = parse_incoming_selection(msg)
    assert action == ""
    assert data["custom_field"] == "test_value"

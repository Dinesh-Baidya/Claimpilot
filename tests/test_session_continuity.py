"""
Unit tests for session continuity and SQLite persistence in ClaimPilot.
Verifies that explicit session IDs propagate across card actions, separate claims
remain isolated, and sessions persist across state machine re-initialization.
"""
import tempfile
from pathlib import Path
from uuid import uuid4
import pytest

from agents.state_machine import ClaimStateMachine


@pytest.fixture
def temp_sm():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    sm = ClaimStateMachine(db_path=db_path)
    yield sm
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass


def test_new_intake_creates_session(temp_sm):
    """Creating a new session starts in INTAKE state with empty data."""
    session_id = f"cp_{uuid4().hex[:12]}"
    session = temp_sm.get_or_create_session(session_id, sender="sender_agent_1")
    assert session["session_id"] == session_id
    assert session["state"] == "INTAKE"
    assert session["data"] == {}


def test_intake_submission_reuses_correct_session(temp_sm):
    """Updating intake evaluation data preserves session_id and updates state."""
    session_id = f"cp_{uuid4().hex[:12]}"
    temp_sm.get_or_create_session(session_id, sender="sender_agent_1")

    case_data = {
        "flight_number": "AF1680",
        "flight_date": "2026-10-25",
        "amount": 250,
        "currency": "EUR"
    }
    temp_sm.update_session(session_id, "EVALUATED", case_data)

    retrieved = temp_sm.get_session(session_id)
    assert retrieved is not None
    assert retrieved["state"] == "EVALUATED"
    assert retrieved["data"]["flight_number"] == "AF1680"
    assert retrieved["data"]["amount"] == 250


def test_evidence_and_draft_reuse_same_session(temp_sm):
    """Proceeding to draft transitions state and retains previously evaluated case data."""
    session_id = f"cp_{uuid4().hex[:12]}"
    temp_sm.get_or_create_session(session_id)

    case_data = {"flight_number": "QTR50", "amount": 600, "currency": "EUR"}
    temp_sm.update_session(session_id, "EVALUATED", case_data)

    # Transition to drafting / awaiting approval
    case_data["letter_text"] = "Formal claim notice text"
    temp_sm.update_session(session_id, "AWAITING_APPROVAL", case_data)

    retrieved = temp_sm.get_session(session_id)
    assert retrieved["state"] == "AWAITING_APPROVAL"
    assert retrieved["data"]["letter_text"] == "Formal claim notice text"
    assert retrieved["data"]["flight_number"] == "QTR50"


def test_approval_action_reuses_session_and_records_claim(temp_sm):
    """Approval records claim with idempotency key and updates session state to MONITORING."""
    session_id = f"cp_{uuid4().hex[:12]}"
    temp_sm.get_or_create_session(session_id)

    case_data = {
        "flight_number": "6E205",
        "booking_ref": "ABC123",
        "passenger_email": "passenger@example.com",
        "amount": 7500,
        "currency": "INR"
    }
    temp_sm.update_session(session_id, "AWAITING_APPROVAL", case_data)

    claim_id = "CLM001"
    idempotency_key = f"dispatch_{claim_id}_{case_data['booking_ref']}"
    recorded = temp_sm.record_claim(
        claim_id=claim_id,
        session_id=session_id,
        passenger_email=case_data["passenger_email"],
        flight_number=case_data["flight_number"],
        amount=case_data["amount"],
        currency=case_data["currency"],
        regime="DGCA_CAR_M_IV",
        idempotency_key=idempotency_key,
        payload=case_data,
        accelerated_seconds=30
    )
    assert recorded is True

    temp_sm.update_session(session_id, "MONITORING", case_data)
    retrieved = temp_sm.get_session(session_id)
    assert retrieved["state"] == "MONITORING"


def test_two_independent_claims_use_separate_sessions(temp_sm):
    """Two different passengers/claims must have completely isolated state and data."""
    session_1 = f"cp_claim_1_{uuid4().hex[:6]}"
    session_2 = f"cp_claim_2_{uuid4().hex[:6]}"

    temp_sm.get_or_create_session(session_1)
    temp_sm.get_or_create_session(session_2)

    temp_sm.update_session(session_1, "EVALUATED", {"flight_number": "AF1680", "passenger_name": "Alice"})
    temp_sm.update_session(session_2, "EVALUATED", {"flight_number": "BA249", "passenger_name": "Bob"})

    retrieved_1 = temp_sm.get_session(session_1)
    retrieved_2 = temp_sm.get_session(session_2)

    assert retrieved_1["data"]["passenger_name"] == "Alice"
    assert retrieved_1["data"]["flight_number"] == "AF1680"

    assert retrieved_2["data"]["passenger_name"] == "Bob"
    assert retrieved_2["data"]["flight_number"] == "BA249"


def test_restarted_process_retrieves_saved_sessions(temp_sm):
    """A new ClaimStateMachine instance pointing to the same SQLite file retains all sessions."""
    session_id = f"cp_persist_{uuid4().hex[:8]}"
    temp_sm.get_or_create_session(session_id)
    temp_sm.update_session(session_id, "EVALUATED", {"flight_number": "LH102", "booking_ref": "PERSIST"})

    # Create fresh state machine pointing to same DB path
    new_sm = ClaimStateMachine(db_path=temp_sm.db_path)
    restored = new_sm.get_session(session_id)

    assert restored is not None
    assert restored["state"] == "EVALUATED"
    assert restored["data"]["booking_ref"] == "PERSIST"


def test_unknown_session_id_handled_safely(temp_sm):
    """Querying a non-existent session_id returns None without error."""
    assert temp_sm.get_session("non_existent_session_id_999") is None

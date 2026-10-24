"""
Session and Claim State Machine with SQLite Persistence.
Enables resilient recovery across restarts and supports Accelerated Clock mode for live demos.
"""
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = Path(__file__).parent.parent / "claimpilot.db"

class ClaimStateMachine:
    """Manages conversational session lifecycle and claim progress."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    sender TEXT,
                    state TEXT,
                    data_json TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claims (
                    claim_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    passenger_email TEXT,
                    flight_number TEXT,
                    amount REAL,
                    currency TEXT,
                    regime TEXT,
                    status TEXT,
                    dispatch_timestamp REAL,
                    deadline_timestamp REAL,
                    idempotency_key TEXT UNIQUE,
                    payload_json TEXT
                )
            """)
            conn.commit()

    def get_or_create_session(self, session_id: str, sender: str = "") -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT state, data_json FROM sessions WHERE session_id = ?", (session_id,))
            row = cur.fetchone()
            if row:
                return {
                    "session_id": session_id,
                    "state": row[0],
                    "data": json.loads(row[1]) if row[1] else {}
                }
            else:
                initial_data = {}
                now = datetime.utcnow().isoformat()
                cur.execute(
                    "INSERT INTO sessions (session_id, sender, state, data_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, sender, "INTAKE", json.dumps(initial_data), now, now)
                )
                conn.commit()
                return {
                    "session_id": session_id,
                    "state": "INTAKE",
                    "data": initial_data
                }

    def update_session(self, session_id: str, state: str, data: Dict[str, Any]):
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE sessions SET state = ?, data_json = ?, updated_at = ? WHERE session_id = ?",
                (state, json.dumps(data), now, session_id)
            )
            conn.commit()

    def record_claim(
        self,
        claim_id: str,
        session_id: str,
        passenger_email: str,
        flight_number: str,
        amount: float,
        currency: str,
        regime: str,
        idempotency_key: str,
        payload: Dict[str, Any],
        accelerated_seconds: int = 30
    ) -> bool:
        """Record dispatched claim. Ensures idempotency against duplicate emails/dispatches."""
        now = time.time()
        deadline = now + accelerated_seconds # Accelerated clock for demo mode
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO claims (
                        claim_id, session_id, passenger_email, flight_number,
                        amount, currency, regime, status, dispatch_timestamp,
                        deadline_timestamp, idempotency_key, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    claim_id, session_id, passenger_email, flight_number,
                    amount, currency, regime, "DISPATCHED", now,
                    deadline, idempotency_key, json.dumps(payload)
                ))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            # Already dispatched with this idempotency key
            return False

    def get_expired_claims(self) -> list:
        """Find claims where response deadline has elapsed for statutory escalation."""
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT claim_id, session_id, passenger_email, flight_number, amount, currency, regime, payload_json
                FROM claims
                WHERE status = 'DISPATCHED' AND deadline_timestamp <= ?
            """, (now,))
            return cur.fetchall()

    def mark_claim_status(self, claim_id: str, new_status: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE claims SET status = ? WHERE claim_id = ?", (new_status, claim_id))
            conn.commit()

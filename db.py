from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import streamlit as st
from supabase import Client, create_client


LOCAL_DB_PATH = Path(".data/rcv.sqlite")


def _secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def supabase_is_configured() -> bool:
    url = _secret("SUPABASE_URL")
    key = _secret("SUPABASE_KEY")
    return bool(url and key and "your-supabase-project" not in url and "your-anon-public-key" not in key)


def backend_name() -> str:
    return "Supabase" if supabase_is_configured() else "Local SQLite"


@st.cache_resource(show_spinner=False)
def get_supabase() -> Client | None:
    if not supabase_is_configured():
        return None

    try:
        return create_client(_secret("SUPABASE_URL"), _secret("SUPABASE_KEY"))
    except Exception:
        return None


def require_supabase() -> Client:
    client = get_supabase()
    if client is None:
        raise RuntimeError("Supabase is not configured.")
    return client


@st.cache_resource(show_spinner=False)
def get_local_connection() -> sqlite3.Connection:
    LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(LOCAL_DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    initialize_local_database(connection)
    return connection


def initialize_local_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS elections (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            seats_available INTEGER NOT NULL DEFAULT 1,
            status TEXT CHECK (status IN ('draft', 'active', 'completed')) DEFAULT 'draft',
            results_visible INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY,
            election_id TEXT REFERENCES elections(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            bio TEXT
        );

        CREATE TABLE IF NOT EXISTS voters (
            id TEXT PRIMARY KEY,
            election_id TEXT REFERENCES elections(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            token TEXT UNIQUE,
            has_voted INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS ballots (
            id TEXT PRIMARY KEY,
            election_id TEXT REFERENCES elections(id) ON DELETE CASCADE,
            ranking TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS candidates_election_id_idx ON candidates(election_id);
        CREATE INDEX IF NOT EXISTS voters_election_id_idx ON voters(election_id);
        CREATE INDEX IF NOT EXISTS voters_token_idx ON voters(token);
        CREATE INDEX IF NOT EXISTS ballots_election_id_idx ON ballots(election_id);
        """
    )
    connection.commit()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in ("has_voted", "results_visible"):
        if key in data:
            data[key] = bool(data[key])
    return data


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [_row_to_dict(row) for row in rows if row is not None]


def fetch_voter_by_token(token: str) -> dict[str, Any] | None:
    if supabase_is_configured():
        response = (
            require_supabase()
            .table("voters")
            .select("id, election_id, email, token, has_voted")
            .eq("token", token)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    row = get_local_connection().execute(
        "SELECT id, election_id, email, token, has_voted FROM voters WHERE token = ? LIMIT 1",
        (token,),
    ).fetchone()
    return _row_to_dict(row)


def fetch_election(election_id: str) -> dict[str, Any] | None:
    if supabase_is_configured():
        response = (
            require_supabase()
            .table("elections")
            .select("id, title, seats_available, status, results_visible, created_at")
            .eq("id", election_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    row = get_local_connection().execute(
        """
        SELECT id, title, seats_available, status, results_visible, created_at
        FROM elections
        WHERE id = ?
        LIMIT 1
        """,
        (election_id,),
    ).fetchone()
    return _row_to_dict(row)


def fetch_elections() -> list[dict[str, Any]]:
    if supabase_is_configured():
        response = (
            require_supabase()
            .table("elections")
            .select("id, title, seats_available, status, results_visible, created_at")
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []

    rows = get_local_connection().execute(
        """
        SELECT id, title, seats_available, status, results_visible, created_at
        FROM elections
        ORDER BY created_at DESC
        """
    ).fetchall()
    return _rows_to_dicts(rows)


def fetch_candidates(election_id: str) -> list[dict[str, Any]]:
    if supabase_is_configured():
        response = (
            require_supabase()
            .table("candidates")
            .select("id, election_id, name, bio")
            .eq("election_id", election_id)
            .order("name")
            .execute()
        )
        return response.data or []

    rows = get_local_connection().execute(
        "SELECT id, election_id, name, bio FROM candidates WHERE election_id = ? ORDER BY name",
        (election_id,),
    ).fetchall()
    return _rows_to_dicts(rows)


def fetch_voters(election_id: str) -> list[dict[str, Any]]:
    if supabase_is_configured():
        response = (
            require_supabase()
            .table("voters")
            .select("id, election_id, email, token, has_voted")
            .eq("election_id", election_id)
            .order("email")
            .execute()
        )
        return response.data or []

    rows = get_local_connection().execute(
        """
        SELECT id, election_id, email, token, has_voted
        FROM voters
        WHERE election_id = ?
        ORDER BY email
        """,
        (election_id,),
    ).fetchall()
    return _rows_to_dicts(rows)


def fetch_ballots(election_id: str) -> list[dict[str, Any]]:
    if supabase_is_configured():
        response = (
            require_supabase()
            .table("ballots")
            .select("id, election_id, ranking, created_at")
            .eq("election_id", election_id)
            .order("created_at")
            .execute()
        )
        return response.data or []

    rows = get_local_connection().execute(
        """
        SELECT id, election_id, ranking, created_at
        FROM ballots
        WHERE election_id = ?
        ORDER BY created_at
        """,
        (election_id,),
    ).fetchall()
    ballots = _rows_to_dicts(rows)
    for ballot in ballots:
        ballot["ranking"] = json.loads(ballot["ranking"])
    return ballots


def create_election(title: str, seats_available: int, candidates: list[dict[str, str]]) -> str:
    if supabase_is_configured():
        client = require_supabase()
        election = (
            client.table("elections")
            .insert({"title": title, "seats_available": seats_available, "status": "active"})
            .execute()
            .data[0]
        )
        rows = [
            {
                "election_id": election["id"],
                "name": candidate["name"],
                "bio": candidate.get("bio", ""),
            }
            for candidate in candidates
        ]
        if rows:
            client.table("candidates").insert(rows).execute()
        return election["id"]

    connection = get_local_connection()
    election_id = str(uuid.uuid4())
    with connection:
        connection.execute(
            """
            INSERT INTO elections (id, title, seats_available, status, results_visible)
            VALUES (?, ?, ?, 'active', 0)
            """,
            (election_id, title, seats_available),
        )
        connection.executemany(
            """
            INSERT INTO candidates (id, election_id, name, bio)
            VALUES (?, ?, ?, ?)
            """,
            [
                (str(uuid.uuid4()), election_id, candidate["name"], candidate.get("bio", ""))
                for candidate in candidates
            ],
        )
    return election_id


def add_voters(election_id: str, emails: list[str]) -> list[dict[str, Any]]:
    if supabase_is_configured():
        rows = [{"election_id": election_id, "email": email} for email in emails]
        if not rows:
            return []
        response = require_supabase().table("voters").insert(rows).execute()
        return response.data or []

    connection = get_local_connection()
    rows = [
        {
            "id": str(uuid.uuid4()),
            "election_id": election_id,
            "email": email,
            "token": str(uuid.uuid4()),
            "has_voted": False,
        }
        for email in emails
    ]
    with connection:
        connection.executemany(
            """
            INSERT INTO voters (id, election_id, email, token, has_voted)
            VALUES (?, ?, ?, ?, 0)
            """,
            [(row["id"], row["election_id"], row["email"], row["token"]) for row in rows],
        )
    return rows


def update_results_visibility(election_id: str, visible: bool) -> None:
    if supabase_is_configured():
        (
            require_supabase()
            .table("elections")
            .update({"results_visible": visible})
            .eq("id", election_id)
            .execute()
        )
        return

    with get_local_connection() as connection:
        connection.execute(
            "UPDATE elections SET results_visible = ? WHERE id = ?",
            (1 if visible else 0, election_id),
        )


def update_election_status(election_id: str, status: str) -> None:
    if supabase_is_configured():
        (
            require_supabase()
            .table("elections")
            .update({"status": status})
            .eq("id", election_id)
            .execute()
        )
        return

    with get_local_connection() as connection:
        connection.execute("UPDATE elections SET status = ? WHERE id = ?", (status, election_id))


def submit_ballot(voter_id: str, election_id: str, ranking: list[str]) -> None:
    if supabase_is_configured():
        require_supabase().rpc(
            "submit_ballot",
            {
                "p_voter_id": voter_id,
                "p_election_id": election_id,
                "p_ranking": ranking,
            },
        ).execute()
        return

    connection = get_local_connection()
    with connection:
        voter = connection.execute(
            """
            SELECT id, has_voted
            FROM voters
            WHERE id = ? AND election_id = ?
            LIMIT 1
            """,
            (voter_id, election_id),
        ).fetchone()
        if voter is None:
            raise RuntimeError("Invalid voter.")
        if bool(voter["has_voted"]):
            raise RuntimeError("Voting link has already been used.")

        connection.execute(
            "INSERT INTO ballots (id, election_id, ranking) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), election_id, json.dumps(ranking)),
        )
        connection.execute("UPDATE voters SET has_voted = 1 WHERE id = ?", (voter_id,))

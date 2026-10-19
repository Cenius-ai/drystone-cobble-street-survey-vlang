"""Data access for the survey register.

Every query in this module is a single static SQL literal with named bound
parameters — no SQL text is ever assembled from variables, so a value can never
reach the statement text. Optional filters are expressed as bound sentinels
(``:heritage = -1`` means "any"), and the one user-chosen ordering (streets) is
applied in Python from a fixed allowlist.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Sequence

PATCH_STATUSES = ("open", "repaired")
JOB_STATUSES = ("planned", "scheduled", "in-progress", "complete", "blocked")
SEVERITIES = ("low", "medium", "high")

STREET_SORTS = ("name", "district", "patches", "newest")


def now_iso() -> str:
    """Current UTC timestamp in ISO-8601 seconds precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- users

USER_BY_EMAIL = "SELECT * FROM users WHERE email = ? COLLATE NOCASE"
USER_BY_ID = "SELECT * FROM users WHERE id = ?"
INSERT_USER = (
    "INSERT INTO users (email, display_name, password_hash, created_at) "
    "VALUES (?, ?, ?, ?)"
)


def get_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute(USER_BY_EMAIL, (email.strip(),)).fetchone()


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(USER_BY_ID, (user_id,)).fetchone()


def create_user(
    conn: sqlite3.Connection, email: str, display_name: str, password_hash: str
) -> int:
    cursor = conn.execute(
        INSERT_USER, (email.strip(), display_name.strip(), password_hash, now_iso())
    )
    return int(cursor.lastrowid)


# ------------------------------------------------------------------------- streets

STREET_QUERY = """
    SELECT s.*,
           (SELECT COUNT(*) FROM patches p WHERE p.street_id = s.id) AS patch_count,
           (SELECT COUNT(*) FROM jobs j
              JOIN patches p2 ON p2.id = j.patch_id
             WHERE p2.street_id = s.id) AS job_count
      FROM streets s
     WHERE (:query = ''
            OR s.name LIKE :like
            OR s.district LIKE :like
            OR s.notes LIKE :like)
       AND (:heritage = -1 OR s.heritage_conservation_area = :heritage)
"""

STREET_BY_ID = "SELECT * FROM streets WHERE id = ?"
STREET_NAME_TAKEN = (
    "SELECT 1 FROM streets WHERE name = ? COLLATE NOCASE AND id <> ?"
)
STREET_NAME_TAKEN_ANY = "SELECT 1 FROM streets WHERE name = ? COLLATE NOCASE"
INSERT_STREET = """
    INSERT INTO streets (name, district, heritage_conservation_area, notes,
                         created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
"""
UPDATE_STREET = """
    UPDATE streets
       SET name = ?, district = ?, heritage_conservation_area = ?, notes = ?, updated_at = ?
     WHERE id = ?
"""
DELETE_STREET = "DELETE FROM streets WHERE id = ?"
STREET_PATCH_COUNT = "SELECT COUNT(*) AS n FROM patches WHERE street_id = ?"
STREET_JOB_COUNT = """
    SELECT COUNT(*) AS n FROM jobs j
      JOIN patches p ON p.id = j.patch_id
     WHERE p.street_id = ?
"""


def _street_sort_key(sort: str):
    if sort == "district":
        return lambda row: (str(row["district"]).casefold(), str(row["name"]).casefold())
    if sort == "patches":
        return lambda row: (-int(row["patch_count"]), str(row["name"]).casefold())
    if sort == "newest":
        return lambda row: (str(row["created_at"]), int(row["id"]))
    return lambda row: str(row["name"]).casefold()


def list_streets(
    conn: sqlite3.Connection,
    query: str = "",
    heritage: bool | None = None,
    sort: str = "name",
) -> list[sqlite3.Row]:
    heritage_flag = 1 if heritage is True else 0 if heritage is False else -1
    rows = conn.execute(
        STREET_QUERY,
        {
            "query": query,
            "like": f"%{query}%",
            "heritage": heritage_flag,
        },
    ).fetchall()
    key = _street_sort_key(sort if sort in STREET_SORTS else "name")
    ordered = sorted(rows, key=key, reverse=(sort == "newest"))
    return list(ordered)


def get_street(conn: sqlite3.Connection, street_id: int) -> sqlite3.Row | None:
    return conn.execute(STREET_BY_ID, (street_id,)).fetchone()


def street_name_taken(
    conn: sqlite3.Connection, name: str, exclude_id: int | None = None
) -> bool:
    if exclude_id is None:
        return conn.execute(STREET_NAME_TAKEN_ANY, (name.strip(),)).fetchone() is not None
    return (
        conn.execute(STREET_NAME_TAKEN, (name.strip(), exclude_id)).fetchone()
        is not None
    )


def create_street(
    conn: sqlite3.Connection,
    name: str,
    district: str,
    heritage: bool,
    notes: str,
) -> int:
    stamp = now_iso()
    cursor = conn.execute(
        INSERT_STREET,
        (name.strip(), district.strip(), 1 if heritage else 0, notes.strip(), stamp, stamp),
    )
    return int(cursor.lastrowid)


def update_street(
    conn: sqlite3.Connection,
    street_id: int,
    name: str,
    district: str,
    heritage: bool,
    notes: str,
) -> None:
    conn.execute(
        UPDATE_STREET,
        (
            name.strip(),
            district.strip(),
            1 if heritage else 0,
            notes.strip(),
            now_iso(),
            street_id,
        ),
    )


def delete_street(conn: sqlite3.Connection, street_id: int) -> None:
    conn.execute(DELETE_STREET, (street_id,))


def street_dependants(conn: sqlite3.Connection, street_id: int) -> tuple[int, int]:
    """Return (patch count, job count through patches) for a street."""
    patch_count = conn.execute(STREET_PATCH_COUNT, (street_id,)).fetchone()["n"]
    job_count = conn.execute(STREET_JOB_COUNT, (street_id,)).fetchone()["n"]
    return int(patch_count), int(job_count)


# ------------------------------------------------------------------------- patches

PATCHES_FOR_STREET = """
    SELECT p.*,
           (SELECT COUNT(*) FROM jobs j WHERE j.patch_id = p.id) AS job_count
      FROM patches p
     WHERE p.street_id = ?
     ORDER BY CASE p.status WHEN 'open' THEN 0 ELSE 1 END,
              p.severity = 'high' DESC, p.discovered_on DESC, p.id DESC
"""

PATCH_BY_ID = """
    SELECT p.*, s.name AS street_name, s.district AS street_district,
           s.heritage_conservation_area
      FROM patches p
      JOIN streets s ON s.id = p.street_id
     WHERE p.id = ?
"""

INSERT_PATCH = """
    INSERT INTO patches (street_id, location_description, sett_count, severity,
                         status, discovered_on, notes, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

UPDATE_PATCH = """
    UPDATE patches
       SET location_description = ?, sett_count = ?, severity = ?, status = ?,
           discovered_on = ?, notes = ?, updated_at = ?
     WHERE id = ?
"""

DELETE_PATCH = "DELETE FROM patches WHERE id = ?"
PATCH_JOB_COUNT = "SELECT COUNT(*) AS n FROM jobs WHERE patch_id = ?"


def list_patches_for_street(
    conn: sqlite3.Connection, street_id: int
) -> list[sqlite3.Row]:
    return list(conn.execute(PATCHES_FOR_STREET, (street_id,)).fetchall())


def get_patch(conn: sqlite3.Connection, patch_id: int) -> sqlite3.Row | None:
    return conn.execute(PATCH_BY_ID, (patch_id,)).fetchone()


def create_patch(
    conn: sqlite3.Connection,
    street_id: int,
    location_description: str,
    sett_count: int,
    severity: str,
    status: str,
    discovered_on: str,
    notes: str,
) -> int:
    stamp = now_iso()
    cursor = conn.execute(
        INSERT_PATCH,
        (
            street_id,
            location_description.strip(),
            sett_count,
            severity,
            status,
            discovered_on,
            notes.strip(),
            stamp,
            stamp,
        ),
    )
    return int(cursor.lastrowid)


def update_patch(
    conn: sqlite3.Connection,
    patch_id: int,
    location_description: str,
    sett_count: int,
    severity: str,
    status: str,
    discovered_on: str,
    notes: str,
) -> None:
    conn.execute(
        UPDATE_PATCH,
        (
            location_description.strip(),
            sett_count,
            severity,
            status,
            discovered_on,
            notes.strip(),
            now_iso(),
            patch_id,
        ),
    )


def delete_patch(conn: sqlite3.Connection, patch_id: int) -> None:
    conn.execute(DELETE_PATCH, (patch_id,))


def patch_job_count(conn: sqlite3.Connection, patch_id: int) -> int:
    return int(conn.execute(PATCH_JOB_COUNT, (patch_id,)).fetchone()["n"])


# --------------------------------------------------------------------------- crews

CREW_QUERY = """
    SELECT c.*,
           (SELECT COUNT(*) FROM jobs j WHERE j.crew_id = c.id) AS job_count
      FROM crews c
     WHERE (:only_active = 0 OR c.active = 1)
     ORDER BY c.active DESC, c.name COLLATE NOCASE ASC
"""

CREW_BY_ID = """
    SELECT c.*,
           (SELECT COUNT(*) FROM jobs j WHERE j.crew_id = c.id) AS job_count
      FROM crews c
     WHERE c.id = ?
"""

INSERT_CREW = (
    "INSERT INTO crews (name, foreman, active, created_at, updated_at) "
    "VALUES (?, ?, 1, ?, ?)"
)
UPDATE_CREW = "UPDATE crews SET name = ?, foreman = ?, updated_at = ? WHERE id = ?"
TOGGLE_CREW = (
    "UPDATE crews SET active = CASE active WHEN 1 THEN 0 ELSE 1 END, updated_at = ? "
    "WHERE id = ?"
)
DELETE_CREW = "DELETE FROM crews WHERE id = ?"
CREW_JOB_COUNT = "SELECT COUNT(*) AS n FROM jobs WHERE crew_id = ?"


def list_crews(conn: sqlite3.Connection, only_active: bool = False) -> list[sqlite3.Row]:
    return list(
        conn.execute(CREW_QUERY, {"only_active": 1 if only_active else 0}).fetchall()
    )


def get_crew(conn: sqlite3.Connection, crew_id: int) -> sqlite3.Row | None:
    return conn.execute(CREW_BY_ID, (crew_id,)).fetchone()


def create_crew(conn: sqlite3.Connection, name: str, foreman: str) -> int:
    stamp = now_iso()
    cursor = conn.execute(INSERT_CREW, (name.strip(), foreman.strip(), stamp, stamp))
    return int(cursor.lastrowid)


def update_crew(conn: sqlite3.Connection, crew_id: int, name: str, foreman: str) -> None:
    conn.execute(UPDATE_CREW, (name.strip(), foreman.strip(), now_iso(), crew_id))


def toggle_crew_active(conn: sqlite3.Connection, crew_id: int) -> None:
    conn.execute(TOGGLE_CREW, (now_iso(), crew_id))


def delete_crew(conn: sqlite3.Connection, crew_id: int) -> None:
    conn.execute(DELETE_CREW, (crew_id,))


def crew_job_count(conn: sqlite3.Connection, crew_id: int) -> int:
    return int(conn.execute(CREW_JOB_COUNT, (crew_id,)).fetchone()["n"])


# ---------------------------------------------------------------------------- jobs

# One static statement serves every jobs read (list, single, per patch, per crew,
# recent, consent gaps): each filter is a bound sentinel where -1 / '' / 0 means
# "do not restrict". Nothing is ever appended to this SQL text.
JOB_QUERY = """
    SELECT j.*,
           p.location_description AS patch_location,
           p.severity AS patch_severity,
           p.status AS patch_status,
           p.street_id AS street_id,
           s.name AS street_name,
           s.heritage_conservation_area AS heritage_conservation_area,
           c.name AS crew_name,
           c.active AS crew_active
      FROM jobs j
      JOIN patches p ON p.id = j.patch_id
      JOIN streets s ON s.id = p.street_id
      JOIN crews c ON c.id = j.crew_id
     WHERE (:job_id = -1 OR j.id = :job_id)
       AND (:patch_id = -1 OR j.patch_id = :patch_id)
       AND (:crew_id = -1 OR j.crew_id = :crew_id)
       AND (:street_id = -1 OR p.street_id = :street_id)
       AND (:statuses = '' OR instr(:statuses, ',' || j.status || ',') > 0)
       AND (:consent_gap_only = 0
            OR (s.heritage_conservation_area = 1
                AND TRIM(j.heritage_consent_ref) = ''))
       AND (:query = ''
            OR p.location_description LIKE :like
            OR s.name LIKE :like
            OR c.name LIKE :like)
     ORDER BY CASE j.status
                WHEN 'blocked' THEN 0
                WHEN 'in-progress' THEN 1
                WHEN 'scheduled' THEN 2
                WHEN 'planned' THEN 3
                ELSE 4
              END,
              j.updated_at DESC,
              j.id DESC
     LIMIT :limit
"""

INSERT_JOB = """
    INSERT INTO jobs (patch_id, crew_id, sett_count, status, heritage_consent_ref,
                      scheduled_for, notes, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

UPDATE_JOB = """
    UPDATE jobs
       SET crew_id = ?, sett_count = ?, status = ?, heritage_consent_ref = ?,
           scheduled_for = ?, notes = ?, updated_at = ?
     WHERE id = ?
"""

DELETE_JOB = "DELETE FROM jobs WHERE id = ?"


def _fetch_jobs(
    conn: sqlite3.Connection,
    job_id: int = -1,
    patch_id: int = -1,
    crew_id: int = -1,
    street_id: int = -1,
    statuses: Sequence[str] = (),
    query: str = "",
    consent_gap_only: bool = False,
    limit: int = -1,
) -> list[sqlite3.Row]:
    valid = [status for status in statuses if status in JOB_STATUSES]
    binds: dict[str, Any] = {
        "job_id": job_id,
        "patch_id": patch_id,
        "crew_id": crew_id,
        "street_id": street_id,
        "statuses": f",{','.join(valid)}," if valid else "",
        "query": query,
        "like": f"%{query}%",
        "consent_gap_only": 1 if consent_gap_only else 0,
        "limit": limit,
    }
    return list(conn.execute(JOB_QUERY, binds).fetchall())


def list_jobs(
    conn: sqlite3.Connection,
    statuses: Sequence[str] | None = None,
    street_id: int | None = None,
    query: str = "",
) -> list[sqlite3.Row]:
    return _fetch_jobs(
        conn,
        street_id=street_id if street_id is not None else -1,
        statuses=statuses or (),
        query=query,
    )


def get_job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    rows = _fetch_jobs(conn, job_id=job_id)
    return rows[0] if rows else None


def jobs_for_patch(conn: sqlite3.Connection, patch_id: int) -> list[sqlite3.Row]:
    return _fetch_jobs(conn, patch_id=patch_id)


def jobs_for_crew(conn: sqlite3.Connection, crew_id: int) -> list[sqlite3.Row]:
    return _fetch_jobs(conn, crew_id=crew_id)


def recent_jobs(conn: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    return _fetch_jobs(conn, limit=limit)


def heritage_gap_jobs(conn: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    """Jobs on heritage streets with no consent reference, in any status."""
    return _fetch_jobs(conn, consent_gap_only=True, limit=limit)


def create_job(
    conn: sqlite3.Connection,
    patch_id: int,
    crew_id: int,
    sett_count: int,
    status: str,
    heritage_consent_ref: str,
    scheduled_for: str,
    notes: str,
) -> int:
    stamp = now_iso()
    cursor = conn.execute(
        INSERT_JOB,
        (
            patch_id,
            crew_id,
            sett_count,
            status,
            heritage_consent_ref.strip(),
            scheduled_for,
            notes.strip(),
            stamp,
            stamp,
        ),
    )
    return int(cursor.lastrowid)


def update_job(
    conn: sqlite3.Connection,
    job_id: int,
    crew_id: int,
    sett_count: int,
    status: str,
    heritage_consent_ref: str,
    scheduled_for: str,
    notes: str,
) -> None:
    conn.execute(
        UPDATE_JOB,
        (
            crew_id,
            sett_count,
            status,
            heritage_consent_ref.strip(),
            scheduled_for,
            notes.strip(),
            now_iso(),
            job_id,
        ),
    )


def delete_job(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute(DELETE_JOB, (job_id,))


# ----------------------------------------------------------------------- dashboard

OPEN_PATCH_COUNT = "SELECT COUNT(*) AS n FROM patches WHERE status <> 'repaired'"
TOTAL_PATCH_COUNT = "SELECT COUNT(*) AS n FROM patches"
STREET_COUNT = "SELECT COUNT(*) AS n FROM streets"
HERITAGE_STREET_COUNT = (
    "SELECT COUNT(*) AS n FROM streets WHERE heritage_conservation_area = 1"
)
JOB_STATUS_COUNTS = "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
HERITAGE_GAP_COUNT = """
    SELECT COUNT(*) AS n
      FROM jobs j
      JOIN patches p ON p.id = j.patch_id
      JOIN streets s ON s.id = p.street_id
     WHERE s.heritage_conservation_area = 1
       AND TRIM(j.heritage_consent_ref) = ''
"""
SETTS_IN_OPEN_PATCHES = (
    "SELECT COALESCE(SUM(sett_count), 0) AS n FROM patches WHERE status <> 'repaired'"
)
TOTAL_SETTS = "SELECT COALESCE(SUM(sett_count), 0) AS n FROM patches"
RECENT_PATCHES = """
    SELECT p.*, s.name AS street_name, s.heritage_conservation_area
      FROM patches p
      JOIN streets s ON s.id = p.street_id
     ORDER BY p.created_at DESC, p.id DESC
     LIMIT ?
"""
DISTINCT_DISTRICTS = (
    "SELECT DISTINCT district FROM streets "
    "WHERE TRIM(district) <> '' ORDER BY district COLLATE NOCASE"
)


def open_patch_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute(OPEN_PATCH_COUNT).fetchone()["n"])


def total_patch_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute(TOTAL_PATCH_COUNT).fetchone()["n"])


def street_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute(STREET_COUNT).fetchone()["n"])


def heritage_street_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute(HERITAGE_STREET_COUNT).fetchone()["n"])


def job_counts_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {status: 0 for status in JOB_STATUSES}
    for row in conn.execute(JOB_STATUS_COUNTS):
        if row["status"] in counts:
            counts[row["status"]] = int(row["n"])
    return counts


def heritage_consent_gap_count(conn: sqlite3.Connection) -> int:
    """Jobs on heritage streets with no consent reference, in any status."""
    return int(conn.execute(HERITAGE_GAP_COUNT).fetchone()["n"])


def setts_in_open_patches(conn: sqlite3.Connection) -> int:
    return int(conn.execute(SETTS_IN_OPEN_PATCHES).fetchone()["n"])


def total_setts_recorded(conn: sqlite3.Connection) -> int:
    return int(conn.execute(TOTAL_SETTS).fetchone()["n"])


def recent_patches(conn: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    return list(conn.execute(RECENT_PATCHES, (limit,)).fetchall())


def distinct_districts(conn: sqlite3.Connection) -> list[str]:
    return [row["district"] for row in conn.execute(DISTINCT_DISTRICTS).fetchall()]

"""Idempotent seed: the demo operator plus a survey register worth looking at.

The seed runs on the normal boot path (see ``app.main.lifespan``) as well as
from ``python3 -m app.seed``. It exits — it never starts the HTTP server.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import auth, db
from .settings import database_path

DEMO_EMAIL = "cenius@cenius.ai"
DEMO_USERNAME = "cenius"
DEMO_PASSWORD = "cenius"
DEMO_DISPLAY_NAME = "Avery Ashdown"


def _stamp(days_ago: int = 0, hours_ago: int = 0) -> str:
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    return moment.isoformat(timespec="seconds")


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def seed_operator(conn: sqlite3.Connection) -> bool:
    """Create the demo operator if it is missing. Returns True when inserted."""
    existing = conn.execute(
        "SELECT id FROM users WHERE email = ? COLLATE NOCASE", (DEMO_EMAIL,)
    ).fetchone()
    if existing:
        return False
    conn.execute(
        """INSERT INTO users (email, display_name, password_hash, created_at)
           VALUES (?, ?, ?, ?)""",
        (DEMO_EMAIL, DEMO_DISPLAY_NAME, auth.hash_password(DEMO_PASSWORD), _stamp()),
    )
    return True


STREETS = [
    (
        "Cobble Lane",
        "Old Market",
        1,
        "Georgian setts between the market hall and Narrow Wine Street; heavily trafficked by delivery vans.",
        42,
    ),
    (
        "Rackhay Row",
        "Harbourside",
        1,
        "Listed quayside surface. All works need conservation officer sign-off before setts are lifted.",
        30,
    ),
    (
        "Wellington Terrace",
        "Clifton",
        0,
        "Wide terraced approach with a dropped kerb crossing at the north end.",
        36,
    ),
    (
        "Marsh Street Mews",
        "Central",
        0,
        "Rear service access for the mews properties; low vehicle use but heavy footfall at shift change.",
        24,
    ),
    (
        "Bellamy Walk",
        "Bedminster",
        0,
        "Pedestrianised walk beside the playground on the primary school route.",
        28,
    ),
    (
        "Quay Head Passage",
        "Redcliffe",
        0,
        "Narrow passage beneath the bridge arch; drainage gullies run along both sides.",
        19,
    ),
]

CREWS = [
    ("Yard Crew A", "Dan Whitcombe", 1),
    ("Yard Crew B", "Priya Raghunathan", 1),
    ("Setts Restoration Unit", "Marcus Ellery", 0),
]

# (street index, location, setts, severity, status, discovered offset, notes, created hours ago)
PATCHES = [
    (
        0,
        "Outside No. 14, gully course across the carriageway",
        42,
        "high",
        "open",
        -6,
        "Two courses rocking under load; cones in place and the gully cover is lifting.",
        3,
    ),
    (
        0,
        "Junction with Rackhay Row, two missing courses",
        18,
        "medium",
        "open",
        -12,
        "Loose setts stacked against the kerb by the mechanical sweeper.",
        20,
    ),
    (
        1,
        "Kerb-side channel opposite the bonded warehouse",
        27,
        "medium",
        "repaired",
        -41,
        "Re-laid and sanded by Yard Crew B; drained and checked after rain.",
        300,
    ),
    (
        1,
        "Footway outside No. 9, subsided setts",
        63,
        "high",
        "open",
        -3,
        "Subsidence over a culverted drain: excavation needed before re-bedding.",
        40,
    ),
    (
        2,
        "Crown of the road at the terrace steps",
        12,
        "low",
        "repaired",
        -55,
        "Tightened in place, no new stone required.",
        420,
    ),
    (
        2,
        "Dropped kerb crossing, loosened setts",
        34,
        "medium",
        "open",
        -9,
        "Crossing setts lifted at the tactile paving edge.",
        70,
    ),
    (
        3,
        "Rear service yard entrance",
        8,
        "low",
        "open",
        -18,
        "Three setts missing at the gate threshold; van traffic widening the gap.",
        120,
    ),
    (
        4,
        "Playground corner, chipped setts",
        21,
        "medium",
        "repaired",
        -33,
        "Chipped setts swapped for reclaimed stock from the depot.",
        200,
    ),
    (
        4,
        "Crossing approach, rocking setts",
        16,
        "high",
        "open",
        -2,
        "Rocking underfoot on the school route; temporary plate fitted.",
        8,
    ),
    (
        5,
        "Beneath the bridge arch, water tracking under the setts",
        55,
        "medium",
        "open",
        -15,
        "Gully blocked upstream; water is washing the bedding out from below.",
        100,
    ),
]

# (patch index, crew index, setts, status, consent ref, scheduled offset, notes, created hours ago)
JOBS = [
    (
        0,
        0,
        42,
        "scheduled",
        "HCA/2026/0184",
        5,
        "Conservation officer approved re-laying on lime mortar bedding.",
        5,
    ),
    (
        2,
        1,
        27,
        "planned",
        "",
        0,
        "Waiting on the harbour office for a revised consent reference.",
        60,
    ),
    (
        4,
        1,
        12,
        "complete",
        "",
        -21,
        "Re-laid, compacted and the footway reopened the same afternoon.",
        260,
    ),
    (
        3,
        0,
        63,
        "in-progress",
        "HCA/2026/0201",
        -4,
        "Excavation over the culvert complete; re-bedding setts this week.",
        30,
    ),
    (
        8,
        0,
        16,
        "blocked",
        "",
        2,
        "Blocked: traffic management order still pending with the street works team.",
        14,
    ),
    (
        7,
        1,
        21,
        "complete",
        "",
        -16,
        "Reclaimed setts laid to level with the playground kerb.",
        180,
    ),
]


def seed_survey(conn: sqlite3.Connection) -> bool:
    """Insert the sample survey register when the streets table is empty."""
    existing = conn.execute("SELECT COUNT(*) AS n FROM streets").fetchone()["n"]
    if existing:
        return False

    street_ids: list[int] = []
    for name, district, heritage, notes, created_hours in STREETS:
        cursor = conn.execute(
            """INSERT INTO streets (name, district, heritage_conservation_area, notes,
                                    created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                name,
                district,
                heritage,
                notes,
                _stamp(hours_ago=created_hours),
                _stamp(hours_ago=created_hours - 1),
            ),
        )
        street_ids.append(int(cursor.lastrowid))

    crew_ids: list[int] = []
    for name, foreman, active in CREWS:
        cursor = conn.execute(
            """INSERT INTO crews (name, foreman, active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name, foreman, active, _stamp(), _stamp()),
        )
        crew_ids.append(int(cursor.lastrowid))

    patch_ids: list[int] = []
    for (
        street_index,
        location,
        setts,
        severity,
        status,
        discovered,
        notes,
        created_hours,
    ) in PATCHES:
        street_id = street_ids[street_index]
        if street_id is None:  # defensive: a parent row must exist before children
            raise RuntimeError("seed parent street missing")
        cursor = conn.execute(
            """INSERT INTO patches (street_id, location_description, sett_count, severity,
                                    status, discovered_on, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                street_id,
                location,
                setts,
                severity,
                status,
                _day(discovered),
                notes,
                _stamp(hours_ago=created_hours),
                _stamp(hours_ago=max(created_hours - 1, 0)),
            ),
        )
        patch_ids.append(int(cursor.lastrowid))

    for (
        patch_index,
        crew_index,
        setts,
        status,
        consent,
        scheduled,
        notes,
        created_hours,
    ) in JOBS:
        patch_id = patch_ids[patch_index]
        crew_id = crew_ids[crew_index]
        if patch_id is None or crew_id is None:
            raise RuntimeError("seed parent patch or crew missing")
        conn.execute(
            """INSERT INTO jobs (patch_id, crew_id, sett_count, status, heritage_consent_ref,
                                 scheduled_for, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                patch_id,
                crew_id,
                setts,
                status,
                consent,
                _day(scheduled) if scheduled else "",
                notes,
                _stamp(hours_ago=created_hours),
                _stamp(hours_ago=max(created_hours - 1, 0)),
            ),
        )
    return True


def seed() -> dict[str, object]:
    """Create the schema, then seed the operator and (if empty) the register."""
    db.init_db()
    with db.session() as conn:
        operator_created = seed_operator(conn)
        survey_created = seed_survey(conn)
        counts = {
            "users": conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"],
            "streets": conn.execute("SELECT COUNT(*) AS n FROM streets").fetchone()["n"],
            "crews": conn.execute("SELECT COUNT(*) AS n FROM crews").fetchone()["n"],
            "patches": conn.execute("SELECT COUNT(*) AS n FROM patches").fetchone()["n"],
            "jobs": conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"],
        }
    return {
        "operator_created": operator_created,
        "survey_created": survey_created,
        "counts": counts,
        "database": str(Path(database_path())),
    }


def main() -> None:
    result = seed()
    counts = result["counts"]
    state = "seeded" if result["survey_created"] else "already present"
    print(f"Drystone seed complete ({state}) at {result['database']}")
    summary = ", ".join(f"{table}={count}" for table, count in dict(counts).items())
    print(f"rows: {summary}")
    print(f"demo operator: {DEMO_EMAIL} (password shown on the login page)")


if __name__ == "__main__":
    main()

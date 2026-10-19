-- Drystone Cobble Street Survey schema.
-- CHECK constraints are the second line of defence behind the server-side
-- validation in app/rules.py: an invalid status can never reach the table.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS streets (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    name                        TEXT NOT NULL UNIQUE,
    district                    TEXT NOT NULL DEFAULT '',
    heritage_conservation_area  INTEGER NOT NULL DEFAULT 0
                                CHECK (heritage_conservation_area IN (0, 1)),
    notes                       TEXT NOT NULL DEFAULT '',
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    foreman    TEXT NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patches (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    street_id            INTEGER NOT NULL REFERENCES streets(id),
    location_description TEXT NOT NULL,
    sett_count           INTEGER NOT NULL CHECK (sett_count > 0),
    severity             TEXT NOT NULL DEFAULT 'medium'
                         CHECK (severity IN ('low', 'medium', 'high')),
    status               TEXT NOT NULL DEFAULT 'open'
                         CHECK (status IN ('open', 'repaired')),
    discovered_on        TEXT NOT NULL DEFAULT '',
    notes                TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    patch_id              INTEGER NOT NULL REFERENCES patches(id),
    crew_id               INTEGER NOT NULL REFERENCES crews(id),
    sett_count            INTEGER NOT NULL CHECK (sett_count > 0),
    status                TEXT NOT NULL DEFAULT 'planned'
                          CHECK (status IN ('planned', 'scheduled', 'in-progress', 'complete', 'blocked')),
    heritage_consent_ref  TEXT NOT NULL DEFAULT '',
    scheduled_for         TEXT NOT NULL DEFAULT '',
    notes                 TEXT NOT NULL DEFAULT '',
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_patches_street_id ON patches(street_id);
CREATE INDEX IF NOT EXISTS ix_patches_status ON patches(status);
CREATE INDEX IF NOT EXISTS ix_jobs_patch_id ON jobs(patch_id);
CREATE INDEX IF NOT EXISTS ix_jobs_crew_id ON jobs(crew_id);
CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status);

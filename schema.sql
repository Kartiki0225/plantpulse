-- PlantPulse database schema.
-- Every fact is stored once: a machine's name lives only in machines,
-- a downtime reason's name lives only in downtime_reasons, and so on.

CREATE TABLE IF NOT EXISTS machines (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    line                TEXT    NOT NULL,
    -- Parts per hour the machine makes when it runs perfectly.
    ideal_rate_per_hour INTEGER NOT NULL CHECK (ideal_rate_per_hour > 0)
);

CREATE TABLE IF NOT EXISTS shifts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    start_time      TEXT    NOT NULL,
    end_time        TEXT    NOT NULL,
    -- Minutes the machine is supposed to run in this shift (breaks removed).
    planned_minutes INTEGER NOT NULL CHECK (planned_minutes > 0)
);

-- One row = what one machine produced in one shift on one date.
CREATE TABLE IF NOT EXISTS production_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id     INTEGER NOT NULL REFERENCES machines(id),
    shift_id       INTEGER NOT NULL REFERENCES shifts(id),
    log_date       TEXT    NOT NULL,               -- YYYY-MM-DD
    total_parts    INTEGER NOT NULL CHECK (total_parts >= 0),
    rejected_parts INTEGER NOT NULL CHECK (rejected_parts >= 0),
    CHECK (rejected_parts <= total_parts),
    UNIQUE (machine_id, shift_id, log_date)        -- no duplicate entries for a shift
);

CREATE TABLE IF NOT EXISTS downtime_reasons (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- One row = one stoppage during a logged shift. A shift can have many.
CREATE TABLE IF NOT EXISTS downtime_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    production_log_id INTEGER NOT NULL REFERENCES production_logs(id) ON DELETE CASCADE,
    reason_id         INTEGER NOT NULL REFERENCES downtime_reasons(id),
    minutes           INTEGER NOT NULL CHECK (minutes > 0)
);

CREATE INDEX IF NOT EXISTS idx_logs_date ON production_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_downtime_log ON downtime_events(production_log_id);

-- A view is a saved query that can be used like a table.
-- This one gives the numbers needed for OEE, one row per production log.
-- LEFT JOIN keeps shifts that had no downtime at all (their downtime becomes 0).
CREATE VIEW IF NOT EXISTS log_totals AS
SELECT
    p.id                                         AS log_id,
    p.log_date,
    m.id                                         AS machine_id,
    m.name                                       AS machine_name,
    m.line,
    s.name                                       AS shift_name,
    s.planned_minutes,
    COALESCE(SUM(d.minutes), 0)                  AS downtime_minutes,
    s.planned_minutes - COALESCE(SUM(d.minutes), 0) AS run_minutes,
    p.total_parts,
    p.rejected_parts,
    p.total_parts - p.rejected_parts             AS good_parts,
    -- Parts the machine should have made in the time it was actually running.
    (s.planned_minutes - COALESCE(SUM(d.minutes), 0)) / 60.0 * m.ideal_rate_per_hour AS ideal_parts
FROM production_logs p
JOIN machines m ON m.id = p.machine_id
JOIN shifts   s ON s.id = p.shift_id
LEFT JOIN downtime_events d ON d.production_log_id = p.id
GROUP BY p.id;

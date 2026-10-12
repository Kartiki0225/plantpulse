"""Everything that talks to the database lives in this file.

The routes in app.py call these functions and never write SQL themselves.
"""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from flask import g

HERE = Path(__file__).parent
DB_PATH = HERE / "plantpulse.db"


def get_db() -> sqlite3.Connection:
    """Open one connection per web request and reuse it within that request."""
    if "db" not in g:
        g.db = connect()
    return g.db


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row            # lets us read columns by name
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores foreign keys unless asked
    return conn


def close_db(error=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    """Create the tables and the view if they do not exist yet."""
    conn.executescript((HERE / "schema.sql").read_text())
    conn.commit()


# ---------------------------------------------------------------- lookups

def list_machines() -> list[dict]:
    rows = get_db().execute("SELECT * FROM machines ORDER BY line, name").fetchall()
    return [dict(row) for row in rows]


def list_shifts() -> list[dict]:
    rows = get_db().execute("SELECT * FROM shifts ORDER BY start_time").fetchall()
    return [dict(row) for row in rows]


def list_reasons() -> list[dict]:
    rows = get_db().execute("SELECT * FROM downtime_reasons ORDER BY name").fetchall()
    return [dict(row) for row in rows]


def add_machine(name: str, line: str, ideal_rate_per_hour: int) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO machines (name, line, ideal_rate_per_hour) VALUES (?, ?, ?)",
        (name, line, ideal_rate_per_hour),
    )
    db.commit()


# ---------------------------------------------------------------- production logs

class InvalidLog(ValueError):
    """Raised when a production log breaks one of the rules below."""


def add_log(machine_id, shift_id, log_date, total_parts, rejected_parts, downtime) -> int:
    """Save one production log together with its downtime events.

    downtime is a list of (reason_id, minutes) pairs.
    Both inserts happen in one transaction: either everything is saved or nothing is.
    """
    db = get_db()
    shift = db.execute("SELECT planned_minutes FROM shifts WHERE id = ?", (shift_id,)).fetchone()
    machine = db.execute("SELECT id FROM machines WHERE id = ?", (machine_id,)).fetchone()

    if shift is None or machine is None:
        raise InvalidLog("Choose a machine and a shift.")
    if total_parts < 0 or rejected_parts < 0:
        raise InvalidLog("Part counts cannot be negative.")
    if rejected_parts > total_parts:
        raise InvalidLog("Rejected parts cannot be more than total parts.")
    if any(minutes <= 0 for _, minutes in downtime):
        raise InvalidLog("Downtime minutes must be more than zero.")
    if sum(minutes for _, minutes in downtime) > shift["planned_minutes"]:
        raise InvalidLog(f"Downtime cannot be more than the shift's {shift['planned_minutes']} planned minutes.")

    try:
        cursor = db.execute(
            """INSERT INTO production_logs (machine_id, shift_id, log_date, total_parts, rejected_parts)
               VALUES (?, ?, ?, ?, ?)""",
            (machine_id, shift_id, log_date, total_parts, rejected_parts),
        )
        log_id = cursor.lastrowid
        db.executemany(
            "INSERT INTO downtime_events (production_log_id, reason_id, minutes) VALUES (?, ?, ?)",
            [(log_id, reason_id, minutes) for reason_id, minutes in downtime],
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise InvalidLog("This machine already has a log for that shift and date.")
    return log_id


def delete_log(log_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM production_logs WHERE id = ?", (log_id,))  # downtime rows cascade
    db.commit()


# ---------------------------------------------------------------- OEE
#
# OEE (Overall Equipment Effectiveness) = Availability x Performance x Quality
#   Availability = time actually running / time planned to run
#   Performance  = parts made / parts it should have made while running
#   Quality      = good parts / parts made
#
# NULLIF(x, 0) turns a zero into NULL so SQL does not divide by zero.

OEE_COLUMNS = """
    SUM(planned_minutes)  AS planned_minutes,
    SUM(downtime_minutes) AS downtime_minutes,
    SUM(total_parts)      AS total_parts,
    SUM(rejected_parts)   AS rejected_parts,
    1.0 * SUM(run_minutes) / SUM(planned_minutes)          AS availability,
    1.0 * SUM(total_parts) / NULLIF(SUM(ideal_parts), 0)   AS performance,
    1.0 * SUM(good_parts)  / NULLIF(SUM(total_parts), 0)   AS quality
"""


def with_oee(row: sqlite3.Row) -> dict:
    """Turn a result row into a dict and multiply the three ratios into OEE."""
    result = dict(row)
    for key in ("availability", "performance", "quality"):
        result[key] = round(result[key] or 0, 4)
    result["oee"] = round(result["availability"] * result["performance"] * result["quality"], 4)
    return result


def default_date_range() -> tuple[str, str]:
    """The 14 days ending on the most recent log (or today if there are no logs)."""
    latest = get_db().execute("SELECT MAX(log_date) FROM production_logs").fetchone()[0]
    end = date.fromisoformat(latest) if latest else date.today()
    return (end - timedelta(days=13)).isoformat(), end.isoformat()


def oee_overall(start: str, end: str) -> dict:
    row = get_db().execute(
        f"SELECT COUNT(*) AS logs, {OEE_COLUMNS} FROM log_totals WHERE log_date BETWEEN ? AND ?",
        (start, end),
    ).fetchone()
    return with_oee(row)


def oee_by_machine(start: str, end: str) -> list[dict]:
    rows = get_db().execute(
        f"""SELECT machine_id, machine_name, line, {OEE_COLUMNS}
            FROM log_totals
            WHERE log_date BETWEEN ? AND ?
            GROUP BY machine_id
            ORDER BY line, machine_name""",
        (start, end),
    ).fetchall()
    return [with_oee(row) for row in rows]


def oee_by_day(start: str, end: str) -> list[dict]:
    rows = get_db().execute(
        f"""SELECT log_date, {OEE_COLUMNS}
            FROM log_totals
            WHERE log_date BETWEEN ? AND ?
            GROUP BY log_date
            ORDER BY log_date""",
        (start, end),
    ).fetchall()
    return [with_oee(row) for row in rows]


def recent_logs(limit: int = 60) -> list[dict]:
    rows = get_db().execute(
        f"""SELECT log_id, log_date, machine_name, shift_name, {OEE_COLUMNS}
            FROM log_totals
            GROUP BY log_id
            ORDER BY log_date DESC, log_id DESC
            LIMIT ?""",
        (limit,),
    ).fetchall()
    return [with_oee(row) for row in rows]


def top_downtime_reasons(start: str, end: str) -> list[dict]:
    """Total minutes lost per reason, biggest first."""
    rows = get_db().execute(
        """SELECT r.name AS reason, SUM(d.minutes) AS minutes, COUNT(*) AS events
           FROM downtime_events d
           JOIN downtime_reasons r ON r.id = d.reason_id
           JOIN production_logs  p ON p.id = d.production_log_id
           WHERE p.log_date BETWEEN ? AND ?
           GROUP BY r.id
           ORDER BY minutes DESC""",
        (start, end),
    ).fetchall()
    return [dict(row) for row in rows]

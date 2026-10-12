"""Fill the database with sample data so the dashboard has something to show.

Run:  python seed.py      (this deletes existing data and creates 30 days of logs)
"""

import random
from datetime import date, timedelta

import db

MACHINES = [
    # name, line, ideal parts per hour
    ("CNC Lathe 1", "Line A", 60),
    ("CNC Lathe 2", "Line A", 60),
    ("Milling Center 1", "Line A", 40),
    ("Hydraulic Press 1", "Line B", 120),
    ("Welding Robot 1", "Line B", 45),
    ("Assembly Station 1", "Line B", 30),
]

SHIFTS = [
    # name, start, end, planned minutes (8 hours minus a 30 minute break)
    ("Morning", "06:00", "14:00", 450),
    ("Evening", "14:00", "22:00", 450),
    ("Night", "22:00", "06:00", 450),
]

REASONS = [
    "Breakdown",
    "Changeover / Setup",
    "Material Shortage",
    "Tool Change",
    "Power Cut",
    "Quality Check",
    "No Operator",
]

# Each machine behaves a little differently so the dashboard is not flat:
# (chance of a stoppage, speed compared to ideal, reject rate, most common reason)
BEHAVIOUR = {
    "CNC Lathe 1": (0.45, 0.93, 0.015, "Tool Change"),
    "CNC Lathe 2": (0.55, 0.88, 0.025, "Tool Change"),
    "Milling Center 1": (0.50, 0.90, 0.020, "Changeover / Setup"),
    "Hydraulic Press 1": (0.75, 0.82, 0.030, "Breakdown"),
    "Welding Robot 1": (0.50, 0.86, 0.060, "Quality Check"),
    "Assembly Station 1": (0.60, 0.80, 0.020, "Material Shortage"),
}

DAYS = 30


def main() -> None:
    random.seed(42)  # same "random" data every time
    conn = db.connect()
    db.init_db(conn)

    for table in ("downtime_events", "production_logs", "downtime_reasons", "shifts", "machines"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM sqlite_sequence")  # restart the id counters at 1

    conn.executemany("INSERT INTO machines (name, line, ideal_rate_per_hour) VALUES (?, ?, ?)", MACHINES)
    conn.executemany(
        "INSERT INTO shifts (name, start_time, end_time, planned_minutes) VALUES (?, ?, ?, ?)", SHIFTS
    )
    conn.executemany("INSERT INTO downtime_reasons (name) VALUES (?)", [(name,) for name in REASONS])

    machines = conn.execute("SELECT * FROM machines").fetchall()
    shifts = conn.execute("SELECT * FROM shifts").fetchall()
    reason_ids = {row["name"]: row["id"] for row in conn.execute("SELECT * FROM downtime_reasons")}

    logs = 0
    for days_ago in range(DAYS - 1, -1, -1):
        log_date = (date.today() - timedelta(days=days_ago)).isoformat()
        for machine in machines:
            stop_chance, speed, reject_rate, main_reason = BEHAVIOUR[machine["name"]]
            for shift in shifts:
                # Decide the stoppages for this shift.
                downtime = []
                while random.random() < stop_chance and len(downtime) < 3:
                    reason = main_reason if random.random() < 0.5 else random.choice(REASONS)
                    downtime.append((reason_ids[reason], random.randint(10, 55)))

                run_minutes = shift["planned_minutes"] - sum(minutes for _, minutes in downtime)
                actual_speed = speed * random.uniform(0.92, 1.05)
                total = int(run_minutes / 60 * machine["ideal_rate_per_hour"] * actual_speed)
                rejected = int(total * reject_rate * random.uniform(0.4, 1.8))

                cursor = conn.execute(
                    """INSERT INTO production_logs (machine_id, shift_id, log_date, total_parts, rejected_parts)
                       VALUES (?, ?, ?, ?, ?)""",
                    (machine["id"], shift["id"], log_date, total, rejected),
                )
                conn.executemany(
                    "INSERT INTO downtime_events (production_log_id, reason_id, minutes) VALUES (?, ?, ?)",
                    [(cursor.lastrowid, reason_id, minutes) for reason_id, minutes in downtime],
                )
                logs += 1

    conn.commit()
    conn.close()
    print(f"Added {len(MACHINES)} machines, {len(SHIFTS)} shifts and {logs} production logs.")


if __name__ == "__main__":
    main()

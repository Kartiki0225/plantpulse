# PlantPulse: Shop-Floor Production & Downtime Tracker

PlantPulse is a web app for a manufacturing line. Supervisors log what each machine produced in each shift and why it stopped, and the dashboard shows **OEE** per machine and the biggest causes of downtime.

Built with Python, Flask, SQLite and a small amount of JavaScript (Chart.js).

## What is OEE?

Overall Equipment Effectiveness is the standard measure of how well a machine is used.

```
OEE = Availability × Performance × Quality

Availability = time actually running / time planned to run
Performance  = parts made / parts it should have made while running
Quality      = good parts / parts made
```

Example: a 450 minute shift with 45 minutes of downtime, 360 parts made on a 60 parts/hour machine, 6 rejected.

- Availability = 405 / 450 = 90.0%
- Performance = 360 / (405 / 60 × 60) = 88.9%
- Quality = 354 / 360 = 98.3%
- OEE = 0.900 × 0.889 × 0.983 = **78.7%**

About 85% is considered world class.

## Features

- Log production per machine, shift and date, with any number of downtime events
- Validation: rejected parts cannot exceed total parts, downtime cannot exceed the shift, one log per machine per shift per day
- Dashboard with overall OEE, OEE per machine, top downtime causes and a daily trend, for any date range
- REST API that the dashboard itself uses
- Sample data generator (30 days, 6 machines, 3 shifts)

## Database design

Five tables, each storing one kind of thing:

```
machines ──┐
           ├──< production_logs ──< downtime_events >── downtime_reasons
shifts ────┘
```

| Table | One row is |
|---|---|
| `machines` | a machine, its line and its ideal parts per hour |
| `shifts` | a shift and its planned minutes |
| `production_logs` | what one machine made in one shift on one date |
| `downtime_reasons` | a reason a machine can stop |
| `downtime_events` | one stoppage during a logged shift |

A view called `log_totals` joins these tables and gives, for each log, the run time, downtime, good parts and ideal parts. Every OEE query is a `SUM ... GROUP BY` over that view. See `schema.sql` and `db.py`.

## REST API

| Method | Endpoint | Returns |
|---|---|---|
| GET | `/api/machines` | all machines |
| GET | `/api/oee/overall?from=&to=` | plant OEE for the date range |
| GET | `/api/oee/machines?from=&to=` | OEE per machine |
| GET | `/api/oee/daily?from=&to=` | OEE per day |
| GET | `/api/downtime/reasons?from=&to=` | minutes lost per reason, biggest first |
| GET | `/api/logs` | most recent logs |
| POST | `/api/logs` | creates a log (201), or 400 with an error message |

Dates are `YYYY-MM-DD`. Without dates, the API uses the 14 days ending on the most recent log.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python seed.py                  # creates the database with sample data
python app.py
```

Then open http://127.0.0.1:5000

## Files

| File | What it does |
|---|---|
| `schema.sql` | Tables, constraints, indexes and the `log_totals` view |
| `db.py` | All SQL queries and the validation rules |
| `app.py` | Flask routes: pages and the REST API |
| `seed.py` | Sample data |
| `templates/` | HTML pages (Jinja) |
| `static/` | CSS and the dashboard JavaScript |

## Limits

- No login, so anyone who can open the app can add or delete logs.
- SQLite suits one plant on one server. A larger setup would move to MySQL or PostgreSQL; the SQL would stay almost the same.

"""PlantPulse: log shop-floor production and downtime, and see OEE per machine.

Run:  python app.py      then open http://127.0.0.1:5000
"""

import sqlite3
from datetime import date

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

import db

app = Flask(__name__)
app.secret_key = "dev-only-key"  # only used to show flash messages
app.teardown_appcontext(db.close_db)

with app.app_context():
    db.init_db(db.get_db())


def date_range() -> tuple[str, str]:
    """Read ?from=YYYY-MM-DD&to=YYYY-MM-DD from the URL, or use the default range."""
    default_start, default_end = db.default_date_range()
    start = request.args.get("from") or default_start
    end = request.args.get("to") or default_end
    try:
        date.fromisoformat(start)
        date.fromisoformat(end)
    except ValueError:
        return default_start, default_end
    return start, end


# ---------------------------------------------------------------- pages

@app.get("/")
def dashboard():
    start, end = date_range()
    return render_template("dashboard.html", start=start, end=end)


@app.route("/log", methods=["GET", "POST"])
def log_production():
    if request.method == "POST":
        form = request.form
        try:
            # The form sends downtime as two parallel lists: reasons and minutes.
            downtime = [
                (int(reason_id), int(minutes))
                for reason_id, minutes in zip(form.getlist("reason_id"), form.getlist("minutes"))
                if reason_id and minutes
            ]
            db.add_log(
                machine_id=int(form["machine_id"]),
                shift_id=int(form["shift_id"]),
                log_date=date.fromisoformat(form["log_date"]).isoformat(),
                total_parts=int(form["total_parts"]),
                rejected_parts=int(form["rejected_parts"]),
                downtime=downtime,
            )
        except db.InvalidLog as error:
            flash(str(error), "error")
        except (KeyError, ValueError):
            flash("Fill every field with a valid value.", "error")
        else:
            flash("Production log saved.", "ok")
            return redirect(url_for("logs"))

    return render_template(
        "log_form.html",
        machines=db.list_machines(),
        shifts=db.list_shifts(),
        reasons=db.list_reasons(),
        today=date.today().isoformat(),
        form=request.form,
    )


@app.get("/logs")
def logs():
    return render_template("logs.html", logs=db.recent_logs())


@app.post("/logs/<int:log_id>/delete")
def delete_log(log_id: int):
    db.delete_log(log_id)
    flash("Log deleted.", "ok")
    return redirect(url_for("logs"))


@app.route("/machines", methods=["GET", "POST"])
def machines():
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            line = request.form["line"].strip()
            rate = int(request.form["ideal_rate_per_hour"])
            if not name or not line or rate <= 0:
                raise ValueError
            db.add_machine(name, line, rate)
        except sqlite3.IntegrityError:
            flash("A machine with that name already exists.", "error")
        except (KeyError, ValueError):
            flash("Enter a name, a line and an ideal rate above zero.", "error")
        else:
            flash("Machine added.", "ok")
            return redirect(url_for("machines"))

    return render_template("machines.html", machines=db.list_machines())


# ---------------------------------------------------------------- REST API
# The dashboard page gets all of its numbers from these endpoints as JSON.

@app.get("/api/machines")
def api_machines():
    return jsonify(db.list_machines())


@app.get("/api/oee/overall")
def api_oee_overall():
    start, end = date_range()
    return jsonify({"from": start, "to": end, **db.oee_overall(start, end)})


@app.get("/api/oee/machines")
def api_oee_machines():
    return jsonify(db.oee_by_machine(*date_range()))


@app.get("/api/oee/daily")
def api_oee_daily():
    return jsonify(db.oee_by_day(*date_range()))


@app.get("/api/downtime/reasons")
def api_downtime_reasons():
    return jsonify(db.top_downtime_reasons(*date_range()))


@app.get("/api/logs")
def api_logs():
    return jsonify(db.recent_logs())


@app.post("/api/logs")
def api_add_log():
    """Create a log from JSON, for example:

    {"machine_id": 1, "shift_id": 2, "log_date": "2026-10-12",
     "total_parts": 380, "rejected_parts": 9,
     "downtime": [{"reason_id": 1, "minutes": 25}]}
    """
    data = request.get_json(silent=True) or {}
    try:
        log_id = db.add_log(
            machine_id=int(data["machine_id"]),
            shift_id=int(data["shift_id"]),
            log_date=date.fromisoformat(data["log_date"]).isoformat(),
            total_parts=int(data["total_parts"]),
            rejected_parts=int(data["rejected_parts"]),
            downtime=[(int(d["reason_id"]), int(d["minutes"])) for d in data.get("downtime", [])],
        )
    except db.InvalidLog as error:
        return jsonify({"error": str(error)}), 400
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Missing or invalid fields."}), 400
    return jsonify({"id": log_id}), 201


if __name__ == "__main__":
    app.run(debug=True)

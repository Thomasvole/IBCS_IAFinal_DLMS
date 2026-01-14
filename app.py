from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime

from db import insert_session, get_connection
from helpers import ISVALIDMACHINEID, KEEPDIGITSONLY

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev"  # fine for IA demo; change later if needed

@app.route("/init-db")
def init_db():
    with open("schema.sql", "r", encoding="utf-8") as f:
        schema = f.read()

    with get_connection() as conn:
        conn.executescript(schema)
        conn.commit()

    return "Database initialized."

@app.route("/machine/<machine_id>/start", methods=["GET", "POST"])
def start_load(machine_id):
    # Step 1: validate machine id
    if not ISVALIDMACHINEID(machine_id):
        return "Invalid machine ID.", 400

    errors = []
    form_values = {"first_name": "", "last_name": "", "phone_number": ""}

    # GET: show empty form
    if request.method == "GET":
        return render_template("machine_start.html", machine_id=machine_id, errors=errors, values=form_values)

    # POST: extract inputs
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    phone_raw = request.form.get("phone_number") or ""

    form_values = {"first_name": first_name, "last_name": last_name, "phone_number": phone_raw}

    # clean phone
    phone_clean = KEEPDIGITSONLY(phone_raw)

    # validate
    if first_name == "":
        errors.append("First name is required.")
    if last_name == "":
        errors.append("Last name is required.")
    if len(phone_clean) != 10:
        errors.append("Phone number must be exactly 10 digits.")

    # if errors: show form again
    if len(errors) > 0:
        return render_template("machine_start.html", machine_id=machine_id, errors=errors, values=form_values)

    # create session
    time_in = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "active"

    session_id = insert_session(
        machine_id=machine_id,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_clean,
        time_in=time_in,
        status=status
    )

    return redirect(url_for("session_page", session_id=session_id))

@app.route("/session/<int:session_id>")
def session_page(session_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT SESSIONID, MACHINEID, FIRSTNAME, LASTNAME, PHONENUMBER, TIMEIN, STATUS FROM sessions WHERE SESSIONID = ?",
            (session_id,)
        ).fetchone()

    if row is None:
        return "Session not found.", 404

    return render_template("session_started.html", session=row)

if __name__ == '__main__':
    app.run()

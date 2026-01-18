from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime, timedelta
from db import insert_session, get_connection, get_session_by_id, update_finish_sms
from helpers import ISVALIDMACHINEID, KEEPDIGITSONLY
from dotenv import load_dotenv
load_dotenv()
from sms_service import send_finish_sms as twilio_send_finish_sms, build_finish_message

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev"  # fine for IA demo; change later if needed
CYCLE_DURATION_MINUTES = 1

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
    row = get_session_by_id(session_id)

    if row is None:
        return "Session not found.", 404
    time_in_dt = datetime.strptime(row["TIMEIN"], "%Y-%m-%d %H:%M:%S")
    expected_end_dt = time_in_dt + timedelta(minutes=CYCLE_DURATION_MINUTES)
    expected_end = expected_end_dt.strftime("%Y-%m-%d %H:%M:%S")
    expected_end_epoch = int(expected_end_dt.timestamp())

    return render_template("session_started.html", session=row, expected_end=expected_end, expected_end_epoch=expected_end_epoch)

@app.route("/session/<int:session_id>/send-finish-sms", methods=["POST"])
def send_finish_sms(session_id):
    row = get_session_by_id(session_id)
    if row is None:
        return jsonify({"error": "Session not found"}), 404

    message_preview = build_finish_message(row["MACHINEID"])

    current_status = row["FINISH_SMS_STATUS"] or ""
    if current_status.startswith("SENT"):
        return jsonify({
            "already_sent": True,
            "finish_sms_status": row["FINISH_SMS_STATUS"],
            "finish_sms_sent_at": row["FINISH_SMS_SENT_AT"],
            "message_preview": message_preview
        }), 200

    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = twilio_send_finish_sms(row["PHONENUMBER"], row["MACHINEID"])

    if result["success"]:
        status_text = f"SENT:{result['sid']}"
    else:
        status_text = f"FAILED:{result['error_type']}"

    update_finish_sms(session_id, status_text, sent_at)

    return jsonify({
        "already_sent": False,
        "success": status_text.startswith("SENT"),
        "finish_sms_status": status_text,
        "finish_sms_sent_at": sent_at,
        "message_preview": message_preview,
        "twilio_debug": result
    }), 200


if __name__ == '__main__':
    app.run()

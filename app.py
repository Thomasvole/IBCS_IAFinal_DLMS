from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime, timedelta
import secrets
import string
import os
import hmac

from db import (
    insert_session,
    get_connection,
    get_session_by_id,
    update_finish_sms,
    get_active_session_by_machine,
    set_verification_code,
    mark_picked_up,

    ensure_machine_exists,
    get_machine_by_id,
    set_machine_occupied,
    set_machine_vacant,
    update_machine_condition,

    get_machine_summary_stats,
)

from helpers import ISVALIDMACHINEID, KEEPDIGITSONLY
from dotenv import load_dotenv
load_dotenv()

from sms_service import send_finish_sms as twilio_send_finish_sms, build_finish_message

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev"

CYCLE_DURATION_MINUTES = 1
GRACE_MINUTES = 6  # SC6: grace period used when calculating pickup delay.

SUPERVISOR_CODE = os.getenv("SUPERVISOR_CODE", "767877")  # SC4/SC5: supervisor override for pickup/condition updates.


@app.route("/init-db")
def init_db():
    with open("schema.sql", "r", encoding="utf-8") as f:
        schema = f.read()

    with get_connection() as conn:
        conn.executescript(schema)
        conn.commit()

    return "Database initialized."


def generate_verification_code(length: int = 6) -> str:
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))


@app.route("/machine/<machine_id>/start", methods=["GET", "POST"])
def start_load(machine_id):
    # SC1: validate machine ID from the QR-based route.
    if not ISVALIDMACHINEID(machine_id):
        return "Invalid machine ID.", 400

    # SC5: ensure machine row exists and load occupancy/condition state.
    ensure_machine_exists(machine_id)
    machine = get_machine_by_id(machine_id)

    errors = []
    form_values = {"first_name": "", "last_name": "", "phone_number": ""}

    # SC4: check for an active session to require verification on re-scan.
    active = get_active_session_by_machine(machine_id)

    # SC1/SC4: GET shows verify screen if active session exists, otherwise start form.
    if request.method == "GET":
        if active is not None:
            return render_template(
                "verify_code.html",
                machine_id=machine_id,
                machine=machine,
                error=None
            )
        return render_template(
            "machine_start.html",
            machine_id=machine_id,
            machine=machine,
            errors=errors,
            values=form_values
        )

    # SC4 vs SC1/SC2/SC5/SC6: POST verifies pickup for active sessions or starts a new session.
    if active is not None:
        entered = (request.form.get("code") or "").strip()
        real = (active["VERIFICATION_CODE"] or "").strip()

        # SC4: accept session verification code or supervisor override for pickup.
        ok_student = hmac.compare_digest(str(entered), str(real))
        ok_supervisor = hmac.compare_digest(str(entered), str(SUPERVISOR_CODE))

        if not (ok_student or ok_supervisor):
            return render_template(
                "verify_code.html",
                machine_id=machine_id,
                machine=machine,
                error="Incorrect code."
            )

        return redirect(url_for("confirm_pickup", session_id=active["SESSIONID"]))

    # SC5: block starting new loads when the machine condition is broken.
    if machine is not None and machine["CONDITION_STATUS"] == "broken":
        return render_template(
            "machine_start.html",
            machine_id=machine_id,
            machine=machine,
            errors=["Machine is marked broken. New loads cannot be started."],
            values=form_values,
        )

    # SC1: collect student info and start a new session.
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    phone_raw = request.form.get("phone_number") or ""

    form_values = {"first_name": first_name, "last_name": last_name, "phone_number": phone_raw}
    phone_clean = KEEPDIGITSONLY(phone_raw)

    if first_name == "":
        errors.append("First name is required.")
    if last_name == "":
        errors.append("Last name is required.")
    if len(phone_clean) != 10:
        errors.append("Phone number must be exactly 10 digits.")

    if len(errors) > 0:
        return render_template(
            "machine_start.html",
            machine_id=machine_id,
            machine=machine,
            errors=errors,
            values=form_values
        )

    # SC2/SC6: record time in and calculate/store expected end time.
    time_in_dt = datetime.now()
    time_in = time_in_dt.strftime("%Y-%m-%d %H:%M:%S")

    expected_end_dt = time_in_dt + timedelta(minutes=CYCLE_DURATION_MINUTES)
    expected_end = expected_end_dt.strftime("%Y-%m-%d %H:%M:%S")

    status = "active"

    session_id = insert_session(
        machine_id=machine_id,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_clean,
        time_in=time_in,
        expected_end=expected_end,  # SC6
        status=status
    )

    code = generate_verification_code(6)
    set_verification_code(session_id, code)

    # SC5: mark machine occupied when a load starts.
    set_machine_occupied(machine_id)

    return redirect(url_for("session_page", session_id=session_id))


@app.route("/machine/<machine_id>/condition", methods=["POST"])
def change_machine_condition(machine_id):
    if not ISVALIDMACHINEID(machine_id):
        return "Invalid machine ID.", 400

    ensure_machine_exists(machine_id)

    action = request.form.get("action")  # SC5: report broken or resolve issue action.
    code_in = (request.form.get("supervisor_code") or "").strip()
    reason = (request.form.get("reason") or "").strip() or None

    if action not in ("REPORT_BROKEN", "RESOLVE_ISSUE"):
        return "Invalid action.", 400

    # SC5: require supervisor code to change machine condition.
    if not hmac.compare_digest(str(code_in), str(SUPERVISOR_CODE)):
        machine = get_machine_by_id(machine_id)
        active = get_active_session_by_machine(machine_id)
        msg = "Invalid supervisor code — condition not changed."

        if active is not None:
            return render_template(
                "verify_code.html",
                machine_id=machine_id,
                machine=machine,
                error=msg
            )

        return render_template(
            "machine_start.html",
            machine_id=machine_id,
            machine=machine,
            errors=[msg],
            values={"first_name": "", "last_name": "", "phone_number": ""}
        )

    new_condition = "broken" if action == "REPORT_BROKEN" else "normal"

    # SC5/SC6: update condition status and stamp problem timestamps.
    update_machine_condition(machine_id, new_condition, reason)

    return redirect(url_for("start_load", machine_id=machine_id))


@app.route("/session/<int:session_id>")
def session_page(session_id):
    row = get_session_by_id(session_id)
    if row is None:
        return "Session not found.", 404

    # SC2: use stored expected end to drive the countdown timer.
    expected_end = row["EXPECTED_END"]
    expected_end_dt = datetime.strptime(expected_end, "%Y-%m-%d %H:%M:%S")
    expected_end_epoch = int(expected_end_dt.timestamp())

    return render_template(
        "session_started.html",
        session=row,
        expected_end=expected_end,
        expected_end_epoch=expected_end_epoch
    )


@app.route("/session/<int:session_id>/send-finish-sms", methods=["POST"])
def send_finish_sms(session_id):
    row = get_session_by_id(session_id)
    if row is None:
        return jsonify({"error": "Session not found"}), 404

    message_preview = build_finish_message(row["MACHINEID"], row["FIRSTNAME"])

    current_status = row["FINISH_SMS_STATUS"] or ""
    if current_status.startswith("SENT"):
        return jsonify({
            "already_sent": True,
            "finish_sms_status": row["FINISH_SMS_STATUS"],
            "finish_sms_sent_at": row["FINISH_SMS_SENT_AT"],
            "message_preview": message_preview
        }), 200

    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = twilio_send_finish_sms(row["PHONENUMBER"], row["MACHINEID"], row["FIRSTNAME"])

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


@app.route("/session/<int:session_id>/confirm-pickup")
def confirm_pickup(session_id):
    row = get_session_by_id(session_id)
    if row is None:
        return "Session not found.", 404

    # SC6: show delay preview using grace rule.
    expected_end_dt = datetime.strptime(row["EXPECTED_END"], "%Y-%m-%d %H:%M:%S")
    now_dt = datetime.now()

    late_by_min = max(0, int((now_dt - expected_end_dt).total_seconds() // 60))
    delay_recorded = max(0, late_by_min - GRACE_MINUTES)

    return render_template(
        "confirm_pickup.html",
        session=row,
        machine_id=row["MACHINEID"],
        now_str=now_dt.strftime("%Y-%m-%d %H:%M:%S"),
        late_by_min=late_by_min,
        grace_min=GRACE_MINUTES,
        delay_recorded=delay_recorded
    )


@app.route("/session/<int:session_id>/pickup", methods=["POST"])
def pickup(session_id):
    row = get_session_by_id(session_id)
    if row is None:
        return "Session not found.", 404

    time_out_dt = datetime.now()
    time_out = time_out_dt.strftime("%Y-%m-%d %H:%M:%S")

    # SC6: compute delay with 6-minute grace.
    expected_end_dt = datetime.strptime(row["EXPECTED_END"], "%Y-%m-%d %H:%M:%S")
    late_by_min = max(0, int((time_out_dt - expected_end_dt).total_seconds() // 60))
    delay_min = max(0, late_by_min - GRACE_MINUTES)

    mark_picked_up(session_id, time_out, delay_min)

    # SC5: update occupancy when a load finishes
    set_machine_vacant(row["MACHINEID"])

    return redirect(url_for("start_load", machine_id=row["MACHINEID"]))


@app.route("/machine/<machine_id>/summary-login", methods=["GET", "POST"])
def summary_login(machine_id):
    if not ISVALIDMACHINEID(machine_id):
        return "Invalid machine ID.", 400

    ensure_machine_exists(machine_id)
    machine = get_machine_by_id(machine_id)

    error = None

    if request.method == "POST":
        code_in = (request.form.get("supervisor_code") or "").strip()

        if hmac.compare_digest(str(code_in), str(SUPERVISOR_CODE)):
            return redirect(url_for("machine_summary", machine_id=machine_id))

        error = "Invalid supervisor code."

    return render_template(
        "summary_login.html",
        machine_id=machine_id,
        machine=machine,
        error=error
    )


@app.route("/machine/<machine_id>/summary")
def machine_summary(machine_id):
    if not ISVALIDMACHINEID(machine_id):
        return "Invalid machine ID.", 400

    ensure_machine_exists(machine_id)
    machine = get_machine_by_id(machine_id)

    stats = get_machine_summary_stats(machine_id)

    return render_template(
        "summary.html",
        machine_id=machine_id,
        machine=machine,
        stats=stats,
        grace_min=GRACE_MINUTES
    )


if __name__ == "__main__":
    app.run()

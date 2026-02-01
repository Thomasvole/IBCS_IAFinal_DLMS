import os
import requests

def to_e164_us(phone10: str) -> str:
    return "+1" + phone10

def format_machine_location(machine_id: str) -> str:
    floor_code = machine_id[0]   # SC3: floor code (M/F) parsed from machine ID.
    hall = machine_id[1]         # SC3: hallway letter parsed from machine ID.
    num = int(machine_id[2])     # SC3: machine number parsed from machine ID.

    floor_text = "third floor (Boys)" if floor_code == "M" else "second floor (Girls)"
    machine_type = "washing machine" if 1 <= num <= 4 else "drying machine"

    return f"{machine_type} {num} in hallway {hall}, {floor_text}"

def build_finish_message(machine_id: str) -> str:
    location = format_machine_location(machine_id)
    return (
        "Your session is done. Please go to "
        f"{location} to pick up your load. "
        "Don't forget to check your belongings and report any issues to the boarding parent."
    )

def send_finish_sms(phone10: str, machine_id: str) -> dict:
    """
    Returns:
      { "success": True, "sid": "SM..." }
      { "success": False, "error_type": "...", "details": "..." }
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_number = os.environ.get("TWILIO_FROM_NUMBER", "").strip()

    if not account_sid or not auth_token or not from_number:
        return {
            "success": False,
            "error_type": "MISSING_CONFIG",
            "details": "Missing TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER"
        }

    to_number = to_e164_us(phone10)
    location = format_machine_location(machine_id)
    body = build_finish_message(machine_id)

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    try:
        resp = requests.post(
            url,
            data={"From": from_number, "To": to_number, "Body": body},
            auth=(account_sid, auth_token),
            timeout=15
        )

        if 200 <= resp.status_code < 300:
            data = resp.json()
            return {"success": True, "sid": data.get("sid", "SM_UNKNOWN")}
        else:
            # SC3: Twilio errors usually return JSON with message/code.
            try:
                err = resp.json()
                code = err.get("code")
                msg = err.get("message")
                return {"success": False, "error_type": f"TWILIO_{code or resp.status_code}", "details": msg or str(err)}
            except Exception:
                return {"success": False, "error_type": f"HTTP_{resp.status_code}", "details": resp.text}

    except requests.exceptions.Timeout:
        return {"success": False, "error_type": "TIMEOUT", "details": "Twilio request timed out"}
    except Exception as e:
        return {
            "success": False,
            "error_type": f"UNKNOWN_{type(e).__name__}",
            "details": repr(e)
        }



import sqlite3

DB_PATH = "dlms.sqlite3"


def get_connection() -> sqlite3.Connection:
    """
    Returns a new SQLite connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def insert_session(
    machine_id: str,
    first_name: str,
    last_name: str,
    phone_number: str,
    time_in: str,
    status: str
) -> int:
    """
    Inserts a new session row and returns the generated SESSIONID.
    (SC2/SC3 base insert; SC4 verification code will be set after insert.)
    """
    sql = """
        INSERT INTO sessions (MACHINEID, FIRSTNAME, LASTNAME, PHONENUMBER, TIMEIN, STATUS)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    with get_connection() as conn:
        cur = conn.execute(sql, (machine_id, first_name, last_name, phone_number, time_in, status))
        conn.commit()
        return int(cur.lastrowid)


def get_session_by_id(session_id: int) -> sqlite3.Row | None:
    """
    Returns one session row (SC3 + SC4 fields) or None if not found.
    """
    sql = """
        SELECT
            SESSIONID, MACHINEID, FIRSTNAME, LASTNAME, PHONENUMBER, TIMEIN, STATUS,
            FINISH_SMS_STATUS, FINISH_SMS_SENT_AT,
            VERIFICATION_CODE, TIMEOUT
        FROM sessions
        WHERE SESSIONID = ?
    """
    with get_connection() as conn:
        return conn.execute(sql, (session_id,)).fetchone()


def update_finish_sms(session_id: int, status_text: str, sent_at: str) -> None:
    """
    Updates SC3 finish SMS logging fields for a session.
    """
    sql = """
        UPDATE sessions
        SET FINISH_SMS_STATUS = ?, FINISH_SMS_SENT_AT = ?
        WHERE SESSIONID = ?
    """
    with get_connection() as conn:
        conn.execute(sql, (status_text, sent_at, session_id))
        conn.commit()


def get_active_session_by_machine(machine_id: str) -> sqlite3.Row | None:
    """
    Returns the most recent active session for a given machine, or None.
    (Used by SC4 when the same machine is scanned again.)
    """
    sql = """
        SELECT
            SESSIONID, MACHINEID, FIRSTNAME, LASTNAME, PHONENUMBER, TIMEIN, STATUS,
            FINISH_SMS_STATUS, FINISH_SMS_SENT_AT,
            VERIFICATION_CODE, TIMEOUT
        FROM sessions
        WHERE MACHINEID = ? AND STATUS = 'active'
        ORDER BY SESSIONID DESC
        LIMIT 1
    """
    with get_connection() as conn:
        return conn.execute(sql, (machine_id,)).fetchone()


def set_verification_code(session_id: int, code: str) -> None:
    """
    Sets the SC4 verification code for a session.
    """
    sql = """
        UPDATE sessions
        SET VERIFICATION_CODE = ?
        WHERE SESSIONID = ?
    """
    with get_connection() as conn:
        conn.execute(sql, (code, session_id))
        conn.commit()


def mark_picked_up(session_id: int, time_out: str) -> None:
    """
    Marks a session as picked up and records TIMEOUT (SC4).
    """
    sql = """
        UPDATE sessions
        SET STATUS = 'picked_up', TIMEOUT = ?
        WHERE SESSIONID = ?
    """
    with get_connection() as conn:
        conn.execute(sql, (time_out, session_id))
        conn.commit()
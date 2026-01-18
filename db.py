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
    Returns one session row (including SC3 SMS fields) or None if not found.
    """
    sql = """
        SELECT
            SESSIONID, MACHINEID, FIRSTNAME, LASTNAME, PHONENUMBER, TIMEIN, STATUS,
            FINISH_SMS_STATUS, FINISH_SMS_SENT_AT
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

def get_session_by_id(session_id: int) -> sqlite3.Row | None:
    sql = """
        SELECT
            SESSIONID, MACHINEID, FIRSTNAME, LASTNAME, PHONENUMBER, TIMEIN, STATUS,
            FINISH_SMS_STATUS, FINISH_SMS_SENT_AT
        FROM sessions
        WHERE SESSIONID = ?
    """
    with get_connection() as conn:
        return conn.execute(sql, (session_id,)).fetchone()


def update_finish_sms(session_id: int, status_text: str, sent_at: str) -> None:
    sql = """
        UPDATE sessions
        SET FINISH_SMS_STATUS = ?, FINISH_SMS_SENT_AT = ?
        WHERE SESSIONID = ?
    """
    with get_connection() as conn:
        conn.execute(sql, (status_text, sent_at, session_id))
        conn.commit()

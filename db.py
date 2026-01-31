import sqlite3
from datetime import datetime

DB_PATH = "dlms.sqlite3"


def get_connection() -> sqlite3.Connection:
    """
    Returns a new SQLite connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# -----------------------------
# Sessions (SC1-SC6)
# -----------------------------

def insert_session(
    machine_id: str,
    first_name: str,
    last_name: str,
    phone_number: str,
    time_in: str,
    expected_end: str,   # SC6
    status: str
) -> int:
    """
    Inserts a new session row and returns the generated SESSIONID.
    SC6: stores EXPECTED_END at creation time.
    """
    sql = """
        INSERT INTO sessions (
            MACHINEID, FIRSTNAME, LASTNAME, PHONENUMBER,
            TIMEIN, EXPECTED_END, STATUS
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    with get_connection() as conn:
        cur = conn.execute(
            sql,
            (machine_id, first_name, last_name, phone_number, time_in, expected_end, status)
        )
        conn.commit()
        return int(cur.lastrowid)


def get_session_by_id(session_id: int) -> sqlite3.Row | None:
    """
    Returns one session row or None if not found.
    Includes SC6: EXPECTED_END and DELAY_MIN.
    """
    sql = """
        SELECT
            SESSIONID, MACHINEID, FIRSTNAME, LASTNAME, PHONENUMBER,
            TIMEIN, EXPECTED_END, STATUS,
            FINISH_SMS_STATUS, FINISH_SMS_SENT_AT,
            VERIFICATION_CODE, TIMEOUT, DELAY_MIN
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
    Includes SC6: EXPECTED_END and DELAY_MIN.
    """
    sql = """
        SELECT
            SESSIONID, MACHINEID, FIRSTNAME, LASTNAME, PHONENUMBER,
            TIMEIN, EXPECTED_END, STATUS,
            FINISH_SMS_STATUS, FINISH_SMS_SENT_AT,
            VERIFICATION_CODE, TIMEOUT, DELAY_MIN
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


def mark_picked_up(session_id: int, time_out: str, delay_min: int) -> None:
    """
    Marks a session as picked up and records TIMEOUT (SC4)
    + DELAY_MIN (SC6).
    """
    sql = """
        UPDATE sessions
        SET STATUS = 'picked_up',
            TIMEOUT = ?,
            DELAY_MIN = ?
        WHERE SESSIONID = ?
    """
    with get_connection() as conn:
        conn.execute(sql, (time_out, delay_min, session_id))
        conn.commit()


# -----------------------------
# Machines (SC5-SC6)
# -----------------------------

def ensure_machine_exists(machine_id: str) -> None:
    """
    Creates a machine row if it doesn't exist yet.
    Default: vacant + normal.
    """
    sql = """
        INSERT OR IGNORE INTO machines (MACHINEID, OCCUPANCY_STATUS, CONDITION_STATUS)
        VALUES (?, 'vacant', 'normal')
    """
    with get_connection() as conn:
        conn.execute(sql, (machine_id,))
        conn.commit()


def get_machine_by_id(machine_id: str) -> sqlite3.Row | None:
    """
    Returns one machine row or None.
    Includes SC6: PROBLEM_REPORTED_AT and PROBLEM_RESOLVED_AT.
    """
    sql = """
        SELECT
            MACHINEID,
            OCCUPANCY_STATUS,
            CONDITION_STATUS,
            LAST_CONDITION_UPDATE,
            LAST_CONDITION_REASON,
            PROBLEM_REPORTED_AT,
            PROBLEM_RESOLVED_AT
        FROM machines
        WHERE MACHINEID = ?
    """
    with get_connection() as conn:
        return conn.execute(sql, (machine_id,)).fetchone()


def set_machine_occupied(machine_id: str) -> None:
    sql = "UPDATE machines SET OCCUPANCY_STATUS = 'occupied' WHERE MACHINEID = ?"
    with get_connection() as conn:
        conn.execute(sql, (machine_id,))
        conn.commit()


def set_machine_vacant(machine_id: str) -> None:
    sql = "UPDATE machines SET OCCUPANCY_STATUS = 'vacant' WHERE MACHINEID = ?"
    with get_connection() as conn:
        conn.execute(sql, (machine_id,))
        conn.commit()


def update_machine_condition(machine_id: str, new_condition: str, reason: str | None) -> None:
    """
    Updates machine condition (SC5) and stamps problem timestamps (SC6).
    - If set to broken: PROBLEM_REPORTED_AT is set and PROBLEM_RESOLVED_AT cleared
    - If set to normal: PROBLEM_RESOLVED_AT is set (reported time remains)
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if new_condition == "broken":
        sql = """
            UPDATE machines
            SET CONDITION_STATUS = ?,
                LAST_CONDITION_UPDATE = ?,
                LAST_CONDITION_REASON = ?,
                PROBLEM_REPORTED_AT = ?,
                PROBLEM_RESOLVED_AT = NULL
            WHERE MACHINEID = ?
        """
        params = (new_condition, now, reason, now, machine_id)
    else:
        sql = """
            UPDATE machines
            SET CONDITION_STATUS = ?,
                LAST_CONDITION_UPDATE = ?,
                LAST_CONDITION_REASON = ?,
                PROBLEM_RESOLVED_AT = ?
            WHERE MACHINEID = ?
        """
        params = (new_condition, now, reason, now, machine_id)

    with get_connection() as conn:
        conn.execute(sql, params)
        conn.commit()


# -----------------------------
# Summary stats (SC6)
# -----------------------------

def get_machine_summary_stats(machine_id: str) -> dict:
    with get_connection() as conn:
        total_sessions = conn.execute("""
            SELECT COUNT(*) AS c
            FROM sessions
            WHERE MACHINEID = ?
        """, (machine_id,)).fetchone()["c"]

        late_count = conn.execute("""
            SELECT COUNT(*) AS c
            FROM sessions
            WHERE MACHINEID = ?
              AND DELAY_MIN > 0
        """, (machine_id,)).fetchone()["c"]

        row = conn.execute("""
            SELECT AVG(DELAY_MIN) AS avgd, MAX(DELAY_MIN) AS maxd
            FROM sessions
            WHERE MACHINEID = ?
        """, (machine_id,)).fetchone()
        avg_delay = row["avgd"] or 0
        max_delay = row["maxd"] or 0

        # This machine: has it been reported broken?
        m = conn.execute("""
            SELECT PROBLEM_REPORTED_AT, PROBLEM_RESOLVED_AT
            FROM machines
            WHERE MACHINEID = ?
        """, (machine_id,)).fetchone()

        # repair time for THIS machine (if resolved)
        repair_min = 0
        if m and m["PROBLEM_REPORTED_AT"] and m["PROBLEM_RESOLVED_AT"]:
            rep = conn.execute("""
                SELECT ((julianday(PROBLEM_RESOLVED_AT) - julianday(PROBLEM_REPORTED_AT)) * 24 * 60) AS rep
                FROM machines
                WHERE MACHINEID = ?
            """, (machine_id,)).fetchone()["rep"]
            repair_min = rep or 0

        recent_sessions = conn.execute("""
            SELECT SESSIONID, TIMEIN, EXPECTED_END, TIMEOUT, DELAY_MIN, STATUS
            FROM sessions
            WHERE MACHINEID = ?
            ORDER BY SESSIONID DESC
            LIMIT 10
        """, (machine_id,)).fetchall()

    return {
        "total_sessions": int(total_sessions),
        "late_count": int(late_count),
        "avg_delay": round(float(avg_delay), 2),
        "max_delay": int(max_delay) if max_delay is not None else 0,
        "repair_min": round(float(repair_min), 2),
        "recent_sessions": recent_sessions,
    }
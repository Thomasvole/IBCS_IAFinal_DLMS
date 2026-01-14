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

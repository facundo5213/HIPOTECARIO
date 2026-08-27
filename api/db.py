import os
from contextlib import contextmanager

import pyodbc
from dotenv import load_dotenv

load_dotenv()


def connection_string() -> str:
    server = os.getenv("DB_SERVER", "").strip()
    database = os.getenv("DB_NAME", "").strip()
    if not server or not database:
        raise RuntimeError("Faltan DB_SERVER y/o DB_NAME en el archivo .env")
    port = os.getenv("DB_PORT", "").strip()
    server_value = f"{server},{port}" if port and "," not in server and "\\" not in server else server
    values = [
        f"DRIVER={{{os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')}}}",
        f"SERVER={server_value}", f"DATABASE={database}",
        f"Encrypt={os.getenv('DB_ENCRYPT', 'no')}",
        f"TrustServerCertificate={os.getenv('DB_TRUST_CERTIFICATE', 'yes')}",
    ]
    if os.getenv("DB_TRUSTED_CONNECTION", "yes").lower() in {"yes", "true", "1"}:
        values.append("Trusted_Connection=yes")
    else:
        username, password = os.getenv("DB_USER", ""), os.getenv("DB_PASSWORD", "")
        if not username or not password:
            raise RuntimeError("Faltan DB_USER y/o DB_PASSWORD")
        values.extend((f"UID={username}", f"PWD={password}"))
    return ";".join(values)


@contextmanager
def get_connection():
    connection = pyodbc.connect(connection_string(), timeout=10, autocommit=False)
    try:
        yield connection
    finally:
        connection.close()


def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_one(sql: str, params: tuple = ()) -> dict | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None

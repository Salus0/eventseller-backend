import os
import threading

from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor


DATABASE_URL = os.getenv("DATABASE_URL")

# Anzahl der gleichzeitigen Datenbankverbindungen.
# 1–2 Benutzer brauchen normalerweise keinen riesigen Pool.
MIN_CONNECTIONS = int(os.getenv("DB_POOL_MIN", "1"))
MAX_CONNECTIONS = int(os.getenv("DB_POOL_MAX", "10"))

_pool = None
_pool_lock = threading.Lock()


def get_pool():
    """
    Erstellt den PostgreSQL Connection Pool bei Bedarf.
    Der Pool wird anschließend für alle Requests wiederverwendet.
    """
    global _pool

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL ist nicht gesetzt!")

    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(
                    minconn=MIN_CONNECTIONS,
                    maxconn=MAX_CONNECTIONS,
                    dsn=DATABASE_URL,
                )

    return _pool


def get_connection():
    """
    Holt eine Verbindung aus dem Connection Pool.

    Die Verbindung wird nach Benutzung mit release_connection()
    wieder an den Pool zurückgegeben.
    """
    pool = get_pool()
    conn = pool.getconn()

    # Wir verwenden für alle Abfragen Dict-ähnliche Ergebnisse.
    # Dadurch bleiben die bisherigen Router kompatibel.
    return conn


def release_connection(conn):
    """
    Gibt eine Verbindung an den Pool zurück.

    Ein eventuell offener/fehlgeschlagener Transaction-Zustand
    wird vorher zurückgesetzt.
    """
    if conn is None:
        return

    try:
        if conn.closed:
            # Geschlossene Verbindung nicht wiederverwenden.
            get_pool().putconn(conn, close=True)
        else:
            # Eventuell offene/abgebrochene Transaktion zurücksetzen.
            conn.rollback()
            get_pool().putconn(conn)
    except Exception:
        try:
            get_pool().putconn(conn, close=True)
        except Exception:
            pass


def close_pool():
    """
    Schließt den kompletten Connection Pool.
    Kann beim Herunterfahren der Anwendung verwendet werden.
    """
    global _pool

    if _pool is not None:
        with _pool_lock:
            if _pool is not None:
                _pool.closeall()
                _pool = None
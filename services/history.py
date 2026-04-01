"""
services/history.py  —  Historial de auditorías en SQLite
"""

import sqlite3, json, os
from datetime import date, datetime

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "app.db")


def get_db_path() -> str:
    return os.path.abspath(_DB_PATH)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Crea las tablas si no existen."""
    os.makedirs(os.path.dirname(get_db_path()), exist_ok=True)
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audits (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha                TEXT NOT NULL,
                raw_text             TEXT DEFAULT '',
                cliente              TEXT DEFAULT '',
                telefono             TEXT DEFAULT '',
                tipo_entrega         TEXT NOT NULL,
                subtotal_reportado   REAL DEFAULT 0,
                envio_reportado      REAL DEFAULT 0,
                total_reportado      REAL NOT NULL,
                subtotal_cliente     REAL NOT NULL,
                subtotal_tienda      REAL NOT NULL,
                envio_real           REAL NOT NULL,
                total_real           REAL NOT NULL,
                pago_tienda          REAL NOT NULL,
                pago_repartidor      REAL NOT NULL,
                ganancia_plataforma  REAL NOT NULL,
                diferencia           REAL NOT NULL,
                estado               TEXT NOT NULL,
                items_json           TEXT NOT NULL,
                warnings_json        TEXT DEFAULT '[]'
            )
        """)
        conn.commit()


def save_audit(data: dict) -> int:
    """Guarda una auditoría. Devuelve el id del registro."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO audits (
                fecha, raw_text, cliente, telefono, tipo_entrega,
                subtotal_reportado, envio_reportado, total_reportado,
                subtotal_cliente, subtotal_tienda, envio_real, total_real,
                pago_tienda, pago_repartidor, ganancia_plataforma,
                diferencia, estado, items_json, warnings_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            now,
            data.get("raw_text", ""),
            data.get("cliente", ""),
            data.get("telefono", ""),
            data.get("tipo_entrega", ""),
            data.get("subtotal_reportado", 0),
            data.get("envio_reportado", 0),
            data.get("total_reportado", 0),
            data["subtotal_cliente"],
            data["subtotal_tienda"],
            data["envio_real"],
            data["total_real"],
            data["pago_tienda"],
            data["pago_repartidor"],
            data["ganancia_plataforma"],
            data["diferencia"],
            data["estado"],
            json.dumps(data.get("items_detalle", []), ensure_ascii=False),
            json.dumps(data.get("warnings", []), ensure_ascii=False),
        ))
        conn.commit()
        return cur.lastrowid


def get_audits(fecha_inicio: str = None, fecha_fin: str = None) -> list[dict]:
    query  = "SELECT * FROM audits WHERE 1=1"
    params = []
    if fecha_inicio:
        query += " AND fecha >= ?"; params.append(f"{fecha_inicio} 00:00:00")
    if fecha_fin:
        query += " AND fecha <= ?"; params.append(f"{fecha_fin} 23:59:59")
    query += " ORDER BY fecha DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_audit(record_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM audits WHERE id=?", (record_id,)).fetchone()
    if row:
        d = dict(row)
        d["items_json"]    = json.loads(d["items_json"])
        d["warnings_json"] = json.loads(d.get("warnings_json", "[]"))
        return d
    return None


def get_daily_summary(fecha: str = None) -> dict:
    if fecha is None:
        fecha = date.today().strftime("%Y-%m-%d")
    fi, ff = f"{fecha} 00:00:00", f"{fecha} 23:59:59"
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                                              AS total_pedidos,
                COALESCE(SUM(pago_tienda), 0)                        AS total_tienda,
                COALESCE(SUM(pago_repartidor), 0)                    AS total_repartidores,
                COALESCE(SUM(ganancia_plataforma), 0)                AS total_plataforma,
                SUM(CASE WHEN estado='OK'                      THEN 1 ELSE 0 END) AS pedidos_ok,
                SUM(CASE WHEN estado='Revisar'                 THEN 1 ELSE 0 END) AS pedidos_revisar,
                SUM(CASE WHEN estado='Manipulado o incompleto' THEN 1 ELSE 0 END) AS pedidos_manipulados
            FROM audits WHERE fecha BETWEEN ? AND ?
        """, (fi, ff)).fetchone()
    r = dict(row) if row else {}
    return {
        "fecha":               fecha,
        "total_pedidos":       r.get("total_pedidos") or 0,
        "total_tienda":        r.get("total_tienda") or 0.0,
        "total_repartidores":  r.get("total_repartidores") or 0.0,
        "total_plataforma":    r.get("total_plataforma") or 0.0,
        "pedidos_ok":          r.get("pedidos_ok") or 0,
        "pedidos_revisar":     r.get("pedidos_revisar") or 0,
        "pedidos_manipulados": r.get("pedidos_manipulados") or 0,
    }

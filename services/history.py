"""
services/history.py
-------------------
Gestión del historial de pedidos verificados en SQLite.
Usa sqlite3 estándar de Python, sin ORM.
"""

import sqlite3
import json
import os
from datetime import date, datetime

# Ruta a la base de datos
_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "database", "historial.db"
)


def get_db_path() -> str:
    return os.path.abspath(_DB_PATH)


def get_connection() -> sqlite3.Connection:
    """Devuelve una conexión configurada con row_factory para dicts."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # mejor rendimiento concurrente
    return conn


def init_db():
    """
    Crea la tabla de historial si no existe.
    Llamar una vez al iniciar la app.
    """
    os.makedirs(os.path.dirname(get_db_path()), exist_ok=True)
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historial (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha               TEXT NOT NULL,
                cliente             TEXT NOT NULL,
                telefono            TEXT DEFAULT '',
                tipo_entrega        TEXT NOT NULL,
                subtotal_reportado  REAL DEFAULT 0,
                envio_reportado     REAL DEFAULT 0,
                total_reportado     REAL NOT NULL,
                subtotal_cliente    REAL NOT NULL,
                subtotal_tienda     REAL NOT NULL,
                envio_real          REAL NOT NULL,
                total_real          REAL NOT NULL,
                pago_tienda         REAL NOT NULL,
                pago_repartidor     REAL NOT NULL,
                ganancia_plataforma REAL NOT NULL,
                diferencia          REAL NOT NULL,
                estado              TEXT NOT NULL,
                productos_json      TEXT NOT NULL
            )
        """)
        conn.commit()


def guardar_verificacion(data: dict) -> int:
    """
    Guarda una verificación en el historial.
    Devuelve el id del registro insertado.

    data espera las claves del resultado de verificar_pedido() más:
        cliente, telefono, tipo_entrega, subtotal_reportado,
        envio_reportado, total_reportado, items_detalle
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    productos_json = json.dumps(data.get("items_detalle", []), ensure_ascii=False)

    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO historial (
                fecha, cliente, telefono, tipo_entrega,
                subtotal_reportado, envio_reportado, total_reportado,
                subtotal_cliente, subtotal_tienda,
                envio_real, total_real,
                pago_tienda, pago_repartidor, ganancia_plataforma,
                diferencia, estado, productos_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            now,
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
            productos_json,
        ))
        conn.commit()
        return cursor.lastrowid


def obtener_historial(fecha_inicio: str = None, fecha_fin: str = None) -> list[dict]:
    """
    Devuelve el historial de verificaciones, opcionalmente filtrado por rango de fechas.
    Las fechas deben estar en formato 'YYYY-MM-DD'.
    """
    query = "SELECT * FROM historial WHERE 1=1"
    params = []

    if fecha_inicio:
        query += " AND fecha >= ?"
        params.append(f"{fecha_inicio} 00:00:00")
    if fecha_fin:
        query += " AND fecha <= ?"
        params.append(f"{fecha_fin} 23:59:59")

    query += " ORDER BY fecha DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def obtener_verificacion(record_id: int) -> dict | None:
    """Devuelve un registro del historial por su id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM historial WHERE id = ?", (record_id,)
        ).fetchone()
    if row:
        d = dict(row)
        d["productos_json"] = json.loads(d["productos_json"])
        return d
    return None


def resumen_del_dia(fecha: str = None) -> dict:
    """
    Devuelve los acumulados para una fecha dada (default: hoy).
    fecha: 'YYYY-MM-DD'
    """
    if fecha is None:
        fecha = date.today().strftime("%Y-%m-%d")

    fecha_inicio = f"{fecha} 00:00:00"
    fecha_fin    = f"{fecha} 23:59:59"

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                COUNT(*)                     AS total_pedidos,
                SUM(pago_tienda)             AS total_tienda,
                SUM(pago_repartidor)         AS total_repartidores,
                SUM(ganancia_plataforma)     AS total_plataforma,
                SUM(CASE WHEN estado='OK'                    THEN 1 ELSE 0 END) AS pedidos_ok,
                SUM(CASE WHEN estado='Revisar'               THEN 1 ELSE 0 END) AS pedidos_revisar,
                SUM(CASE WHEN estado='Manipulado o incompleto' THEN 1 ELSE 0 END) AS pedidos_manipulados
            FROM historial
            WHERE fecha BETWEEN ? AND ?
        """, (fecha_inicio, fecha_fin)).fetchone()

    row = dict(rows) if rows else {}

    # Valores seguros si no hay datos
    return {
        "fecha":               fecha,
        "total_pedidos":       row.get("total_pedidos") or 0,
        "total_tienda":        row.get("total_tienda") or 0.0,
        "total_repartidores":  row.get("total_repartidores") or 0.0,
        "total_plataforma":    row.get("total_plataforma") or 0.0,
        "pedidos_ok":          row.get("pedidos_ok") or 0,
        "pedidos_revisar":     row.get("pedidos_revisar") or 0,
        "pedidos_manipulados": row.get("pedidos_manipulados") or 0,
    }

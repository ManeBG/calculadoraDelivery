"""
app.py
------
Calculadora de Deliveries – Miscelánea García
Flask app privada/local para verificar y auditar pedidos.

Rutas:
    GET  /              → formulario de verificación
    POST /verificar     → procesa y muestra resultado
    GET  /historial     → tabla de verificaciones guardadas
    GET  /resumen       → resumen del día actual
    GET  /ver/<id>      → detalle de una verificación del historial
    POST /api/catalog   → (AJAX) devuelve catálogo como JSON
"""

import json
from datetime import date

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, jsonify, session
)

from services.catalog    import get_products_for_select, get_store_meta, get_delivery_options
from services.calculator import verificar_pedido
from services.history    import init_db, guardar_verificacion, obtener_historial, obtener_verificacion, resumen_del_dia
from services.parser     import parse_order_form

# ─── App init ────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = "garcia-delivery-secret-2024"   # para flash messages

# Inicializar base de datos al arrancar
with app.app_context():
    init_db()


# ─── Context processor: datos globales en todos los templates ────────────────

@app.context_processor
def inject_globals():
    meta = get_store_meta()
    return {
        "store_name": meta.get("storeName", "Miscelánea García"),
        "currency":   meta.get("currency", "MXN"),
    }


# ─── Filtro Jinja para formatear moneda ──────────────────────────────────────

@app.template_filter("money")
def money_filter(value):
    """Formatea un número como moneda MXN con 2 decimales."""
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"


# ─── Rutas ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Pantalla de bienvenida / dashboard rápido."""
    hoy = date.today().strftime("%Y-%m-%d")
    resumen = resumen_del_dia(hoy)
    return render_template("index.html", resumen=resumen, hoy=hoy)


@app.route("/verificar", methods=["GET", "POST"])
def verificar():
    """
    GET  → muestra el formulario de verificación con el catálogo.
    POST → procesa el pedido y redirige a /resultado con datos en sesión.
    """
    products       = get_products_for_select()
    delivery_options = get_delivery_options()

    if request.method == "GET":
        return render_template(
            "verificador.html",
            products=products,
            delivery_options=delivery_options,
            products_json=json.dumps(products, ensure_ascii=False),
        )

    # ── POST: validar y calcular ──────────────────────────────────────────────
    form_data, errors = parse_order_form(request.form)

    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template(
            "verificador.html",
            products=products,
            delivery_options=delivery_options,
            products_json=json.dumps(products, ensure_ascii=False),
            form_values=request.form,
        )

    # Calcular
    resultado = verificar_pedido(
        items              = form_data["items"],
        tipo_entrega       = form_data["tipo_entrega"],
        total_reportado    = form_data["total_reportado"],
        envio_reportado    = form_data["envio_reportado"],
        subtotal_reportado = form_data["subtotal_reportado"],
    )

    # Enriquecer resultado con datos del formulario
    resultado.update({
        "cliente":             form_data["cliente"],
        "telefono":            form_data["telefono"],
        "tipo_entrega":        form_data["tipo_entrega"],
        "subtotal_reportado":  form_data["subtotal_reportado"],
        "envio_reportado":     form_data["envio_reportado"],
        "total_reportado":     form_data["total_reportado"],
    })

    # Guardar en historial
    record_id = guardar_verificacion(resultado)

    # Guardar en sesión para mostrar en /resultado
    session["last_result"] = resultado
    session["last_record_id"] = record_id

    return redirect(url_for("resultado"))


@app.route("/resultado")
def resultado():
    """Muestra el resultado de la última verificación."""
    result = session.get("last_result")
    record_id = session.get("last_record_id")

    if not result:
        flash("No hay resultado disponible. Verifica un pedido primero.", "warning")
        return redirect(url_for("verificar"))

    delivery_options = get_delivery_options()
    # Etiqueta del tipo de entrega
    tipo_label = delivery_options.get(result.get("tipo_entrega", ""), {}).get("label", result.get("tipo_entrega", ""))

    return render_template(
        "resultado.html",
        r=result,
        record_id=record_id,
        tipo_label=tipo_label,
    )


@app.route("/historial")
def historial():
    """Muestra el historial de verificaciones con filtro por fecha."""
    fecha_inicio = request.args.get("fecha_inicio", "")
    fecha_fin    = request.args.get("fecha_fin", "")

    registros = obtener_historial(
        fecha_inicio=fecha_inicio or None,
        fecha_fin=fecha_fin or None,
    )

    return render_template(
        "historial.html",
        registros=registros,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )


@app.route("/ver/<int:record_id>")
def ver_verificacion(record_id: int):
    """Detalle de un registro del historial."""
    registro = obtener_verificacion(record_id)
    if not registro:
        flash(f"Registro #{record_id} no encontrado.", "danger")
        return redirect(url_for("historial"))

    delivery_options = get_delivery_options()
    tipo_label = delivery_options.get(registro.get("tipo_entrega", ""), {}).get("label", registro.get("tipo_entrega", ""))

    return render_template(
        "resultado.html",
        r=registro,
        record_id=record_id,
        tipo_label=tipo_label,
        readonly=True,     # indica que es solo lectura (del historial)
    )


@app.route("/resumen")
def resumen():
    """Resumen del día (o de una fecha específica)."""
    fecha = request.args.get("fecha", date.today().strftime("%Y-%m-%d"))
    datos = resumen_del_dia(fecha)
    return render_template("resumen.html", datos=datos, fecha=fecha)


# ─── API AJAX ────────────────────────────────────────────────────────────────

@app.route("/api/catalog")
def api_catalog():
    """Devuelve el catálogo completo como JSON para uso en JS."""
    return jsonify(get_products_for_select())


@app.route("/api/delivery-options")
def api_delivery_options():
    """Devuelve las opciones de entrega como JSON."""
    return jsonify(get_delivery_options())


# ─── Manejo de errores ───────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Página no encontrada"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Error interno del servidor"), 500


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Calculadora de Deliveries – Miscelánea García")
    print("  http://127.0.0.1:5000")
    print("=" * 55)
    app.run(debug=True, host="0.0.0.0", port=5000)

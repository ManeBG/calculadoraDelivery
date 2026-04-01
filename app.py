"""
app.py — Calculadora / Auditor de Deliveries — Miscelánea García
================================================================
Flujo principal:
  GET  /verificar          → textarea para pegar texto del pedido
  POST /analizar           → parsea el texto y guarda en sesión
  GET  /revisar            → muestra lo detectado + formulario de corrección
  POST /confirmar          → calcula, guarda en DB, redirige a /resultado
  GET  /resultado          → muestra el resultado de la última auditoría
  GET  /ver/<id>           → detalle de un registro del historial
  GET  /historial          → tabla de auditorías guardadas
  GET  /resumen            → resumen acumulado del día
  GET  /                   → dashboard (redirige a /verificar si está vacío)
"""

import json
from datetime import date

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, jsonify, session
)

from services.catalog    import (
    get_products_for_select, get_store_meta,
    get_delivery_options
)
from services.parser     import build_detected_order
from services.calculator import run_full_calculation, resolve_item_prices
from services.history    import init_db, save_audit, get_audits, get_audit, get_daily_summary

# ─── App init ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "garcia-audit-local-2024"

with app.app_context():
    init_db()


# ─── Context processor ────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    meta = get_store_meta()
    return {
        "store_name": meta.get("storeName", "Miscelánea García"),
        "currency":   meta.get("currency", "MXN"),
    }


# ─── Filtro moneda ────────────────────────────────────────────────────────────
@app.template_filter("money")
def money_filter(value):
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"


# ─── Dashboard ────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    hoy    = date.today().strftime("%Y-%m-%d")
    resumen = get_daily_summary(hoy)
    return render_template("index.html", resumen=resumen, hoy=hoy)


# ─── PASO 1: Textarea para pegar el pedido ────────────────────────────────────
@app.route("/verificar", methods=["GET"])
def verificar():
    """Página principal: textarea para pegar el texto del pedido."""
    # Si hay un análisis en sesión, preguntar si seguir con él
    has_analysis = bool(session.get("analysis"))
    prev_text    = session.get("analysis", {}).get("raw_text", "") if has_analysis else ""
    return render_template("verificar.html",
                           has_analysis=has_analysis,
                           prev_text=prev_text)


# ─── PASO 2: Analizar el texto pegado ─────────────────────────────────────────
@app.route("/analizar", methods=["POST"])
def analizar():
    """Parsea el texto libre del pedido y guarda el análisis en sesión."""
    raw_text = request.form.get("raw_text", "").strip()

    if not raw_text:
        flash("Pega el texto del pedido antes de analizar.", "warning")
        return redirect(url_for("verificar"))

    # Analizar con el parser inteligente
    analysis = build_detected_order(raw_text)

    # Guardar en sesión (como dict serializable)
    session["analysis"] = analysis.to_dict()
    session["last_result"] = None  # resetear resultado anterior

    return redirect(url_for("revisar"))


# ─── PASO 3: Revisar y corregir el análisis ───────────────────────────────────
@app.route("/revisar", methods=["GET"])
def revisar():
    """
    Muestra el resultado del análisis con opción de corrección.
    El usuario puede:
    - cambiar datos detectados (cliente, teléfono, tipo entrega, montos)
    - cambiar producto/variante de un ítem
    - cambiar cantidad
    - eliminar ítems incorrectos
    - agregar nuevos ítems manualmente
    """
    analysis = session.get("analysis")
    if not analysis:
        flash("Primero pega y analiza un pedido.", "warning")
        return redirect(url_for("verificar"))

    products         = get_products_for_select()
    delivery_options = get_delivery_options()

    return render_template(
        "revisar.html",
        analysis=analysis,
        products=products,
        delivery_options=delivery_options,
        products_json=json.dumps(products, ensure_ascii=False),
    )


# ─── PASO 4: Confirmar y calcular ────────────────────────────────────────────
@app.route("/confirmar", methods=["POST"])
def confirmar():
    """
    Recibe el formulario de revisión (corregido por el usuario),
    re-calcula todo, guarda en historial y muestra el resultado.
    """
    analysis = session.get("analysis", {})
    raw_text = analysis.get("raw_text", "")

    # Datos del encabezado
    cliente     = request.form.get("cliente", "").strip()
    telefono    = request.form.get("telefono", "").strip()
    tipo_entrega = request.form.get("tipo_entrega", "").strip()

    if not tipo_entrega:
        flash("Selecciona el tipo de entrega.", "danger")
        return redirect(url_for("revisar"))

    # Montos reportados
    def _float(key, default=0.0) -> float:
        try:
            return float(request.form.get(key, default) or default)
        except (ValueError, TypeError):
            return default

    total_reportado    = _float("total_reportado")
    subtotal_reportado = _float("subtotal_reportado")
    envio_reportado    = _float("envio_reportado")

    # Productos (listas paralelas del formulario)
    product_ids  = request.form.getlist("product_id[]")
    variant_ids  = request.form.getlist("variant_id[]")
    quantities   = request.form.getlist("quantity[]")
    # Nombre y variante label por si el productor no está en catálogo
    prod_names   = request.form.getlist("product_name[]")
    var_labels   = request.form.getlist("variant_label[]")

    if not product_ids:
        flash("Agrega al menos un producto al pedido.", "danger")
        return redirect(url_for("revisar"))

    # Construir items con precios resueltos del catálogo
    items_detalle = []
    for i, pid in enumerate(product_ids):
        pid = pid.strip()
        if not pid:
            continue
        try:
            qty = int(quantities[i]) if i < len(quantities) else 1
            qty = max(1, qty)
        except (ValueError, TypeError):
            qty = 1

        vid = (variant_ids[i] if i < len(variant_ids) else "").strip()

        raw_item = {
            "product_id":    pid,
            "variant_id":    vid,
            "quantity":      qty,
            "product_name":  prod_names[i] if i < len(prod_names) else "",
            "variant_label": var_labels[i] if i < len(var_labels) else "",
        }
        resolved = resolve_item_prices(raw_item)
        items_detalle.append(resolved)

    # Calcular
    result = run_full_calculation(
        items             = items_detalle,
        tipo_entrega      = tipo_entrega,
        total_reportado   = total_reportado,
        envio_reportado   = envio_reportado,
        subtotal_reportado= subtotal_reportado,
    )

    # Guardar en historial
    audit_data = {
        **result,
        "raw_text":           raw_text,
        "cliente":            cliente,
        "telefono":           telefono,
        "tipo_entrega":       tipo_entrega,
        "subtotal_reportado": subtotal_reportado,
        "envio_reportado":    envio_reportado,
        "total_reportado":    total_reportado,
        "items_detalle":      items_detalle,
        "warnings":           analysis.get("warnings", []),
    }

    record_id = save_audit(audit_data)

    # Guardar resultado en sesión para mostrar
    session["last_result"]    = audit_data
    session["last_record_id"] = record_id
    # Limpiar análisis de sesión
    session.pop("analysis", None)

    return redirect(url_for("resultado"))


# ─── Resultado ────────────────────────────────────────────────────────────────
@app.route("/resultado")
def resultado():
    result    = session.get("last_result")
    record_id = session.get("last_record_id")

    if not result:
        flash("No hay resultado disponible. Analiza un pedido primero.", "warning")
        return redirect(url_for("verificar"))

    delivery_options = get_delivery_options()
    tipo_label = delivery_options.get(
        result.get("tipo_entrega", ""), {}
    ).get("label", result.get("tipo_entrega", ""))

    return render_template("resultado.html", r=result,
                           record_id=record_id, tipo_label=tipo_label)


# ─── Historial ────────────────────────────────────────────────────────────────
@app.route("/historial")
def historial():
    fecha_inicio = request.args.get("fecha_inicio", "")
    fecha_fin    = request.args.get("fecha_fin", "")
    registros    = get_audits(
        fecha_inicio=fecha_inicio or None,
        fecha_fin=fecha_fin or None,
    )
    return render_template("historial.html", registros=registros,
                           fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)


@app.route("/ver/<int:record_id>")
def ver_auditoria(record_id: int):
    registro = get_audit(record_id)
    if not registro:
        flash(f"Registro #{record_id} no encontrado.", "danger")
        return redirect(url_for("historial"))

    delivery_options = get_delivery_options()
    tipo_label = delivery_options.get(
        registro.get("tipo_entrega", ""), {}
    ).get("label", registro.get("tipo_entrega", ""))

    # Normalizar items_json para el template
    registro["items_detalle"] = registro.get("items_json", [])

    return render_template("resultado.html", r=registro,
                           record_id=record_id, tipo_label=tipo_label, readonly=True)


# ─── Resumen del día ──────────────────────────────────────────────────────────
@app.route("/resumen")
def resumen():
    fecha = request.args.get("fecha", date.today().strftime("%Y-%m-%d"))
    datos = get_daily_summary(fecha)
    return render_template("resumen.html", datos=datos, fecha=fecha)


# ─── API AJAX ─────────────────────────────────────────────────────────────────
@app.route("/api/catalog")
def api_catalog():
    return jsonify(get_products_for_select())


@app.route("/api/delivery-options")
def api_delivery_options():
    return jsonify(get_delivery_options())


# ─── Errores ──────────────────────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="Página no encontrada"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, message="Error interno del servidor"), 500


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Auditor de Deliveries – Miscelánea García")
    print("  http://127.0.0.1:5000")
    print("=" * 55)
    app.run(debug=True, host="0.0.0.0", port=5000)

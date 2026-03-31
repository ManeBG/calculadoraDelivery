"""
services/parser.py
------------------
Utilidades para parsear y validar los datos del formulario
antes de pasarlos al calculador.
"""

from flask import Request


def parse_order_form(form) -> tuple[dict, list[str]]:
    """
    Extrae y valida los datos del formulario de verificación.
    Devuelve (data_dict, errores_list).
    Si errores_list está vacío, el formulario es válido.

    Campos esperados:
        cliente, telefono, tipo_entrega
        subtotal_reportado, envio_reportado, total_reportado
        product_id[]  (lista)
        variant_id[]  (lista, puede ser vacío)
        quantity[]    (lista)
    """
    errors = []

    cliente  = form.get("cliente", "").strip()
    telefono = form.get("telefono", "").strip()
    tipo_entrega = form.get("tipo_entrega", "").strip()

    if not cliente:
        errors.append("El nombre del cliente es obligatorio.")
    if not tipo_entrega:
        errors.append("Debes seleccionar el tipo de entrega.")

    # Montos reportados (pueden ser 0)
    try:
        subtotal_reportado = float(form.get("subtotal_reportado", 0) or 0)
    except (ValueError, TypeError):
        subtotal_reportado = 0.0
        errors.append("Subtotal reportado inválido.")

    try:
        envio_reportado = float(form.get("envio_reportado", 0) or 0)
    except (ValueError, TypeError):
        envio_reportado = 0.0
        errors.append("Envío reportado inválido.")

    try:
        total_reportado = float(form.get("total_reportado", 0) or 0)
    except (ValueError, TypeError):
        total_reportado = 0.0
        errors.append("Total reportado inválido.")

    # Productos (listas paralelas)
    product_ids = form.getlist("product_id[]")
    variant_ids = form.getlist("variant_id[]")
    quantities  = form.getlist("quantity[]")

    # Aseguramos que variant_ids tenga la misma longitud
    while len(variant_ids) < len(product_ids):
        variant_ids.append("")

    items = []
    for i, pid in enumerate(product_ids):
        pid = pid.strip()
        if not pid:
            continue
        try:
            qty = int(quantities[i]) if i < len(quantities) else 1
            qty = max(1, qty)
        except (ValueError, TypeError):
            qty = 1

        items.append({
            "product_id": pid,
            "variant_id": (variant_ids[i] or "").strip(),
            "quantity":   qty,
        })

    if not items:
        errors.append("Agrega al menos un producto al pedido.")

    data = {
        "cliente":             cliente,
        "telefono":            telefono,
        "tipo_entrega":        tipo_entrega,
        "subtotal_reportado":  subtotal_reportado,
        "envio_reportado":     envio_reportado,
        "total_reportado":     total_reportado,
        "items":               items,
    }

    return data, errors

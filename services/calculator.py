"""
services/calculator.py
----------------------
Motor de cálculo de pedidos para Miscelánea García.
Reglas:
  precio_web    → precio al cliente (delivery)
  precio_tienda → costo real de la tienda
  Ganancia plataforma = subtotal_web - subtotal_tienda
  Pago repartidor = costo de envío del JSON meta
"""

from services.catalog import find_product_by_id, find_variant, get_delivery_options

TOLERANCE_OK      = 0.01
TOLERANCE_REVISAR = 5.00


def calculate_customer_subtotal(items: list[dict]) -> float:
    """Suma precio_web × cantidad para items pre-resueltos con precio_web."""
    return round(sum(
        float(i.get("precio_web", 0)) * int(i.get("quantity", 1))
        for i in items
    ), 2)


def calculate_store_subtotal(items: list[dict]) -> float:
    """Suma precio_tienda × cantidad."""
    return round(sum(
        float(i.get("precio_tienda", 0)) * int(i.get("quantity", 1))
        for i in items
    ), 2)


def calculate_delivery_fee(tipo_entrega: str) -> float:
    """Costo de envío real según tipo de entrega."""
    opts = get_delivery_options()
    return float(opts.get(tipo_entrega, {}).get("cost", 0))


def calculate_driver_payment(delivery_fee: float) -> float:
    return round(delivery_fee, 2)


def calculate_platform_profit(subtotal_cliente: float, subtotal_tienda: float) -> float:
    """Margen entre precio_web y precio_tienda."""
    return round(subtotal_cliente - subtotal_tienda, 2)


def classify_order_status(diferencia: float) -> str:
    abs_diff = abs(diferencia)
    if abs_diff <= TOLERANCE_OK:
        return "OK"
    elif abs_diff <= TOLERANCE_REVISAR:
        return "Revisar"
    else:
        return "Manipulado o incompleto"


def run_full_calculation(
    items: list[dict],
    tipo_entrega: str,
    total_reportado: float,
    envio_reportado: float = 0.0,
    subtotal_reportado: float = 0.0,
) -> dict:
    """
    Ejecuta el cálculo completo. Los items deben tener:
    {"precio_web": float, "precio_tienda": float, "quantity": int, ...}

    Devuelve el diccionario completo de resultados.
    """
    subtotal_cliente    = calculate_customer_subtotal(items)
    subtotal_tienda     = calculate_store_subtotal(items)
    envio_real          = calculate_delivery_fee(tipo_entrega)
    total_real          = round(subtotal_cliente + envio_real, 2)
    pago_tienda         = subtotal_tienda
    pago_repartidor     = calculate_driver_payment(envio_real)
    ganancia_plataforma = calculate_platform_profit(subtotal_cliente, subtotal_tienda)
    diferencia          = round(total_reportado - total_real, 2)
    diferencia_envio    = round(envio_reportado - envio_real, 2)
    diferencia_subtotal = round(subtotal_reportado - subtotal_cliente, 2)
    estado              = classify_order_status(diferencia)

    return {
        "subtotal_cliente":    subtotal_cliente,
        "subtotal_tienda":     subtotal_tienda,
        "envio_real":          envio_real,
        "total_real":          total_real,
        "pago_tienda":         pago_tienda,
        "pago_repartidor":     pago_repartidor,
        "ganancia_plataforma": ganancia_plataforma,
        "diferencia":          diferencia,
        "diferencia_envio":    diferencia_envio,
        "diferencia_subtotal": diferencia_subtotal,
        "estado":              estado,
    }


# ─── Compatibilidad con el catálogo (resolución de precios) ───────────────────

def resolve_item_prices(item: dict) -> dict:
    """
    Dado un item con product_id y variant_id, resuelve los precios
    desde el catálogo y devuelve el item enriquecido.
    """
    from services.catalog import find_product_by_id as fpid, find_variant as fv

    pid = item.get("product_id", "")
    vid = item.get("variant_id") or ""
    qty = int(item.get("quantity", 1))
    product = fpid(pid)

    if not product:
        return {**item, "precio_web": 0, "precio_tienda": 0,
                "product_name": "Desconocido", "variant_label": "",
                "subtotal_web": 0, "subtotal_tienda": 0}

    if product["type"] == "simple":
        pw = product.get("precio_web", 0)
        pt = product.get("precio_tienda", 0)
        vl = ""
    else:
        variant = fv(pid, vid)
        if not variant and product.get("variants"):
            variant = product["variants"][0]
        if variant:
            pw = variant.get("precio_web", 0)
            pt = variant.get("precio_tienda", 0)
            vl = variant.get("label", "")
        else:
            pw, pt, vl = 0, 0, ""

    return {
        **item,
        "product_name":    item.get("product_name") or product["name"],
        "variant_label":   item.get("variant_label") or vl,
        "precio_web":      pw,
        "precio_tienda":   pt,
        "subtotal_web":    round(pw * qty, 2),
        "subtotal_tienda": round(pt * qty, 2),
    }

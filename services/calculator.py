"""
services/calculator.py
----------------------
Motor de cálculo de pedidos para Miscelánea García.

Reglas de negocio:
- precio_web   → lo que cobra el cliente (precio delivery)
- precio_tienda → lo que cuesta a la tienda (su precio)
- Ganancia plataforma = subtotal_cliente - subtotal_tienda
- Pago repartidor    = costo de envío definido en meta
- Pago tienda        = subtotal_tienda   (lo que entra a la tienda)
- Total real cliente = subtotal_cliente + envío real
- Diferencia        = total_reportado - total_real_cliente
- Estado: OK / Revisar / Manipulado
"""

from services.catalog import find_product_by_id, find_variant, get_delivery_options

# Umbral de diferencia para clasificar estado (en pesos MXN)
TOLERANCE_OK      = 0.01   # diferencia ≤ 0.01  → OK
TOLERANCE_REVISAR = 5.00   # diferencia ≤ 5.00  → Revisar
# diferencia > 5.00           → Manipulado o incompleto


# ─── Subtotales ───────────────────────────────────────────────────────────────

def calcular_subtotal_cliente(items: list[dict]) -> float:
    """
    Suma precio_web × cantidad para cada ítem del pedido.
    items: [{"product_id": str, "variant_id": str|None, "quantity": int}, ...]
    """
    total = 0.0
    for item in items:
        precio = _get_precio_web(item)
        total += precio * int(item.get("quantity", 1))
    return round(total, 2)


def calcular_subtotal_tienda(items: list[dict]) -> float:
    """
    Suma precio_tienda × cantidad para cada ítem.
    """
    total = 0.0
    for item in items:
        precio = _get_precio_tienda(item)
        total += precio * int(item.get("quantity", 1))
    return round(total, 2)


# ─── Envío ────────────────────────────────────────────────────────────────────

def calcular_envio_real(tipo_entrega: str, subtotal_cliente: float) -> float:
    """
    Devuelve el costo de envío real según tipo de entrega.
    tipo_entrega: 'pickup' | 'local' | 'outside'
    """
    options = get_delivery_options()
    option  = options.get(tipo_entrega, {})
    return float(option.get("cost", 0))


# ─── Desglose de pagos ────────────────────────────────────────────────────────

def calcular_pago_tienda(subtotal_tienda: float) -> float:
    """Lo que entra directamente a la tienda (costo real de la mercancía)."""
    return round(subtotal_tienda, 2)


def calcular_pago_repartidor(envio_real: float) -> float:
    """El repartidor se lleva el costo de envío."""
    return round(envio_real, 2)


def calcular_ganancia_plataforma(subtotal_cliente: float, subtotal_tienda: float) -> float:
    """
    La ganancia de la plataforma es el margen entre precio_web y precio_tienda.
    """
    return round(subtotal_cliente - subtotal_tienda, 2)


def calcular_total_real(subtotal_cliente: float, envio_real: float) -> float:
    """Total real que debe pagar el cliente."""
    return round(subtotal_cliente + envio_real, 2)


# ─── Diferencia y estado ──────────────────────────────────────────────────────

def calcular_diferencia(total_reportado: float, total_real: float) -> float:
    """
    Diferencia entre lo reportado y el real.
    Positivo = reportaron más de lo que es (posible manipulación).
    Negativo = reportaron menos (pedido incompleto o descuento).
    """
    return round(total_reportado - total_real, 2)


def clasificar_estado(diferencia: float) -> str:
    """
    Clasifica el estado del pedido según la diferencia.
    Devuelve: 'OK', 'Revisar', 'Manipulado o incompleto'
    """
    abs_diff = abs(diferencia)
    if abs_diff <= TOLERANCE_OK:
        return "OK"
    elif abs_diff <= TOLERANCE_REVISAR:
        return "Revisar"
    else:
        return "Manipulado o incompleto"


# ─── Función principal ────────────────────────────────────────────────────────

def verificar_pedido(
    items: list[dict],
    tipo_entrega: str,
    total_reportado: float,
    envio_reportado: float,
    subtotal_reportado: float,
) -> dict:
    """
    Ejecuta el cálculo completo y devuelve un diccionario con todos los valores.

    Parámetros:
        items               → lista de productos del pedido
        tipo_entrega        → 'pickup' | 'local' | 'outside'
        total_reportado     → total que reportó el cliente / la plataforma
        envio_reportado     → envío que reportó el cliente
        subtotal_reportado  → subtotal que reportó el cliente

    Retorna:
        {
            "subtotal_cliente":      float,
            "subtotal_tienda":       float,
            "envio_real":            float,
            "total_real":            float,
            "pago_tienda":           float,
            "pago_repartidor":       float,
            "ganancia_plataforma":   float,
            "diferencia":            float,
            "diferencia_envio":      float,
            "diferencia_subtotal":   float,
            "estado":                str,
            "items_detalle":         list[dict],  # con precios resueltos
        }
    """
    # Resolver precios para cada ítem
    items_detalle = _resolver_items(items)

    # Cálculos
    subtotal_cliente    = calcular_subtotal_cliente(items)
    subtotal_tienda     = calcular_subtotal_tienda(items)
    envio_real          = calcular_envio_real(tipo_entrega, subtotal_cliente)
    total_real          = calcular_total_real(subtotal_cliente, envio_real)
    pago_tienda         = calcular_pago_tienda(subtotal_tienda)
    pago_repartidor     = calcular_pago_repartidor(envio_real)
    ganancia_plataforma = calcular_ganancia_plataforma(subtotal_cliente, subtotal_tienda)
    diferencia          = calcular_diferencia(total_reportado, total_real)
    diferencia_envio    = round(envio_reportado - envio_real, 2)
    diferencia_subtotal = round(subtotal_reportado - subtotal_cliente, 2)
    estado              = clasificar_estado(diferencia)

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
        "items_detalle":       items_detalle,
    }


# ─── Helpers privados ─────────────────────────────────────────────────────────

def _get_precio_web(item: dict) -> float:
    pid = item.get("product_id", "")
    vid = item.get("variant_id") or ""
    product = find_product_by_id(pid)
    if not product:
        return 0.0
    if product["type"] == "simple":
        return product.get("precio_web", 0.0)
    variant = find_variant(pid, vid)
    return variant.get("precio_web", 0.0) if variant else 0.0


def _get_precio_tienda(item: dict) -> float:
    pid = item.get("product_id", "")
    vid = item.get("variant_id") or ""
    product = find_product_by_id(pid)
    if not product:
        return 0.0
    if product["type"] == "simple":
        return product.get("precio_tienda", 0.0)
    variant = find_variant(pid, vid)
    return variant.get("precio_tienda", 0.0) if variant else 0.0


def _resolver_items(items: list[dict]) -> list[dict]:
    """Enriquece cada ítem con nombre, variante y precios para el detalle."""
    result = []
    for item in items:
        pid = item.get("product_id", "")
        vid = item.get("variant_id") or ""
        qty = int(item.get("quantity", 1))
        product = find_product_by_id(pid)

        if not product:
            result.append({
                "product_id":    pid,
                "variant_id":    vid,
                "name":          "Producto no encontrado",
                "variant_label": "",
                "quantity":      qty,
                "precio_web":    0.0,
                "precio_tienda": 0.0,
                "subtotal_web":  0.0,
                "subtotal_tienda": 0.0,
            })
            continue

        if product["type"] == "simple":
            precio_web    = product.get("precio_web", 0.0)
            precio_tienda = product.get("precio_tienda", 0.0)
            variant_label = ""
        else:
            variant = find_variant(pid, vid)
            precio_web    = variant.get("precio_web", 0.0) if variant else 0.0
            precio_tienda = variant.get("precio_tienda", 0.0) if variant else 0.0
            variant_label = variant.get("label", vid) if variant else vid

        result.append({
            "product_id":      pid,
            "variant_id":      vid,
            "name":            product["name"],
            "variant_label":   variant_label,
            "quantity":        qty,
            "precio_web":      precio_web,
            "precio_tienda":   precio_tienda,
            "subtotal_web":    round(precio_web * qty, 2),
            "subtotal_tienda": round(precio_tienda * qty, 2),
        })
    return result

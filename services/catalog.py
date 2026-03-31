"""
services/catalog.py
-------------------
Capa de adaptación del catálogo de productos.
Lee el products.json (Miscelánea García) y proporciona una representación
interna uniforme para que el resto de la app no dependa del formato crudo.

Estructura interna normalizada de un producto:
{
    "id": str,
    "name": str,
    "type": "simple" | "variable",
    "category_id": str,
    "category_label": str,
    "available": bool,
    "description": str,
    # Sólo si type == "simple":
    "precio_tienda": float,
    "precio_web": float,
    # Sólo si type == "variable":
    "variants": [
        {
            "id": str,
            "label": str,
            "precio_tienda": float,
            "precio_web": float,
        }, ...
    ]
}

Meta de la tienda se expone vía get_store_meta().
"""

import json
import os
from functools import lru_cache

# Ruta al JSON del catálogo
_CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "products.json"
)


# ─── Carga y normalización ────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_catalog() -> dict:
    """
    Lee y devuelve el JSON crudo del catálogo.
    Se cachea en memoria para no leer disco en cada request.
    Llama reset_catalog_cache() si necesitas recargar en caliente.
    """
    path = os.path.abspath(_CATALOG_PATH)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def reset_catalog_cache():
    """Limpia la caché para forzar recarga del JSON."""
    load_catalog.cache_clear()


def normalize_catalog() -> list[dict]:
    """
    Devuelve la lista de productos normalizados.
    Soporta tanto productos 'simple' como 'variable'.
    Los campos faltantes se rellenan con valores seguros.
    """
    raw = load_catalog()
    categories = {c["id"]: c.get("label", c["id"]) for c in raw.get("categories", [])}
    products = []

    for p in raw.get("products", []):
        if not p.get("available", True):
            continue  # omitir productos no disponibles

        base = {
            "id": p["id"],
            "name": p.get("name", "Producto"),
            "type": p.get("type", "simple"),
            "category_id": p.get("categoryId", ""),
            "category_label": categories.get(p.get("categoryId", ""), "General"),
            "available": p.get("available", True),
            "description": p.get("description", ""),
        }

        if base["type"] == "simple":
            base["precio_tienda"] = float(p.get("precio_tienda", 0))
            base["precio_web"]    = float(p.get("precio_web", 0))

        elif base["type"] == "variable":
            variants = []
            for v in p.get("variants", []):
                variants.append({
                    "id":            v["id"],
                    "label":         v.get("label", "Variante"),
                    "precio_tienda": float(v.get("precio_tienda", 0)),
                    "precio_web":    float(v.get("precio_web", 0)),
                })
            base["variants"] = variants

        products.append(base)

    return products


# ─── Búsqueda ────────────────────────────────────────────────────────────────

def get_all_products() -> list[dict]:
    """Devuelve todos los productos normalizados (disponibles)."""
    return normalize_catalog()


def find_product_by_id(product_id: str) -> dict | None:
    """Busca un producto por su id. Devuelve None si no existe."""
    for p in normalize_catalog():
        if p["id"] == product_id:
            return p
    return None


def find_variant(product_id: str, variant_id: str) -> dict | None:
    """
    Busca una variante específica dentro de un producto variable.
    Devuelve None si el producto o la variante no existe.
    """
    product = find_product_by_id(product_id)
    if not product or product["type"] != "variable":
        return None
    for v in product.get("variants", []):
        if v["id"] == variant_id:
            return v
    return None


def get_store_meta() -> dict:
    """Devuelve la sección 'meta' del catálogo (tienda, moneda, envíos)."""
    return load_catalog().get("meta", {})


def get_delivery_options() -> dict:
    """Devuelve las opciones de entrega definidas en el JSON."""
    meta = get_store_meta()
    return meta.get("deliveryOptions", {})


def get_categories() -> list[dict]:
    """Devuelve las categorías disponibles."""
    return load_catalog().get("categories", [])


# ─── Utilidad para el formulario ─────────────────────────────────────────────

def get_products_for_select() -> list[dict]:
    """
    Devuelve una lista simplificada de productos para poblar
    el <select> del formulario de verificación.
    Incluye variantes dentro de cada producto.
    """
    result = []
    for p in get_all_products():
        item = {
            "id":   p["id"],
            "name": p["name"],
            "type": p["type"],
        }
        if p["type"] == "simple":
            item["precio_tienda"] = p["precio_tienda"]
            item["precio_web"]    = p["precio_web"]
            item["variants"] = []
        else:
            item["variants"] = p.get("variants", [])
        result.append(item)
    return result

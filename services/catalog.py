"""
services/catalog.py
-------------------
Capa de adaptación del catálogo de productos (products.json).
Proporciona un índice de búsqueda para que el parser pueda
encontrar productos por nombre parcial, alias o variante.

Estructura interna normalizada:
{
    "id": str,
    "name": str,
    "type": "simple" | "variable",
    "category_id": str,
    "category_label": str,
    "available": bool,
    "description": str,
    "precio_tienda": float,     # solo si simple
    "precio_web": float,        # solo si simple
    "variants": [               # solo si variable
        {"id": str, "label": str, "precio_tienda": float, "precio_web": float}
    ]
}
"""

import json
import os
import unicodedata
import difflib
from functools import lru_cache

_CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "products.json"
)

# ─── Alias manuales ────────────────────────────────────────────────────────────
# Mapeo de términos informales → id del producto en el JSON
# Agrega más aquí según los pedidos reales que recibas
PRODUCT_ALIASES: dict[str, str] = {
    # Bebidas
    "coca":           "coca-600-001",
    "coke":           "coca-600-001",
    "coca cola":      "coca-600-001",
    "cocacola":       "coca-600-001",
    "refresco cola":  "coca-600-001",
    "pepsi":          "pepsi-600-001",
    "agua":           "agua-ciel-001",
    "aguita":         "agua-ciel-001",
    "agua ciel":      "agua-ciel-001",
    "ciel":           "agua-ciel-001",
    "jumex":          "jumex-473-001",
    "boing":          "boing-355-001",
    "electrolit":     "electrolit-001",
    "suero":          "electrolit-001",
    # Botanas
    "sabritas":       "sabritas-001",
    "papas":          "sabritas-001",
    "papas sabritas": "sabritas-001",
    "doritos":        "doritos-001",
    "ruffles":        "ruffles-001",
    "cheetos":        "cheetos-001",
    "churrumais":     "churrumais-001",
    "churros":        "churrumais-001",
    "takis":          "takis-001",
    "chips":          "chips-001",
    # Galletas y dulces
    "principe":       "principe-001",
    "triki":          "triki-trakes-001",
    "trikitrakes":    "triki-trakes-001",
    "gansito":        "gansito-001",
    "barritas":       "barritas-001",
    "submarinos":     "submarinos-001",
    "pastisetas":     "pastisetas-001",
    "mazapan":        "mazapan-001",
    "mazapán":        "mazapan-001",
    # Lácteos
    "leche":          "leche-lala-001",
    "leche lala":     "leche-lala-001",
    "lala":           "leche-lala-001",
    "alpura":         "leche-alpura-001",
    "leche alpura":   "leche-alpura-001",
    "yogurt":         "yogurt-danone-220-001",
    "danone":         "yogurt-danone-220-001",
    "yogurt lala":    "yogurt-lala-bebible-001",
    "yakult":         "yakult-001",
    "crema":          "crema-lala-001",
    # Carnes
    "chorizo":        "chorizo-001",
    "cecina":         "cecina-001",
    "enchilada":      "enchilada-001",
    "carne enchilada":"enchilada-001",
    "bistec":         "bistec-001",
    "bistec de res":  "bistec-001",
    "res":            "bistec-001",
    "chuleta":        "chuletas-001",
    "chuletas":       "chuletas-001",
    "cerdo":          "chuletas-001",
    # Higiene
    "papel":          "papel-regio-001",
    "papel higienico":"papel-regio-001",
    "regio":          "papel-regio-001",
    "paracetamol":    "paracetamol-001",
    "ibuprofeno":     "ibuprofeno-001",
    "colgate":        "pasta-colgate-001",
    "pasta dental":   "pasta-colgate-001",
    "zote":           "jabon-zote-001",
    "jabon":          "jabon-zote-001",
    "jabón":          "jabon-zote-001",
    "sedal":          "shampoo-sedal-001",
    "shampoo":        "shampoo-sedal-001",
}

# Alias de variantes (texto → id de variante o keyword)
VARIANT_ALIASES: dict[str, str] = {
    # Tamaños
    "medio kilo":  "500g",
    "medio":       "500g",
    "medios":      "500g",
    "1/2 kilo":    "500g",
    "1/2kg":       "500g",
    "½ kilo":      "500g",
    "½kg":         "500g",
    "500g":        "500g",
    "500gr":       "500g",
    "500 gr":      "500g",
    "chico":       "500g",     # a veces "chico" = tamaño pequeño
    "1 kilo":      "1kg",
    "1kg":         "1kg",
    "1 kg":        "1kg",
    "kilo":        "1kg",
    "kilos":       "1kg",
    "grande":      "1kg",
    # Sabores / tipos
    "normal":      "normal",
    "clasica":     "normal",
    "clásica":     "normal",
    "original":    "original",
    "sin azucar":  "sin-azucar",
    "sin azúcar":  "sin-azucar",
    "light":       "light",
    "entera":      "entera",
    "deslactosada":"deslactosada",
    "mango":       "mango",
    "durazno":     "durazno",
    "fresa":       "fresa",
    "manzana":     "manzana",
    "guayaba":     "guayaba",
    "tamarindo":   "tamarindo",
    "piña":        "pina",
    "pina":        "pina",
    "chocolate":   "chocolate",
    "vainilla":    "vainilla",
    "toronja":     "toronja",
    "jamon":       "jamon",
    "jamón":       "jamon",
    "queso":       "queso",
    "nacho":       "nacho",
    "torciditos":  "torciditos",
    "bolitas":     "bolitas",
    "adobadas":    "adobadas",
    "limon":       "limon",
    "limón":       "limon",
}


# ─── Carga y normalización ─────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_catalog() -> dict:
    """Lee y cachea el JSON crudo del catálogo."""
    path = os.path.abspath(_CATALOG_PATH)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def reset_catalog_cache():
    load_catalog.cache_clear()
    build_search_index.cache_clear()


def normalize_catalog() -> list[dict]:
    """Devuelve todos los productos disponibles en formato interno uniforme."""
    raw = load_catalog()
    categories = {c["id"]: c.get("label", c["id"]) for c in raw.get("categories", [])}
    products = []
    for p in raw.get("products", []):
        if not p.get("available", True):
            continue
        base = {
            "id":             p["id"],
            "name":           p.get("name", "Producto"),
            "type":           p.get("type", "simple"),
            "category_id":    p.get("categoryId", ""),
            "category_label": categories.get(p.get("categoryId", ""), "General"),
            "available":      True,
            "description":    p.get("description", ""),
        }
        if base["type"] == "simple":
            base["precio_tienda"] = float(p.get("precio_tienda", 0))
            base["precio_web"]    = float(p.get("precio_web", 0))
            base["variants"]      = []
        else:
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


# ─── Índice de búsqueda ────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def build_search_index() -> dict:
    """
    Construye un índice para búsqueda rápida por texto normalizado.
    Devuelve:
    {
        "by_id":    {product_id: product_dict},
        "by_token": {token: [product_id, ...]},  # tokenizado
        "aliases":  {alias_normalized: product_id},
    }
    """
    products = normalize_catalog()
    by_id    = {}
    by_token = {}
    aliases  = {}

    for p in products:
        by_id[p["id"]] = p
        # Indexar tokens del nombre
        for token in _tokenize(p["name"]):
            by_token.setdefault(token, [])
            if p["id"] not in by_token[token]:
                by_token[token].append(p["id"])

    # Agregar alias manuales normalizados
    for alias, pid in PRODUCT_ALIASES.items():
        aliases[_normalize_text(alias)] = pid

    return {"by_id": by_id, "by_token": by_token, "aliases": aliases}


# ─── Búsqueda de productos ─────────────────────────────────────────────────────

def find_product_by_id(pid: str) -> dict | None:
    idx = build_search_index()
    return idx["by_id"].get(pid)


def find_best_product_match(query: str) -> tuple[dict | None, float]:
    """
    Busca el mejor producto para un texto de consulta (nombre informal).
    Devuelve (product_dict|None, confidence 0-1).

    Estrategia (en orden de prioridad):
    1. Alias exacto
    2. Token exacto en el índice
    3. Coincidencia difusa con difflib en nombres de productos
    """
    idx   = build_search_index()
    q_norm = _normalize_text(query)

    # 1. Alias exacto
    if q_norm in idx["aliases"]:
        pid = idx["aliases"][q_norm]
        return idx["by_id"].get(pid), 0.99

    # 2. Alias parcial (el query contiene un alias)
    best_alias, best_pid = None, None
    best_len = 0
    for alias_norm, pid in idx["aliases"].items():
        if alias_norm in q_norm and len(alias_norm) > best_len:
            best_alias, best_pid = alias_norm, pid
            best_len = len(alias_norm)
    if best_pid:
        return idx["by_id"].get(best_pid), 0.85

    # 3. Token exacto
    q_tokens = set(_tokenize(query))
    candidates: dict[str, int] = {}
    for token in q_tokens:
        for pid in idx["by_token"].get(token, []):
            candidates[pid] = candidates.get(pid, 0) + 1

    if candidates:
        best_pid = max(candidates, key=lambda k: candidates[k])
        token_score = candidates[best_pid] / max(len(q_tokens), 1)
        return idx["by_id"].get(best_pid), round(min(token_score * 0.9, 0.9), 2)

    # 4. Coincidencia difusa en nombres
    all_names = [(p["name"], p["id"]) for p in normalize_catalog()]
    name_strings = [n for n, _ in all_names]
    matches = difflib.get_close_matches(query, name_strings, n=1, cutoff=0.4)
    if matches:
        matched_name = matches[0]
        pid = next(pid for name, pid in all_names if name == matched_name)
        score = difflib.SequenceMatcher(None, q_norm, _normalize_text(matched_name)).ratio()
        return idx["by_id"].get(pid), round(score * 0.75, 2)

    return None, 0.0


def find_variant_match(product: dict, variant_query: str) -> dict | None:
    """
    Encuentra la variante más apropiada dentro de un producto variable.
    Soporta: tamaños (kilo, 500g), sabores, etc.
    """
    if not product or product["type"] == "simple":
        return None
    variants = product.get("variants", [])
    if not variants:
        return None

    q_norm = _normalize_text(variant_query)

    # Mapear el query a una keyword canónica via VARIANT_ALIASES
    canonical = None
    for alias, canon in VARIANT_ALIASES.items():
        if _normalize_text(alias) in q_norm:
            canonical = canon
            break

    # Buscar en los ids y labels de las variantes
    for v in variants:
        v_id_norm   = _normalize_text(v["id"])
        v_lab_norm  = _normalize_text(v["label"])
        if canonical:
            if canonical in v_id_norm or canonical in v_lab_norm:
                return v
        # Texto directo
        if q_norm in v_id_norm or q_norm in v_lab_norm:
            return v

    # Coincidencia difusa en labels
    labels = [v["label"] for v in variants]
    close  = difflib.get_close_matches(variant_query, labels, n=1, cutoff=0.5)
    if close:
        return next(v for v in variants if v["label"] == close[0])

    return None


def find_variant(product_id: str, variant_id: str) -> dict | None:
    """Busca una variante por product_id y variant_id exactos."""
    product = find_product_by_id(product_id)
    if not product:
        return None
    for v in product.get("variants", []):
        if v["id"] == variant_id:
            return v
    return None


def get_all_products() -> list[dict]:
    return normalize_catalog()


def get_store_meta() -> dict:
    return load_catalog().get("meta", {})


def get_delivery_options() -> dict:
    return get_store_meta().get("deliveryOptions", {})


def get_products_for_select() -> list[dict]:
    """Lista simplificada para poblar selects en formularios."""
    result = []
    for p in get_all_products():
        item = {"id": p["id"], "name": p["name"], "type": p["type"]}
        if p["type"] == "simple":
            item["precio_tienda"] = p.get("precio_tienda", 0)
            item["precio_web"]    = p.get("precio_web", 0)
            item["variants"] = []
        else:
            item["variants"] = p.get("variants", [])
        result.append(item)
    return result


# ─── Utilidades internas ───────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """
    Normaliza texto: minúsculas, sin acentos, sin puntuación extra.
    """
    text = text.lower().strip()
    # Quitar acentos
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return text


def _tokenize(text: str) -> list[str]:
    """Divide el texto normalizado en tokens de ≥ 3 caracteres."""
    import re
    norm = _normalize_text(text)
    tokens = re.split(r"[\s\-_\/]+", norm)
    return [t for t in tokens if len(t) >= 3]

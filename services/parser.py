"""
services/parser.py
------------------
Parser inteligente de texto libre para pedidos de delivery.

Flujo:
    texto_pegado → build_detected_order(text) → OrderAnalysis

El parser:
- soporta texto informal (WhatsApp, dictado, trascripción)
- extrae cantidades: "2", "3x", "1 kg", "medio kilo"
- detecta tipo de entrega por palabras clave
- detecta total, subtotal y envío reportados
- busca coincidencias contra el catálogo por alias y nombre parcial
- si no está seguro, marca advertencia sin inventar
- normaliza acentos y mayúsculas

NO usa IA externa. Solo regex + difflib + heurísticas.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from services.catalog import (
    find_best_product_match,
    find_variant_match,
    get_delivery_options,
    _normalize_text,
)

# ─── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class DetectedItem:
    """Un producto detectado en el texto del pedido."""
    raw_text:      str          # fragmento original del texto
    product_id:    str | None   # id del producto en el catálogo
    variant_id:    str | None   # id de la variante (si aplica)
    product_name:  str          # nombre del producto sugerido
    variant_label: str          # label de la variante sugerida
    quantity:      float        # cantidad detectada
    precio_web:    float        # precio al cliente
    precio_tienda: float        # precio costo tienda
    confidence:    float        # 0-1, confianza del match
    warning:       str | None   # advertencia si hay ambigüedad

    @property
    def subtotal_web(self) -> float:
        return round(self.precio_web * self.quantity, 2)

    @property
    def subtotal_tienda(self) -> float:
        return round(self.precio_tienda * self.quantity, 2)

    def to_dict(self) -> dict:
        return {
            "raw_text":      self.raw_text,
            "product_id":    self.product_id,
            "variant_id":    self.variant_id,
            "product_name":  self.product_name,
            "variant_label": self.variant_label,
            "quantity":      self.quantity,
            "precio_web":    self.precio_web,
            "precio_tienda": self.precio_tienda,
            "subtotal_web":  self.subtotal_web,
            "subtotal_tienda": self.subtotal_tienda,
            "confidence":    self.confidence,
            "warning":       self.warning,
        }


@dataclass
class OrderAnalysis:
    """Resultado completo del análisis de un texto de pedido."""
    raw_text:          str
    client_name:       str | None   = None
    phone:             str | None   = None
    delivery_type:     str | None   = None
    reported_subtotal: float | None = None
    reported_shipping: float | None = None
    reported_total:    float | None = None
    detected_items:    list[DetectedItem] = field(default_factory=list)
    unrecognized:      list[str]    = field(default_factory=list)
    warnings:          list[str]    = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "raw_text":          self.raw_text,
            "client_name":       self.client_name,
            "phone":             self.phone,
            "delivery_type":     self.delivery_type,
            "reported_subtotal": self.reported_subtotal,
            "reported_shipping": self.reported_shipping,
            "reported_total":    self.reported_total,
            "detected_items":    [i.to_dict() for i in self.detected_items],
            "unrecognized":      self.unrecognized,
            "warnings":          self.warnings,
        }


# ─── Palabras a ignorar ────────────────────────────────────────────────────────
STOPWORDS = {
    "hola", "buenas", "buen", "dias", "tardes", "noches", "por", "favor",
    "porfavor", "gracias", "quiero", "quisiera", "me", "puede", "un", "una",
    "unos", "unas", "del", "de", "la", "el", "los", "las", "con", "sin",
    "para", "que", "pedido", "orden", "mi", "su", "tu", "pido", "necesito",
    "llevo", "dame", "dar", "por", "please", "mandame", "manda",
    "son", "seria", "seria", "cuanto", "cuánto", "total", "cobrar",
    "subtotal", "envio", "envío", "costo", "precio", "vale", "pesos",
    "mxn", "transferencia", "efectivo", "pago", "ok", "okey", "y",
}

# Números en español
SPANISH_NUMBERS: dict[str, float] = {
    "un": 1, "uno": 1, "una": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "media": 0.5, "medio": 0.5,
}

# Frases que indican el final de un ítem (separadores)
LINE_SEPARATORS = re.compile(
    r"(?:\n|(?<![\d])\.(?!\d)|"       # salto de línea o punto (no decimal)
    r"(?:^|\s),(?:\s|$))",            # coma al inicio/final de palabra
    re.MULTILINE
)

# ─── Función principal ─────────────────────────────────────────────────────────

def build_detected_order(raw_text: str) -> OrderAnalysis:
    """
    Analiza un texto libre de pedido y devuelve un OrderAnalysis.
    Este es el punto de entrada principal del parser.
    """
    analysis = OrderAnalysis(raw_text=raw_text)

    # Normalizar texto para análisis (sin modificar raw_text)
    text = raw_text.strip()

    # 1. Extraer metadatos del pedido
    analysis.phone         = extract_phone(text)
    analysis.delivery_type = extract_delivery_type(text)
    analysis.reported_total, \
    analysis.reported_subtotal, \
    analysis.reported_shipping = extract_reported_amounts(text)
    analysis.client_name   = extract_client_name(text)

    # 2. Extraer líneas candidatas (posibles productos)
    candidate_lines = extract_candidate_lines(text)

    # 3. Intentar hacer match de cada línea con el catálogo
    recognized    = []
    unrecognized  = []

    for line in candidate_lines:
        item = match_line_to_catalog(line)
        if item:
            recognized.append(item)
        else:
            clean = line.strip()
            if clean and len(clean) > 2:
                unrecognized.append(clean)

    analysis.detected_items = recognized
    analysis.unrecognized   = unrecognized

    # 4. Advertencias globales
    if not recognized:
        analysis.warnings.append(
            "No se detectaron productos en el texto. "
            "Revisa el formato o agrega los productos manualmente."
        )
    if analysis.reported_total is None:
        analysis.warnings.append(
            "No se detectó el total reportado en el texto. "
            "Ingrésalo manualmente en el campo correspondiente."
        )
    if analysis.delivery_type is None:
        analysis.warnings.append(
            "No se detectó el tipo de entrega. "
            "Selecciónalo manualmente."
        )
    low_conf = [i for i in recognized if i.confidence < 0.6]
    if low_conf:
        names = ", ".join(i.raw_text for i in low_conf)
        analysis.warnings.append(
            f"Baja confianza en: {names}. Revisa que el producto sea correcto."
        )

    return analysis


# ─── Extractores de metadatos ──────────────────────────────────────────────────

def extract_phone(text: str) -> str | None:
    """Extrae número de teléfono de 10 dígitos."""
    # Formato: 10 dígitos seguidos (con o sin espacios, guiones)
    pattern = re.compile(
        r"(?:tel[eé]fono|tel|cel|celular|whatsapp)?[\s:]*"
        r"(\d[\d\s\-\.]{8,12}\d)"
    )
    for m in pattern.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) == 10:
            return digits
    # Número pegado de 10 dígitos
    m = re.search(r"\b(\d{10})\b", text)
    return m.group(1) if m else None


def extract_delivery_type(text: str) -> str | None:
    """
    Detecta tipo de entrega:
    'pickup' = recoger en tienda
    'local'  = domicilio en Atoyac
    'outside'= fuera de Atoyac
    """
    norm = _normalize_text(text)
    opts = get_delivery_options()

    # Fuera (debe ir antes de 'local' para evitar falsos positivos)
    if re.search(r"fuera|afuera|otro municipio|otro lado|colonia|rancho", norm):
        return "outside"

    # Local / domicilio
    if re.search(r"domicilio|a domicilio|delivery|entrega|llevar|lleven|manden|reparto|envio|envío", norm):
        return "local"

    # Recoger
    if re.search(r"recoger|paso a|pasar|en tienda|yo recojo|recojo yo|pick.?up", norm):
        return "pickup"

    return None


def extract_reported_amounts(text: str) -> tuple[float | None, float | None, float | None]:
    """
    Extrae total, subtotal y envío reportados del texto.
    Devuelve (total, subtotal, envio).
    """
    norm = _normalize_text(text)

    def _find_amount(patterns: list[str]) -> float | None:
        for pat in patterns:
            m = re.search(pat, norm)
            if m:
                try:
                    return float(m.group(1).replace(",", ""))
                except (ValueError, IndexError):
                    pass
        return None

    total = _find_amount([
        r"total[:\s]+\$?\s*(\d[\d,]*(?:\.\d+)?)",
        r"\$\s*(\d[\d,]*(?:\.\d+)?)\s+(?:en\s+)?total",
        r"son\s+\$?\s*(\d[\d,]*(?:\.\d+)?)",
        r"cobrar?\s+\$?\s*(\d[\d,]*(?:\.\d+)?)",
        r"pagar?\s+\$?\s*(\d[\d,]*(?:\.\d+)?)",
        r"queda(?:ron)?\s+en\s+\$?\s*(\d[\d,]*(?:\.\d+)?)",
        r"total\s+(?:que\s+le\s+dije|reportado|estimado)[:\s]+\$?\s*(\d[\d,]*(?:\.\d+)?)",
    ])

    subtotal = _find_amount([
        r"subtotal[:\s]+\$?\s*(\d[\d,]*(?:\.\d+)?)",
        r"productos?[:\s]+\$?\s*(\d[\d,]*(?:\.\d+)?)",
    ])

    envio = _find_amount([
        r"envio[:\s]+\$?\s*(\d[\d,]*(?:\.\d+)?)",
        r"enví?o[:\s]+\$?\s*(\d[\d,]*(?:\.\d+)?)",
        r"delivery[:\s]+\$?\s*(\d[\d,]*(?:\.\d+)?)",
        r"flete[:\s]+\$?\s*(\d[\d,]*(?:\.\d+)?)",
    ])

    return total, subtotal, envio


def extract_client_name(text: str) -> str | None:
    """
    Intenta extraer el nombre del cliente.
    Busca patrones como "para Juan", "cliente: María", "nombre: Pedro"
    """
    patterns = [
        r"(?:cliente|nombre|para|pedido de)[:\s]+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})",
        r"^([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})?)\s*[\:\-\n]",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.MULTILINE)
        if m:
            name = m.group(1).strip()
            if name.lower() not in STOPWORDS and len(name) > 2:
                return name
    return None


# ─── Extracción de líneas candidatas ──────────────────────────────────────────

def extract_candidate_lines(text: str) -> list[str]:
    """
    Divide el texto en fragmentos candidatos a ser productos.
    Filtra líneas que claramente no son productos (metadatos).
    """
    # Dividir por saltos de línea, y también por comas
    lines = re.split(r"\n|(?<!\d),(?!\d)", text)

    # También dividir por numeración de lista: "1.", "2.", "- "
    expanded = []
    for line in lines:
        sub = re.split(r"(?:^|\s)(?:\d+\.|[-*•])\s+", line)
        expanded.extend(sub)

    candidate_lines = []
    for line in expanded:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        line_lower = _normalize_text(line)

        # Saltar líneas que son claramente metadatos
        if re.search(
            r"^(?:total|subtotal|envio|envi.{1,2}o|hola|buenas|gracias|"
            r"pedido:|fecha:|tel[eé]fono:|whatsapp:|nombre:|cliente:|"
            r"domicilio:|direcci[oó]n:|nota:|notas:|observaci[oó]n:|"
            r"pago|transferencia|efectivo|ok\s*$)",
            line_lower,
        ):
            continue

        # Saltar si es solo números (probablemente un total)
        if re.match(r"^\$?\d+(?:\.\d+)?$", line.strip()):
            continue

        candidate_lines.append(line)

    return candidate_lines


# ─── Match de línea con catálogo ──────────────────────────────────────────────

def match_line_to_catalog(line: str) -> DetectedItem | None:
    """
    Analiza un fragmento de texto e intenta mapearlo a un producto del catálogo.
    Devuelve un DetectedItem o None si no pudo reconocer nada.
    """
    # Extraer cantidad y texto del producto
    quantity, product_query, variant_hint = parse_quantity_and_product(line)

    if not product_query:
        return None

    # Buscar producto
    product, confidence = find_best_product_match(product_query)

    if not product or confidence < 0.25:
        return None

    # Buscar variante
    variant      = None
    variant_hint_combined = f"{variant_hint} {product_query}"  # buscar variante en todo el texto
    if product["type"] == "variable":
        # Intentar con el hint específico de variante
        if variant_hint:
            variant = find_variant_match(product, variant_hint)
        # Si no, buscar en el texto completo de la línea
        if not variant:
            variant = find_variant_match(product, variant_hint_combined)
        # Si sigue sin variante, buscar en la línea entera
        if not variant:
            variant = find_variant_match(product, line)

    # Obtener precios
    warning = None
    if product["type"] == "simple":
        precio_web    = product.get("precio_web", 0.0)
        precio_tienda = product.get("precio_tienda", 0.0)
        variant_id    = None
        variant_label = ""
    elif variant:
        precio_web    = variant.get("precio_web", 0.0)
        precio_tienda = variant.get("precio_tienda", 0.0)
        variant_id    = variant["id"]
        variant_label = variant["label"]
    else:
        # Producto variable sin variante detectada → usar la primera
        variants = product.get("variants", [])
        if variants:
            v = variants[0]
            precio_web    = v.get("precio_web", 0.0)
            precio_tienda = v.get("precio_tienda", 0.0)
            variant_id    = v["id"]
            variant_label = v["label"]
            warning = (
                f"No se detectó la variante. "
                f"Se usó '{variant_label}' por defecto — verifica."
            )
        else:
            precio_web    = 0.0
            precio_tienda = 0.0
            variant_id    = None
            variant_label = ""
            warning = "Variante no detectada y no hay variantes disponibles."

    if confidence < 0.6:
        warning = (warning or "") + (
            f" Coincidencia aproximada ({int(confidence*100)}%). Verifica el producto."
        )

    return DetectedItem(
        raw_text      = line,
        product_id    = product["id"],
        variant_id    = variant_id,
        product_name  = product["name"],
        variant_label = variant_label,
        quantity      = quantity,
        precio_web    = precio_web,
        precio_tienda = precio_tienda,
        confidence    = confidence,
        warning       = warning.strip() if warning else None,
    )


# ─── Extracción de cantidad y producto ────────────────────────────────────────

# Patrón de cantidad al inicio: "2 coca", "3x sabritas", "1.5 kg bistec"
_QTY_PREFIX = re.compile(
    r"^"
    r"(?P<qty_num>\d+(?:[.,]\d+)?)\s*"          # número: "2", "1.5"
    r"(?:x\s*)?"                                  # opcional: "x"
    r"(?:(?P<unit>kg|kilo|kilos|g|gr|gramos?|litros?|lts?|ml|pz|pza|piezas?|pack|six(?:pack)?)\s*)?"  # unidad
    r"(?:de\s*)?",                                # "de "
    re.IGNORECASE,
)

# Palabras de cantidad en español al inicio
_SPANISH_QTY = re.compile(
    r"^(?P<word>un(?:a)?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|medio|media)"
    r"(?:\s+(?P<unit>kg|kilo|kilos|gramos?|litros?))?(?:\s+de\s*)?",
    re.IGNORECASE,
)

# Variante en el texto — peso al final o con separador
_VARIANT_SUFFIX = re.compile(
    r"(?:de\s+)?(?P<variant>"
    r"medio\s+kilo|½\s*kilo|1/2\s*kilo|1\s*kilo|1\s*kg|"
    r"(?:mango|durazno|fresa|manzana|vainilla|chocolate|"
    r"toronja|guayaba|tamarindo|pi[ñn]a|limon|limon|nacho|"
    r"original|adobada[s]?|queso|jamon|torcidito[s]?|bolita[s]?|"
    r"entera|deslactosada|sin\s+azucar|light|normal|natural|"
    r"fresa\s+platano|fresa\s+pl[aá]tano|"
    r"flamin.?hot)"
    r")\s*$",
    re.IGNORECASE,
)


def parse_quantity_and_product(line: str) -> tuple[float, str, str]:
    """
    Extrae (cantidad, texto_producto, hint_variante) de una línea.

    Ejemplos:
        "2 cocas 600"          → (2.0, "cocas 600", "")
        "1 kg bistec"          → (1.0, "bistec", "1kg")
        "medio kilo de chorizo"→ (0.5, "chorizo", "medio kilo")
        "3x sabritas adobadas" → (3.0, "sabritas", "adobadas")
        "1 coca sin azucar"    → (1.0, "coca", "sin azucar")
    """
    text  = line.strip()
    qty   = 1.0
    unit  = ""
    remainder = text

    # Intentar número español al inicio
    m = _SPANISH_QTY.match(text)
    if m:
        word = m.group("word").lower()
        qty  = SPANISH_NUMBERS.get(word, 1.0)
        unit = m.group("unit") or ""
        remainder = text[m.end():]

    else:
        # Intentar número arábigo al inicio
        m = _QTY_PREFIX.match(text)
        if m and m.group("qty_num"):
            qty  = float(m.group("qty_num").replace(",", "."))
            unit = m.group("unit") or ""
            remainder = text[m.end():]

    # Extraer hint de variante del resto de la línea
    variant_hint = unit.lower() if unit else ""
    m_var = _VARIANT_SUFFIX.search(remainder)
    if m_var:
        v = m_var.group("variant").strip()
        variant_hint = (variant_hint + " " + v).strip()
        remainder    = remainder[:m_var.start()].strip()

    # Corrección: si el qty vino de "medio/media" + unidad de peso,
    # lo tratamos como "1 presentación de ½ kilo" (la variante ya tiene ese precio)
    _is_half_size = (
        qty == 0.5 and
        re.search(r"^(kg|kilo|kilos|gramos?)$", unit, re.IGNORECASE)
    )
    if _is_half_size:
        qty = 1.0
        variant_hint = ("medio kilo " + variant_hint).strip()

    # Limpiar el producto
    product_text = _clean_product_text(remainder)

    # Si no quedó nada útil, usar el texto completo
    if not product_text and not variant_hint:
        product_text = _clean_product_text(text)

    return qty, product_text, variant_hint


def _clean_product_text(text: str) -> str:
    """
    Limpia el texto del nombre del producto:
    - quita stopwords al inicio/final
    - quita caracteres extraños
    - quita sufijos de unidad comunes
    """
    text = text.strip(" ,.-:*•")

    # Remover emojis/símbolos
    text = re.sub(r"[^\w\sáéíóúñüÁÉÍÓÚÑÜ½/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Remover palabras que no aportan
    words = text.split()
    cleaned = [
        w for w in words
        if w.lower() not in STOPWORDS
        and len(w) > 1
    ]
    return " ".join(cleaned)

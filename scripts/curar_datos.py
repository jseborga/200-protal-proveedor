"""
Script de curado de datos v3: limpieza inteligente de nombres + filtros mejorados.

Mejoras sobre v2:
- Normaliza nombres: usa descripcion cuando el nombre es pobre/codigo
- Filtra servicios, alquileres, transporte, reparaciones
- Consolida variantes del mismo producto (GRAVA x2 -> merge)
- Genera archivo para normalizacion con IA (paso separado)
- Categoriza items en "review" con razones especificas

Uso:
    python scripts/curar_datos.py

Genera:
    data/curated_suppliers.json     - proveedores con compras reales
    data/curated_products.json      - materiales de construccion curados
    data/curated_prices.json        - historial de precios por producto
    data/curated_review.json        - items que necesitan revision manual
    data/curated_ai_normalize.json  - items para normalizar con IA
    data/curated_report.txt         - resumen del curado
"""

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import median

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# ── Exclusion: items que NO son materiales de construccion ────
EXCLUDE_KEYWORDS = [
    # Mano de obra
    "MANO DE OBRA", "MDO-", "MAESTRO", "AYUDANTE", "CAPATAZ",
    "CONTRAMAESTRO", "ALBANYIL", "ALBANIL", "JORNALERO",
    "SIN FACTURA", "C_F", "S_F",
    # Impuestos y ajustes
    "IMPUESTOS", "AJUSTE DE SALDO", "REDONDEO", "IVA ", "IT ",
    "RETENCION", "PROVISION",
    # Alimentacion y campamento
    "ALMUERZO", "COMIDA", "DESAYUNO", "CENA", "CAMPAMENTO",
    "HOSPEDAJE", "HOTEL", "ALOJAMIENTO", "REFRIGERIO",
    # Combustibles
    "GASOLINA", "DIESEL", "COMBUSTIBLE", "GAS LICUADO", "GLP",
    # Oficina y papeleria
    "ARCHIVADOR", "PAPEL BOND", "PAPELERIA", "IMPRESORA",
    "COMPUTADOR", "LAPTOP", "RESMA", "HOJAS BOND", "BOLIGRAFO",
    "CARPETA", "FOLDER", "CUADERNO", "LAPIZ", "BORRADOR",
    "FOTOCOPIA", "SELLO SECO", "NOTA FISCAL", "TONER",
    "TINTA PARA", "USB ", "MOUSE", "TECLADO", "MONITOR",
    "WORKSTATION", "HP Z800", "CARTUCHO HP",
    "CLIP G", "CLIP M", "CLIP P", "DOBLE CLIP", "FASTENER",
    "RESALTADOR", "MARCADOR PERMANENTE", "TIJERA",
    "CAJAS ARCHIVO", "BANDERITAS", "CD GRABABLE", "DVD GRABABLE",
    "FUNDAS PLASTICAS", "LIGAS N", "TAJADOR", "GRAPAS",
    # Limpieza
    "LIMPIEZA", "DETERGENTE", "DESINFECTANTE", "JABON LIQUIDO",
    "PAPEL HIGIENICO", "ESCOBA", "TRAPEADOR", "BASURERO",
    "AMBIENTADOR", "SERVILLETA",
    # Vehiculos y seguros
    "RASTREO SATELITAL", "POLIZA", "SEGURO VEHIC",
    "SOAT", "INSPECCION VEHIC",
    # Servicios generales
    "INTERNET", "ADSL", "ENERGIA ELECTRICA", "TELEFONO",
    "CELULAR", "ALQUILER DE OFICINA",
    "TRANSPORTE C/", "TRANSPORTE S/", "FLETE",
    "RETIRO DE ESCOMBROS", "RETIRO ESCOMBROS",
    "MANTENIMIENTO",
    # Generico
    "GENERICO SERVICIO", "SERVICIO GENERICO",
    "ACTUALIZACION DE MATRICULA",
    # Ensayos y laboratorio
    "ENSAYO", "LABORATORIO", "PRUEBA DE",
    "CONO DE ARENA", "DENSIDAD IN SITU",
    # v3: Servicios y alquileres
    "ALQUILER", "ARRENDATARIO", "REPARACION DE", "REPARACI",
    "ACARREO", "TRANSPORTE EN VOLQUETA", "TRANSPORTE GRUA",
    "RETIRO DE ", "RETIRO DEL ",
    "INSTALACION DE GAS", "INSTALACION GPS",
    "CORTADO DE FIERRO", "CORTADO DE COLUMNA",
    "EXTRACCION DE NUCLEO",
    "FLEXION DE VIGA",
    "VIBRADOR DE CONCRETO",
    "OPERADOR RETRO",
    "TRASLADO",
    "FABRICACION DE",
    "ACHICADO DE PUERTA",
    "PLASTIFICADO DE PISO",
    "INSTALACION DE PISO",
    "MONTAJE DE PISO",
    "SERVICIO DOBLADO",
    "ESTERILIZADOR",
    "LIMPIA VIDRIOS",
    "EMBRAGUE", "KIT APV",
    "RETIRO DE CUBIERTA",
    "RETROEXCAVADORA",  # es maquinaria, no material
    "MAQUINARIA RETRO",
    "CAMPANA_PARRILLA",
    "BANQUINA DE CEMENTO",
    "PORTON CON REJAS",
    "BOMBA CENTRIFUGA",
    "AUTORETRACTIL",
    "GRANITO TUMA",  # error de datos
    "BRISTOL",       # error de datos - no es aislante
    "CORTE DEPORTIVO",  # error de datos
    "TRANSPORTE MATERIAL",  # servicio de transporte
    "SERVICIO+",  # servicios compuestos
]

# Refs que son claramente no-construccion
EXCLUDE_REFS = {
    "MDO-S_F_MANO_DE_OBRA_SIN_FACTURA", "MDO-Maestro", "MDO-Ayudante",
    "MDO-Capataz", "MDO-Contramaestro", "MDO-C_F",
    "IMPUESTOS", "AJUSTE_DE_SALDO",
    "COMIDA_CAMPAMENTO_ALM.", "COMIDA_CAMPAMENTO_DES.",
    "COMIDA_CAMPAMENTO_CENA", "HOSPEDAJE",
    "001-inter",
}

# ── Categorizacion por keywords ──────────────────────────────
CATEGORY_RULES = [
    (["CEMENTO", "CEM-", "CEM0", "PORTLAND", "IP30", "IP40", "VIACHA"], "cemento"),
    (["HORMIGON", "HORM-", "HORM_", "PREMEZCLADO", "CONCRETO", "MPA", "H-25", "H-21", "H-30"], "cemento"),
    (["ARENA FINA", "ARENA CORRIENTE", "ARENA COMUN", "GRAVA", "GRAVILLA",
      "AGREGADO", "RIPIO", "PIEDRA CHANCADA", "PIEDRA BRUTA", "CASCOTE",
      "CANTO RODADO"], "agregados"),
    (["BARRA", "FIERRO", "FIERRO CORRUGADO", "ACERO", "MALLA", "ALAMBRE",
      "ESTRIBOS", "ESTRIBO", "VARILLA", "CORRUGADO", "GEOMALLA"], "acero"),
    (["CABLE UTP", "CABLE COXIAL", "CABLE MULTIPAR", "CABLE COBRE",
      "INTERRUPTOR", "TOMACORRIENTE", "TOMA ", "TABLERO ELECTR",
      "BREAKER", "DISYUNTOR", "FLUORESCENTE", "FOCO ", "LED ", "LUMINARIA",
      "CINTA AISL", "CANALETA ELECTR", "TUBERIA CONDUIT",
      "ENCHUFE", "SOCKET", "LAMPARA"], "electrico"),
    (["CABLE DE ACERO", "CABLE ACERO", "TEZADOR", "GRAMPA P/CABLE"], "acero"),  # cable de acero es acero no electrico
    (["TUBO PVC", "TUBERIA PVC", "CODO PVC", "TEE PVC", "UNION PVC",
      "REDUCCION PVC", "VALVULA", "INODORO", "LAVAMANOS", "LAVAPLATO",
      "GRIFO", "DUCHA", "LLAVE DE PASO", "SIFON", "TRAMPA"], "sanitario"),
    (["TUBO GALV", "TUBERIA GALV", "CODO GALV", "CANERIA",
      "NIPLE", "BUSHING", "CODO HG", "TEE HG", "CODO FG", "TEE FG"], "plomeria"),
    (["MADERA", "TABLA", "LISTON", "TABLON", "VIGA MADERA",
      "VIGUETA", "TIRANTE", "MACHIHEMBR", "PARQUET", "TRIPLAY",
      "CAOBA", "CEDRO", "PINO ", "EUCALIPTO", "ROBLE"], "madera"),
    (["PINTURA", "ESMALTE", "LATEX", "BARNIZ", "ANTICORROSIVO",
      "SELLADOR", "IMPRIMANTE", "THINNER", "AGUARRAS", "BROCHA",
      "RODILLO", "LIJA ", "MASILLA"], "pintura"),
    (["CERAMICA", "CERAMICO", "PORCELANATO", "AZULEJO", "PISO ",
      "FRAGUA", "PEGAMENTO CERAMICO", "KLAUKOL", "JUNTA"], "ceramica"),
    (["CLAVO", "TORNILLO", "PERNO", "TUERCA", "ARANDELA",
      "BISAGRA", "CHAPA", "CERRADURA", "CANDADO", "PASADOR",
      "GANCHO", "TIRAFONDO", "ANCLAJE", "TACO FISHER",
      "REMACHE", "GRAPA CERCO", "PRENSA", "ABRAZADERA"], "ferreteria"),
    (["MARTILLO", "COMBO", "ALICATE", "DESTORNILLADOR",
      "SERRUCHO", "NIVEL", "PLOMADA", "FLEXOMETRO",
      "PALA", "PICO", "CARRETILLA", "BUGUI", "BALDE",
      "VIBRADORA", "MEZCLADORA", "AMOLADORA", "TALADRO",
      "DISCO DE CORTE", "DISCO DIAMANT", "SIERRA", "ESMERIL"], "herramientas"),
    (["CALAMINA", "TECHO", "CUBIERTA", "CUMBRERA", "CANALON",
      "BAJANTE", "PERFIL C", "PERFIL L", "PERFIL U",
      "CHAPA GALV", "PLANCHA GALV", "ONDULINE"], "techos"),
    (["IMPERMEABILIZ", "SIKA", "ADITIVO", "MEMBRANA",
      "CHEMA", "CURADOR", "DESMOLDANTE", "ACELERANTE",
      "RETARDANTE", "PLASTIFICANTE"], "impermeabilizantes"),
    (["LADRILLO", "BLOQUE", "BOVEDILLA", "VIGUETA PRE",
      "LOSETA", "LOSA PRE", "POSTE", "ADOQUIN"], "prefabricados"),
    (["CASCO", "GUANTE", "CHALECO", "BOTAS DE SEGURIDAD",
      "ARNES", "LINEA DE VIDA", "GAFA", "PROTECTOR",
      "EXTINTOR", "CONO ", "CINTA SEGURIDAD",
      "DESLIZADOR", "SISTEMA LINEA"], "seguridad"),
    (["VIDRIO", "ESPEJO", "MAMPARA", "VITROBLOCK"], "vidrios"),
    (["AISLANTE", "TECNOPOR", "PLASTOFORMO", "POLIESTIRENO",
      "POLIETILENO", "FOAM", "FIBRA DE VIDRIO"], "aislantes"),
    (["ANDAMIO"], "maquinaria"),
    (["GRUA "], "maquinaria"),
]

# ── UOM inference rules ──────────────────────────────────────
UOM_RULES = [
    (["CEMENTO", "CEM-", "CEM0", "PORTLAND", "IP30", "IP40", "BOLSA", "BLS"], "bls"),
    (["ARENA", "GRAVA", "GRAVILLA", "RIPIO", "PIEDRA", "HORMIGON",
      "HORM-", "HORM_", "PREMEZCLADO", "CONCRETO", "M3", "METRO CUBICO"], "m3"),
    (["BARRA", "VARILLA", "FIERRO CORRUGADO"], "varilla"),
    (["CABLE", "SOGA", "CUERDA", "MANGUERA",
      "METRO LINEAL", "ML "], "ml"),
    (["ALAMBRE", "ROLLO DE ALAMBRE"], "rollo"),
    (["MALLA", "CALAMINA", "PLANCHA", "LAMINA", "CHAPA",
      "METRO CUADRADO", "M2 "], "m2"),
    (["PINTURA", "LATEX", "ESMALTE", "BARNIZ", "SELLADOR",
      "GALON", "GL "], "gl"),
    (["THINNER", "AGUARRAS", "LITRO", "LT "], "lt"),
    (["ARENA FINA", "ARENA CORRIENTE", "ARENA COMUN"], "m3"),
    (["SACO", "YESO", "CAL "], "saco"),
    (["TUBO", "CANERIA", "TUBERIA"], "tubo"),
    (["ANDAMIO"], "glb"),
    (["GRUA "], "glb"),
    (["ROLLO", "CINTA"], "rollo"),
    (["CLAVO", "TORNILLO", "PERNO", "REMACHE"], "kg"),
    (["MADERA", "TABLA", "LISTON", "TABLON"], "pza"),
    (["LADRILLO", "BLOQUE", "BOVEDILLA", "ADOQUIN"], "pza"),
    (["CAJA"], "caja"),
]

# ── Rangos de precios unitarios esperados por producto/categoria ──
PRICE_ANCHORS = {
    "CEMENTO": (35, 100, "bls"),
    "HORMIGON": (500, 1000, "m3"),
    "ARENA": (50, 300, "m3"),
    "GRAVA": (50, 300, "m3"),
    "AGREGADO": (50, 300, "m3"),
    "PIEDRA": (30, 300, "m3"),
    "BARRA": (10, 200, "varilla"),
    "FIERRO": (10, 200, "varilla/pza"),
    "ALAMBRE": (5, 800, "rollo/kg"),
    "MALLA": (20, 500, "m2/pza"),
    "CLAVO": (5, 25, "kg"),
    "TORNILLO": (0.05, 5, "pza"),
    "LADRILLO": (0.3, 5, "pza"),
    "BLOQUE": (0.5, 10, "pza"),
    "MADERA": (5, 250, "pza"),
    "PINTURA": (15, 800, "gl/lt"),
    "LATEX": (15, 800, "gl"),
    "ESMALTE": (15, 600, "gl"),
    "CALAMINA": (30, 200, "pza"),
    "TUBO PVC": (5, 300, "tubo"),
    "CABLE": (1, 50, "ml"),
    "SIKA": (10, 300, "pza/lt"),
    "VIDRIO": (20, 500, "m2/pza"),
    "CERAMICA": (5, 200, "m2/pza"),
    "CASCO": (15, 80, "pza"),
    "GUANTE": (5, 200, "par/pza"),
    "DISCO": (10, 100, "pza"),
}

CATEGORY_PRICE_RANGE = {
    "cemento": (20, 1200),
    "acero": (5, 2000),
    "agregados": (30, 400),
    "ferreteria": (0.05, 500),
    "pintura": (5, 1000),
    "madera": (3, 500),
    "electrico": (0.5, 2000),
    "sanitario": (1, 5000),
    "plomeria": (2, 500),
    "ceramica": (3, 500),
    "herramientas": (5, 5000),
    "techos": (1, 500),
    "impermeabilizantes": (5, 2000),
    "prefabricados": (0.3, 200),
    "seguridad": (2, 5000),
    "vidrios": (10, 2000),
    "aislantes": (5, 500),
    "maquinaria": (50, 50000),
}


# ══════════════════════════════════════════════════════════════
# v3: LOGICA DE NORMALIZACION DE NOMBRES
# ══════════════════════════════════════════════════════════════

def is_name_poor(name):
    """Determina si un nombre es de baja calidad y necesita mejora."""
    if not name:
        return True
    n = name.strip()
    # Es solo un codigo numerico
    if n.replace("-", "").replace("_", "").replace(" ", "").replace(".", "").isdigit():
        return True
    # Codigo multi-segmento: "00.66.051.111", "01-234-567"
    if re.match(r'^\d{2,}([.\-_]\d+){1,}(\s|$)', n):
        return True
    # Parece dimension sin contexto: "1x35x3", "2x4x350", "1x25x350"
    if re.match(r'^\d+[xX]\d+[xX]?\d*$', n):
        return True
    # Codigo alfanumerico corto tipo "BA15x15PP", "NB732", "BT100mm"
    if re.match(r'^[A-Z]{1,4}\d+[xX]?\d*[A-Z]*$', n) and len(n) < 15:
        return True
    # Marca + codigo: "BACO NB732-500", "SIKA 226 MS-POL"
    if re.match(r'^[A-Z]{2,6}\s+[A-Z0-9]{2,}[\-]\d+', n):
        return True
    # Specs tecnicas sin nombre: "30MPa Ip40 67-5-10", "fck=30"
    if re.match(r'^\d+\s*MPa\b', n, re.IGNORECASE):
        return True
    # Muy corto (menos de 6 caracteres)
    if len(n) < 6:
        return True
    # Parece un codigo (todo mayusculas/numeros, corto)
    if len(n) < 12 and all(c.isupper() or c.isdigit() or c in "_-/ ." for c in n):
        # Pero no si es un nombre real como "GRAVA", "CABLE"
        real_words = ["GRAVA", "CABLE", "CLAVO", "CEMENTO", "ARENA", "MADERA",
                      "PERNO", "TUERCA", "GANCHO", "FOCO", "SIFON"]
        if n.upper() not in real_words:
            return True
    # Baja proporcion de letras vs numeros/simbolos
    alpha_count = sum(1 for c in n if c.isalpha())
    if len(n) > 5 and alpha_count / len(n) < 0.3:
        return True
    # Es una palabra sola demasiado generica
    generic_singles = {
        "material", "materiales", "cemento", "madera", "agregados",
        "pintura", "cable", "cortado", "cuerda", "barras", "extraccion",
        "porcelanato", "anclaje", "mezcladora", "amoladora", "pala",
        "bisagra", "tuerca", "pernos", "foco", "rodillos",
    }
    if name.lower().strip() in generic_singles:
        return True
    return False


def build_better_name(name, description, ref, product_catalog_entry=None, category_hint=None):
    """Construye un nombre mejorado usando toda la info disponible."""
    candidates = []

    # 1. Si la desc tiene mas info, usarla
    if description:
        first_line = description.split("\n")[0].strip()
        # Descartar desc tipo "segun cotizacion adjunta" o muy vagas
        vague = ["segun cotizacion", "adjunta", "varios", "ver detalle", "material de construccion"]
        if first_line and len(first_line) > 5 and not any(v in first_line.lower() for v in vague):
            candidates.append(first_line)

    # 2. Datos del catalogo de producto
    if product_catalog_entry:
        cat_label = product_catalog_entry.get("label", "")
        cat_desc = product_catalog_entry.get("description", "").split("\n")[0].strip()
        if cat_label and len(cat_label) > len(name):
            candidates.append(cat_label)
        if cat_desc and len(cat_desc) > len(name):
            candidates.append(cat_desc)

    # 3. Combinar ref + name si el ref aporta info
    if ref and ref != name and len(ref) > 3:
        # Si ref parece un nombre real (no solo codigo)
        ref_clean = ref.replace("_", " ").replace("-", " ").strip()
        if any(c.isalpha() for c in ref_clean) and len(ref_clean) > 5:
            candidates.append(ref_clean)

    # 4. El nombre original si no es codigo puro
    if name and not name.replace("-", "").replace("_", "").replace(" ", "").isdigit():
        candidates.append(name)

    if not candidates:
        # Fallback: si el nombre parece dimension (ej: "1x35x3"), prefijarlo con categoria
        if re.match(r'^\d+[xX]\d+', name) and category_hint:
            prefix_map = {"madera": "Madera", "acero": "Barra", "electrico": "Cable"}
            prefix = prefix_map.get(category_hint, "")
            if prefix:
                return f"{prefix} {name}"
        # Si empieza con codigo alfanumerico corto (ej: "BT100mm"), usar desc
        return name

    # Elegir el candidato mas informativo
    best = max(candidates, key=lambda c: _name_quality_score(c))

    # Si el mejor candidato es muy generico ("madera"), enriquecer con el nombre original
    # si este tiene dimensiones
    if best.lower().strip() in ("madera", "acero", "cable") and name != best:
        if re.search(r'\d', name):  # nombre original tiene numeros (dimensiones)
            best = f"{best} {name}"

    return clean_product_name(best)


def _name_quality_score(name):
    """Puntaje de calidad para un nombre de producto."""
    if not name:
        return 0
    score = 0
    # Penalizar nombres muy cortos
    if len(name) < 5:
        score -= 10
    # Premiar longitud razonable (10-60 chars)
    if 10 <= len(name) <= 60:
        score += 5
    elif len(name) > 60:
        score += 2  # demasiado largo tambien es malo
    # Premiar si tiene numeros con contexto (dimensiones: 1/2, 3/8, 12mm)
    if re.search(r'\d+[/x]\d+|\d+\s*mm|\d+\s*m\b|\d+\s*kg', name, re.IGNORECASE):
        score += 10
    # Premiar palabras clave de construccion
    construction_words = [
        "barra", "cemento", "arena", "grava", "hormigon", "madera",
        "clavo", "tornillo", "tubo", "cable", "pintura", "calamina",
        "ladrillo", "bloque", "vigueta", "malla", "alambre", "sika",
    ]
    name_lower = name.lower()
    for w in construction_words:
        if w in name_lower:
            score += 3
    # Penalizar si es solo un codigo
    if name.replace("-", "").replace("_", "").replace(" ", "").isdigit():
        score -= 20
    # Penalizar si todo es mayusculas sin separacion
    if name.isupper() and " " not in name and len(name) > 8:
        score -= 3
    # Penalizar nombres con baja proporcion de letras
    alpha_ratio = sum(1 for c in name if c.isalpha()) / max(len(name), 1)
    if alpha_ratio < 0.4:
        score -= 15
    # Penalizar codigos multi-segmento
    if re.match(r'^\d{2,}([.\-_]\d+){1,}', name.strip()):
        score -= 20
    return score


def clean_product_name(name):
    """Limpia y normaliza un nombre de producto."""
    if not name:
        return name
    # Quitar saltos de linea (reales y literales \n de Dolibarr)
    for sep in ["\n", "\\n"]:
        if sep in name:
            parts = name.split(sep)
            # Keep first part if meaningful, else try second
            first = parts[0].strip()
            if first and len(first) >= 3:
                name = first
            elif len(parts) > 1 and parts[1].strip():
                name = parts[1].strip()
            break
    # Quitar espacios multiples
    name = re.sub(r"\s+", " ", name).strip()
    # Quitar comillas
    name = name.strip("\"'")
    # Quitar codigos numericos al inicio: "00.66.051.111 sellador" -> "sellador"
    name = re.sub(r'^[\d]{2,}(?:[.\-_][\d]+){1,}\s+', '', name)
    # Quitar codigos alfanumericos al inicio: "MAT-001-B sellador" -> "sellador"
    name = re.sub(r'^[A-Z]{2,5}[\-_][\d]+[\-_]?[A-Z0-9]?\s+', '', name)
    # Interpretar specs tecnicas como nombres de producto
    # "30MPa Ip40 67-5-10" -> "Hormigon fck=30MPa"
    mpa_match = re.match(r'^(\d+)\s*MPa\b', name, re.IGNORECASE)
    if mpa_match:
        name = f"Hormigon fck={mpa_match.group(1)}MPa"
    # Title case si esta todo en mayusculas (pero preservar siglas como PVC, LED)
    if name.isupper() and len(name) > 5:
        name = smart_title_case(name)
    # Truncar si es demasiado largo
    if len(name) > 100:
        name = name[:97] + "..."
    return name.strip()


def smart_title_case(text):
    """Title case que preserva siglas comunes."""
    siglas = {
        "PVC", "LED", "HG", "FG", "SDR", "HP", "AWG", "THW", "UTP",
        "SDS", "MPA", "IP30", "IP40", "BLS", "CAT", "SMD", "HDPE",
        "PPR", "CPVC", "GU", "GU10", "MM", "CM", "MT", "ML", "M2", "M3",
        "KG", "GLB", "PR", "BOL", "VP1", "VP2", "VP3", "VP4", "VP5", "VP6",
        "II", "III", "IV", "DN", "NIT",
    }
    words = text.split()
    result = []
    for word in words:
        word_upper = word.upper().rstrip(".,;:()")
        if word_upper in siglas:
            result.append(word.upper())
        elif re.match(r'^\d+[xX/]\d+', word):  # dimensiones: 1/2, 3x4
            result.append(word)
        elif re.match(r'^\d+', word):  # empieza con numero
            result.append(word)
        else:
            result.append(word.capitalize())
        # Preservar puntuacion
    return " ".join(result)


# ── v3: Deteccion de servicios (no solo excluidos) ───────────
SERVICE_INDICATORS = [
    "INSTALACION", "FABRICACION", "MONTAJE", "REPARACION",
    "ARMADO DE ", "TRANSPORTE", "SERVICIO", "ALQUILER",
    "PROVISION E INSTALACION", "MANO DE OBRA",
    "RETIRO", "TRASLADO", "OPERADOR",
]

def is_service(name, description=""):
    """Detecta si un item es un servicio y no un material."""
    combined = f"{name} {description}".upper()
    # Si tiene tanto material como servicio, verificar mas
    for indicator in SERVICE_INDICATORS:
        if indicator in combined:
            # Excepciones: "provision e instalacion" puede incluir material
            if "PROVISION" in combined and "INSTALACION" in combined:
                return False  # probablemente incluye el material
            # "servicio+aditivos" incluye material
            if "ADITIVO" in combined or "MATERIAL" in combined:
                return False
            return True
    return False


# ── v3: Consolidacion de variantes ───────────────────────────
def make_consolidation_key(name, uom, category):
    """Genera una clave para agrupar variantes del mismo producto."""
    name_norm = normalize(name)

    # Patrones especificos de consolidacion
    consolidation_patterns = [
        # BOL CLAVO / BOL.CLAVO -> clavo
        (r"^bol\.?\s*clavo\s*(\d+[/ ]?\d*)\s*pr$", r"clavo \1 pr"),
        # TORNILLO T1/T2 PUNTA AGUJA/BROCA -> tornillo tipo punta
        (r"^tornillo[s]?\s*(t[12]|ciser.t[12])?\s*punta\s*(aguja|broca).*$", r"tornillo punta \2"),
        # ARENA CORRIENTE con fechas -> arena corriente
        (r"^arena corriente\s+\d+.*$", r"arena corriente"),
        # ARENA FINA con ubicaciones -> arena fina
        (r"^arena fina\s+\w+.*$", r"arena fina"),
        # Grava con especificaciones -> grava tipo
        (r"^grava\s*(chancada|semichancada|rodada)?.*$", r"grava \1"),
        # HORMIGON con variantes de formato
        (r"^hormigon\s*(\d+)\s*mpa$", r"hormigon \1 MPA"),
        # MADERA DE CONSTRUCCION generico
        (r"^madera de construccion$", None),  # None = marcar para dimension
        # VIGUETA PRETENSADA VP{n}
        (r"^vigueta\s*pretensada\s*(vp\d+)?.*$", r"vigueta pretensada \1"),
    ]

    for pattern, replacement in consolidation_patterns:
        match = re.match(pattern, name_norm)
        if match:
            if replacement is None:
                # No consolidar, cada uno es unico (necesita dimension)
                return None
            key = re.sub(pattern, replacement, name_norm).strip()
            return f"{key}|{uom}|{category}"

    return None  # no se consolida


# ── Helpers existentes (de v2) ────────────────────────────────
def normalize(text):
    """Lowercase, strip accents, collapse whitespace."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_excluded(name, ref=""):
    """Check if item should be excluded."""
    name_upper = name.upper()
    ref_upper = ref.upper() if ref else ""
    combined = f"{name_upper} {ref_upper}"

    for kw in EXCLUDE_KEYWORDS:
        if kw in combined:
            return True
    if ref in EXCLUDE_REFS:
        return True
    if ref_upper.startswith("MDO"):
        return True
    return False


def infer_category(name, ref=""):
    """Try to categorize based on keywords."""
    combined = f"{name} {ref}".upper()
    for keywords, cat in CATEGORY_RULES:
        for kw in keywords:
            if kw in combined:
                return cat
    return None


def infer_uom(name, ref="", default="pza"):
    """Infer unit of measure from name/ref."""
    combined = f"{name} {ref}".upper()
    for keywords, uom in UOM_RULES:
        for kw in keywords:
            if kw in combined:
                return uom
    return default


def is_price_outlier(unit_price, name, category):
    """Check if price is an outlier based on product anchors and category ranges."""
    name_upper = name.upper()
    for keyword, (lo, hi, _) in PRICE_ANCHORS.items():
        if keyword in name_upper:
            if unit_price < lo * 0.3 or unit_price > hi * 5:
                return True
            return False
    if category and category in CATEGORY_PRICE_RANGE:
        lo, hi = CATEGORY_PRICE_RANGE[category]
        if unit_price < lo * 0.2 or unit_price > hi * 10:
            return True
        return False
    return unit_price > 50000


def clean_phone(phone):
    """Normalize phone number for Bolivia."""
    if not phone:
        return ""
    phone = re.sub(r"[^\d+]", "", phone)
    phone = phone.lstrip("+")
    if phone.startswith("591"):
        local = phone[3:]
    else:
        local = phone
    if len(local) >= 7:
        if not phone.startswith("591"):
            phone = "591" + local
        return phone
    return ""


def validate_whatsapp_bolivia(phone):
    """Validate if a phone number is WhatsApp-capable in Bolivia.
    Returns: (is_valid, clean_number, issue)
    - Bolivia movil (WhatsApp): 591 + 8 digitos empezando con 6 o 7
    - Fijo (NO WhatsApp): empieza con 2, 3, 4, 5
    - Placeholder: todo ceros o "0000000000"
    """
    clean = re.sub(r'[^\d]', '', phone or '')
    if not clean:
        return False, "", "empty"
    if clean.startswith('591'):
        local = clean[3:]
    elif clean.startswith('0'):
        local = clean[1:]  # quitar 0 inicial local
    else:
        local = clean
    # Placeholder
    if not local or all(c == '0' for c in local):
        return False, "", "placeholder"
    # Longitud Bolivia: 8 digitos
    if len(local) != 8:
        return False, f"591{local}" if len(local) >= 7 else clean, "wrong_length"
    # Fijo: empieza con 2, 3, 4, 5
    if local[0] in ('2', '3', '4', '5'):
        return False, f"591{local}", "landline"
    # Movil: empieza con 6, 7
    if local[0] in ('6', '7'):
        return True, f"591{local}", None
    return False, f"591{local}", "unknown_prefix"


def infer_department(address, phone):
    """Infer department from address text and phone prefix."""
    combined = (address or "").upper()
    phone_clean = re.sub(r"[^\d]", "", phone or "")
    dept_keywords = {
        "La Paz": ["LA PAZ", "MURILLO", "EL ALTO", "ZONA SUR", "CALACOTO",
                    "SOPOCACHI", "MIRAFLORES", "SAN PEDRO", "OBRAJES",
                    "ACHUMANI", "IRPAVI", "MALLASA", "VIACHA"],
        "Cochabamba": ["COCHABAMBA", "CERCADO", "QUILLACOLLO", "SACABA",
                       "TIQUIPAYA", "COLCAPIRHUA"],
        "Santa Cruz": ["SANTA CRUZ", "ANDRES IBANEZ", "WARNES", "MONTERO",
                        "EQUIPETROL", "URUBO"],
        "Oruro": ["ORURO"],
        "Potosi": ["POTOSI"],
        "Tarija": ["TARIJA"],
        "Sucre": ["SUCRE", "CHUQUISACA"],
        "Beni": ["TRINIDAD", "BENI"],
        "Pando": ["COBIJA", "PANDO"],
    }
    for dept, keywords in dept_keywords.items():
        for kw in keywords:
            if kw in combined:
                return dept
    if phone_clean.startswith("591"):
        phone_clean = phone_clean[3:]
    if len(phone_clean) >= 1:
        prefix = phone_clean[0]
        prefix_map = {"2": "La Paz", "4": "Cochabamba", "3": "Santa Cruz",
                      "5": "Potosi", "6": "Tarija"}
        if prefix in prefix_map:
            return prefix_map[prefix]
    return "La Paz"


def filter_outlier_prices(prices, factor=3.0):
    """Remove price outliers beyond factor * median."""
    if len(prices) < 3:
        return prices
    med = median(prices)
    if med == 0:
        return prices
    return [p for p in prices if p / med < factor and med / p < factor]


# ══════════════════════════════════════════════════════════════
# MAIN PROCESSING
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("CURACION DE DATOS v3 - APU Marketplace")
    print("Limpieza inteligente + normalizacion de nombres")
    print("=" * 60)

    # ── Step 1: Read pedidos ────────────────────────────────
    print("\n[1/7] Leyendo pedidos de compra...")
    pedidos_lines = []
    with open(DATA_DIR / "pedidos de productos_precios.csv", encoding="latin-1") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            if len(row) < 41:
                continue
            pedidos_lines.append({
                "supplier_id_doli": row[0],
                "supplier_name": row[1].strip(),
                "supplier_address": row[2].strip(),
                "supplier_phone": row[6].strip(),
                "supplier_nit": row[13].strip(),
                "order_ref": row[15].strip(),
                "order_date": row[18].strip(),
                "line_desc": row[30].strip(),
                "line_qty": row[32].strip(),
                "line_total_iva": row[35].strip(),
                "line_type": row[37].strip(),
                "product_id_doli": row[38].strip(),
                "product_ref": row[39].strip(),
                "product_label": row[40].strip(),
            })
    print(f"  {len(pedidos_lines)} lineas de pedido leidas")

    product_lines = [l for l in pedidos_lines if l["line_type"] == "0"]
    service_lines = [l for l in pedidos_lines if l["line_type"] == "1"]
    print(f"  {len(product_lines)} tipo producto, {len(service_lines)} tipo servicio")

    # ── Step 2: Read product catalog ────────────────────────
    print("\n[2/7] Leyendo catalogo de productos...")
    product_catalog = {}
    with open(DATA_DIR / "export_produit_1.csv", encoding="latin-1") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            if len(row) < 20:
                continue
            pid = row[0].strip()
            product_catalog[pid] = {
                "ref": row[1].strip(),
                "label": row[2].strip(),
                "description": row[3].strip(),
                "supplier_name": row[18].strip(),
                "pmp": row[19].strip(),
            }
    print(f"  {len(product_catalog)} productos en catalogo")

    # ── Step 3: Read suppliers ───────────────────────────────
    print("\n[3/7] Leyendo terceros...")
    supplier_catalog = {}
    with open(DATA_DIR / "terceros_bolivia14.04.2026.csv", encoding="latin-1") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            if len(row) < 20:
                continue
            sid = row[0].strip()
            is_supplier = row[4].strip() == "1"
            if not is_supplier:
                continue
            supplier_catalog[sid] = {
                "name": row[1].strip(),
                "address": row[11].strip(),
                "city": row[13].strip(),
                "state": row[14].strip(),
                "phone": row[17].strip(),
                "email": row[20].strip(),
                "nit": row[28].strip(),
            }
    print(f"  {len(supplier_catalog)} proveedores en catalogo")

    # ── Step 4: Process and aggregate ────────────────────────
    print("\n[4/7] Procesando y agregando datos...")

    product_data = defaultdict(lambda: {
        "refs": set(), "labels": set(), "descriptions": set(),
        "prices": [], "price_records": [], "suppliers": set(),
        "order_count": 0, "total_qty": 0,
        "catalog_entry": None,
    })

    supplier_products = defaultdict(set)
    active_suppliers = {}

    excluded_count = 0
    service_count = 0
    outlier_count = 0

    for line in product_lines:
        pid = line["product_id_doli"]
        ref = line["product_ref"]
        label = line["product_label"]

        if pid in product_catalog:
            cat_data = product_catalog[pid]
            if not label:
                label = cat_data["label"]
            if not ref:
                ref = cat_data["ref"]

        if is_excluded(label, ref):
            excluded_count += 1
            continue

        # v3: Filtrar servicios por contenido
        if is_service(label, line.get("line_desc", "")):
            service_count += 1
            continue

        try:
            qty = float(line["line_qty"])
            total = float(line["line_total_iva"])
            if qty <= 0 or total <= 0:
                continue
            unit_price = total / qty
        except (ValueError, ZeroDivisionError):
            continue

        order_date = line["order_date"]
        if not order_date:
            continue

        category = infer_category(label, ref)

        if is_price_outlier(unit_price, label, category):
            outlier_count += 1
            continue

        pd = product_data[pid]
        if ref:
            pd["refs"].add(ref)
        if label:
            # Clean literal \n from Dolibarr early
            clean_label = label.split("\\n")[0].strip() if "\\n" in label else label
            pd["labels"].add(clean_label)
        if line["line_desc"]:
            desc_clean = line["line_desc"].replace("\\n", "\n").split("\n")[0][:200]
            pd["descriptions"].add(desc_clean)
        # Guardar catalogo
        if pid in product_catalog and not pd["catalog_entry"]:
            pd["catalog_entry"] = product_catalog[pid]

        pd["prices"].append(unit_price)
        pd["price_records"].append({
            "unit_price": round(unit_price, 2),
            "quantity": qty,
            "date": order_date,
            "order_ref": line["order_ref"],
            "supplier_name": line["supplier_name"],
        })
        pd["suppliers"].add(line["supplier_name"])
        pd["order_count"] += 1
        pd["total_qty"] += qty

        supplier_products[line["supplier_name"]].add(pid)
        if line["supplier_name"] not in active_suppliers:
            active_suppliers[line["supplier_name"]] = {
                "name": line["supplier_name"],
                "address": line["supplier_address"],
                "phone": line["supplier_phone"],
                "nit": line["supplier_nit"],
            }

    print(f"  {len(product_data)} productos unicos con compras reales")
    print(f"  {excluded_count} lineas excluidas (keywords)")
    print(f"  {service_count} lineas excluidas (servicios)")
    print(f"  {outlier_count} lineas excluidas (precio outlier)")
    print(f"  {len(active_suppliers)} proveedores con ventas")

    # ── Step 5: Curate products with name normalization ─────
    print("\n[5/7] Curando productos con normalizacion de nombres...")

    curated_products = []
    review_products = []
    ai_normalize_queue = []
    category_counts = Counter()
    seen_names = {}  # name_normalized -> product, for dedup

    for pid, data in product_data.items():
        labels = list(data["labels"])
        label = max(labels, key=len) if labels else ""
        if not label:
            continue

        # Limpiar newlines temprano (Dolibarr mete \n literal y real en labels)
        for sep in ["\\n", "\n"]:
            if sep in label:
                parts = label.split(sep)
                first = parts[0].strip()
                if first and len(first) >= 3:
                    label = first
                elif len(parts) > 1:
                    label = parts[1].strip()
                break

        refs = list(data["refs"])
        ref = refs[0] if refs else ""
        desc_text = list(data["descriptions"])[0] if data["descriptions"] else ""

        # v3: Normalizar nombre
        # Pre-infer category for name building
        pre_category = infer_category(label, ref)
        if is_name_poor(label):
            new_name = build_better_name(label, desc_text, ref, data.get("catalog_entry"), category_hint=pre_category)
            if new_name and new_name != label:
                label = new_name

        # Limpiar nombre (title case, etc)
        label = clean_product_name(label)

        clean_prices = filter_outlier_prices(data["prices"])
        if not clean_prices:
            clean_prices = data["prices"]
        median_price = round(median(clean_prices), 2) if clean_prices else None

        category = infer_category(label, ref)
        if not category and data["descriptions"]:
            for desc in data["descriptions"]:
                category = infer_category(desc)
                if category:
                    break

        uom = infer_uom(label, ref)

        product = {
            "name": label,
            "code": ref,
            "uom": uom,
            "category": category,
            "ref_price": median_price,
            "ref_currency": "BOB",
            "description": desc_text,
            "order_count": data["order_count"],
            "supplier_count": len(data["suppliers"]),
            "_pid": pid,
            "_original_label": max(list(data["labels"]), key=len) if data["labels"] else "",
        }

        # Decide: curated vs review vs AI
        if not category:
            product["_review_reason"] = "sin_categoria"
            review_products.append(product)
            continue
        if not median_price or median_price <= 0:
            product["_review_reason"] = "sin_precio"
            review_products.append(product)
            continue

        # Check if name is still poor after normalization
        if is_name_poor(label):
            product["_review_reason"] = "nombre_pobre"
            ai_normalize_queue.append(product)
            # Still add to curated but flag it
            curated_products.append(product)
            category_counts[category] += 1
            continue

        # Dedup by normalized name + uom
        name_key = f"{normalize(label)}|{uom}"
        if name_key in seen_names:
            existing = seen_names[name_key]
            # Merge: keep the one with more orders, accumulate price records
            if data["order_count"] > existing.get("order_count", 0):
                seen_names[name_key] = product
                # Replace in curated list
                for i, p in enumerate(curated_products):
                    if p.get("_pid") == existing.get("_pid"):
                        curated_products[i] = product
                        break
            continue
        else:
            seen_names[name_key] = product

        curated_products.append(product)
        category_counts[category] += 1

    # Sort
    curated_products.sort(key=lambda p: (p["category"] or "zzz", p["name"]))

    # Clean internal fields from output
    for p in curated_products:
        p.pop("_pid", None)
        p.pop("_original_label", None)
        p.pop("_review_reason", None)

    print(f"  {len(curated_products)} productos curados")
    print(f"  {len(review_products)} productos para revision manual")
    print(f"  {len(ai_normalize_queue)} productos para normalizar con IA")
    print(f"\n  Categorias:")
    for cat, count in category_counts.most_common():
        print(f"    {cat}: {count}")

    # ── Step 6: Curate suppliers ─────────────────────────────
    print("\n[6/7] Curando proveedores...")

    curated_product_suppliers = set()
    for p in curated_products:
        for pid, data in product_data.items():
            labels = list(data["labels"])
            best_label = max(labels, key=len) if labels else ""
            # Match por nombre limpio
            if clean_product_name(best_label) == p["name"] or best_label == p["name"]:
                curated_product_suppliers |= data["suppliers"]
                break

    curated_suppliers = []
    seen_sup_names = set()

    for sup_name, sup_info in active_suppliers.items():
        name_norm = normalize(sup_name)
        if name_norm in seen_sup_names:
            continue
        seen_sup_names.add(name_norm)

        enriched = dict(sup_info)
        for sid, cat_sup in supplier_catalog.items():
            if normalize(cat_sup["name"]) == name_norm:
                if cat_sup["email"]:
                    enriched["email"] = cat_sup["email"]
                if cat_sup["city"]:
                    enriched["city"] = cat_sup["city"]
                if cat_sup["address"] and not enriched.get("address"):
                    enriched["address"] = cat_sup["address"]
                if cat_sup["nit"] and not enriched.get("nit"):
                    enriched["nit"] = cat_sup["nit"]
                break

        whatsapp = clean_phone(enriched.get("phone", ""))
        department = infer_department(enriched.get("address", ""), enriched.get("phone", ""))

        sup_categories = set()
        for pid in supplier_products.get(sup_name, set()):
            if pid in product_data:
                labels = list(product_data[pid]["labels"])
                refs = list(product_data[pid]["refs"])
                label = max(labels, key=len) if labels else ""
                ref = refs[0] if refs else ""
                cat = infer_category(label, ref)
                if cat:
                    sup_categories.add(cat)

        # Validar WhatsApp
        is_valid_wa, clean_wa, wa_issue = validate_whatsapp_bolivia(whatsapp)

        supplier = {
            "name": sup_name,
            "whatsapp": clean_wa if is_valid_wa else "",
            "phone": enriched.get("phone", ""),
            "city": enriched.get("city") or department,
            "department": department,
            "categories": sorted(sup_categories) if sup_categories else [],
            "verification_state": "verified" if is_valid_wa else "pending",
        }
        if wa_issue:
            supplier["_wa_issue"] = wa_issue
            # Si es fijo, guardarlo como telefono en vez de whatsapp
            if wa_issue == "landline" and clean_wa:
                supplier["phone"] = clean_wa
        # Solo sobrescribir phone si no se asigno ya por landline
        if enriched.get("phone") and not supplier.get("phone"):
            supplier["phone"] = clean_phone(enriched["phone"])
        # Limpiar phone vacio
        if not supplier.get("phone"):
            supplier.pop("phone", None)
        if enriched.get("email"):
            supplier["email"] = enriched["email"]
        if enriched.get("nit"):
            supplier["nit"] = enriched["nit"]
        if enriched.get("address"):
            supplier["address"] = enriched["address"]

        curated_suppliers.append(supplier)

    curated_suppliers.sort(key=lambda s: s["name"])

    # Resumen de validacion WhatsApp
    wa_issues = Counter(s.get("_wa_issue", "valid") for s in curated_suppliers)
    wa_verified = sum(1 for s in curated_suppliers if s["verification_state"] == "verified")
    wa_pending = sum(1 for s in curated_suppliers if s["verification_state"] == "pending")
    print(f"  {len(curated_suppliers)} proveedores curados")
    print(f"  WhatsApp: {wa_verified} verificados, {wa_pending} pendientes")
    for issue, count in wa_issues.most_common():
        print(f"    {issue}: {count}")

    # ── Build price history ──────────────────────────────────
    print("\n[7/7] Generando historial de precios...")

    # Build name lookup: pid -> curated product name
    pid_to_curated_name = {}
    for pid, data in product_data.items():
        labels = list(data["labels"])
        best_label = max(labels, key=len) if labels else ""
        cleaned = clean_product_name(best_label)
        # Find matching curated product
        for p in curated_products:
            if p["name"] == cleaned or p["name"] == best_label:
                pid_to_curated_name[pid] = p["name"]
                break

    price_history = []
    for pid, data in product_data.items():
        curated_name = pid_to_curated_name.get(pid)
        if not curated_name:
            continue

        for rec in data["price_records"]:
            price_history.append({
                "product_name": curated_name,
                "supplier_name": rec["supplier_name"],
                "unit_price": rec["unit_price"],
                "currency": "BOB",
                "quantity": rec["quantity"],
                "observed_date": rec["date"],
                "source": "pedido",
                "source_ref": rec["order_ref"],
            })

    print(f"  {len(price_history)} registros de precio generados")

    # ── Save outputs ─────────────────────────────────────────
    print("\nGuardando archivos...")

    DATA_DIR.mkdir(exist_ok=True)

    with open(DATA_DIR / "curated_suppliers.json", "w", encoding="utf-8") as f:
        json.dump(curated_suppliers, f, ensure_ascii=False, indent=2)
    print(f"  curated_suppliers.json: {len(curated_suppliers)} proveedores")

    with open(DATA_DIR / "curated_products.json", "w", encoding="utf-8") as f:
        json.dump(curated_products, f, ensure_ascii=False, indent=2)
    print(f"  curated_products.json: {len(curated_products)} productos")

    with open(DATA_DIR / "curated_prices.json", "w", encoding="utf-8") as f:
        json.dump(price_history, f, ensure_ascii=False, indent=2)
    print(f"  curated_prices.json: {len(price_history)} registros de precio")

    # Review con razones
    for p in review_products:
        p.pop("_pid", None)
        p.pop("_original_label", None)
    with open(DATA_DIR / "curated_review.json", "w", encoding="utf-8") as f:
        json.dump(review_products, f, ensure_ascii=False, indent=2)
    print(f"  curated_review.json: {len(review_products)} items para revision")

    # AI normalize queue
    ai_output = []
    for p in ai_normalize_queue:
        ai_output.append({
            "current_name": p["name"],
            "description": p.get("description", ""),
            "code": p.get("code", ""),
            "category": p.get("category", ""),
            "ref_price": p.get("ref_price"),
            "uom": p.get("uom", ""),
        })
    with open(DATA_DIR / "curated_ai_normalize.json", "w", encoding="utf-8") as f:
        json.dump(ai_output, f, ensure_ascii=False, indent=2)
    print(f"  curated_ai_normalize.json: {len(ai_output)} items para IA")

    # ── Report ───────────────────────────────────────────────
    report_lines = [
        "=" * 60,
        "REPORTE DE CURACION v3",
        "=" * 60,
        "",
        f"Fuentes:",
        f"  Pedidos: {len(pedidos_lines)} lineas ({len(product_lines)} productos, {len(service_lines)} servicios)",
        f"  Catalogo productos: {len(product_catalog)}",
        f"  Catalogo proveedores: {len(supplier_catalog)}",
        "",
        f"Filtros aplicados:",
        f"  Excluidos por keywords: {excluded_count}",
        f"  Excluidos por ser servicios: {service_count}",
        f"  Excluidos por precio outlier: {outlier_count}",
        "",
        f"Resultados:",
        f"  Productos curados: {len(curated_products)}",
        f"  Productos para revision: {len(review_products)}",
        f"  Productos para normalizar con IA: {len(ai_output)}",
        f"  Proveedores curados: {len(curated_suppliers)}",
        f"  Registros de precio: {len(price_history)}",
        "",
        "Categorias:",
    ]
    for cat, count in category_counts.most_common():
        report_lines.append(f"  {cat}: {count}")

    report_lines.extend(["", "Top 20 productos por frecuencia de compra:"])
    top_products = sorted(curated_products, key=lambda p: p["order_count"], reverse=True)[:20]
    for p in top_products:
        report_lines.append(
            f"  {p['name'][:50]:50s}  x{p['order_count']:4d}  {p['ref_price']:>10.2f} Bs/{p['uom']}"
        )

    report_lines.extend(["", "Review por razon:"])
    review_reasons = Counter(p.get("_review_reason", "unknown") for p in review_products)
    for reason, cnt in review_reasons.most_common():
        report_lines.append(f"  {reason}: {cnt}")

    report_text = "\n".join(report_lines)
    with open(DATA_DIR / "curated_report.txt", "w", encoding="utf-8") as f:
        f.write(report_text)

    print("\n" + report_text)
    print("\nCuracion v3 completada!")
    print("\nSiguiente paso: ejecutar 'python scripts/ai_normalize.py' para normalizar nombres con IA")


if __name__ == "__main__":
    main()

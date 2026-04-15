"""
Script de curado de datos v2: integra terceros, productos Y pedidos.

Lee los 3 CSVs exportados de Dolibarr, cruza datos, filtra solo materiales
de construccion reales (con historial de compras), y genera JSONs listos
para subir al portal.

Uso:
    python scripts/curar_datos.py

Genera:
    data/curated_suppliers.json     - proveedores con compras reales
    data/curated_products.json      - materiales de construccion curados
    data/curated_prices.json        - historial de precios por producto
    data/curated_review.json        - items que necesitan revision manual
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
    # (keywords_in_name_or_ref, category_key)
    (["CEMENTO", "CEM-", "CEM0", "PORTLAND", "IP30", "IP40", "VIACHA"], "cemento"),
    (["HORMIGON", "HORM-", "HORM_", "PREMEZCLADO", "CONCRETO", "MPA", "H-25", "H-21", "H-30"], "cemento"),
    (["ARENA FINA", "ARENA CORRIENTE", "ARENA COMUN", "GRAVA", "GRAVILLA",
      "AGREGADO", "RIPIO", "PIEDRA CHANCADA", "PIEDRA BRUTA", "CASCOTE",
      "CANTO RODADO"], "agregados"),
    (["BARRA", "FIERRO", "FIERRO CORRUGADO", "ACERO", "MALLA", "ALAMBRE",
      "ESTRIBOS", "ESTRIBO", "VARILLA", "CORRUGADO"], "acero"),
    (["CABLE", "INTERRUPTOR", "TOMACORRIENTE", "TOMA ", "TABLERO ELECTR",
      "BREAKER", "DISYUNTOR", "FLUORESCENTE", "FOCO ", "LED ", "LUMINARIA",
      "CINTA AISL", "CANALETA ELECTR", "TUBERIA CONDUIT",
      "ENCHUFE", "SOCKET"], "electrico"),
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
      "EXTINTOR", "CONO ", "CINTA SEGURIDAD"], "seguridad"),
    (["VIDRIO", "ESPEJO", "MAMPARA", "VITROBLOCK"], "vidrios"),
    (["AISLANTE", "TECNOPOR", "PLASTOFORMO", "POLIESTIRENO",
      "POLIETILENO", "FOAM", "FIBRA DE VIDRIO"], "aislantes"),
    (["RETROEXCAVADORA", "VOLQUETA", "EXCAVADORA", "COMPACTADOR",
      "MOTONIVELADORA", "GRUA", "ANDAMIO"], "maquinaria"),
]

# ── UOM inference rules ──────────────────────────────────────
UOM_RULES = [
    # (condition_on_ref_or_label, uom_key)
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
    (["RETROEXCAVADORA", "RETRO EXCAVADORA", "VOLQUETA", "EXCAVADORA",
      "COMPACTADOR", "MOTONIVELADORA", "GRUA"], "glb"),
    (["ANDAMIO"], "glb"),
    (["ROLLO", "CINTA"], "rollo"),
    (["CLAVO", "TORNILLO", "PERNO", "REMACHE"], "kg"),
    (["MADERA", "TABLA", "LISTON", "TABLON"], "pza"),
    (["LADRILLO", "BLOQUE", "BOVEDILLA", "ADOQUIN"], "pza"),
    (["CAJA"], "caja"),
]

# ── Rangos de precios unitarios esperados por producto/categoria ──
# Precios de referencia Bolivia 2024-2026 en Bs
# Se usan para filtrar outliers (totales de linea confundidos con unitarios)
PRICE_ANCHORS = {
    # Producto especifico -> (min, max, uom)
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

# Rangos amplios por categoria (fallback si no hay ancla especifica)
CATEGORY_PRICE_RANGE = {
    "cemento": (20, 1200),        # desde aditivos hasta hormigon/m3
    "acero": (5, 2000),           # desde clavos hasta planchas
    "agregados": (30, 400),       # arenas, gravas por m3
    "ferreteria": (0.05, 500),    # desde tornillos hasta cerraduras
    "pintura": (10, 1000),        # desde lijas hasta baldes de pintura
    "madera": (3, 500),           # desde listones hasta tablones
    "electrico": (0.5, 2000),     # desde conectores hasta tableros
    "sanitario": (3, 5000),       # desde codos hasta inodoros
    "plomeria": (2, 500),         # desde niples hasta valvulas
    "ceramica": (3, 500),         # desde piso hasta porcelanato
    "herramientas": (5, 5000),    # desde destornilladores hasta vibradoras
    "techos": (5, 500),           # desde tornillos hasta calaminas
    "impermeabilizantes": (5, 2000),
    "prefabricados": (0.3, 200),  # ladrillos, bloques, viguetas
    "seguridad": (2, 1000),       # desde guantes hasta arneses
    "vidrios": (10, 2000),
    "aislantes": (5, 500),
    "maquinaria": (50, 50000),    # alquileres y equipos
}


def is_price_outlier(unit_price, name, category):
    """Check if price is an outlier based on product anchors and category ranges."""
    name_upper = name.upper()

    # Try specific product anchors first
    for keyword, (lo, hi, _) in PRICE_ANCHORS.items():
        if keyword in name_upper:
            # Use 0.3x and 5x of range to allow some flexibility
            if unit_price < lo * 0.3 or unit_price > hi * 5:
                return True
            return False

    # Fallback to category range
    if category and category in CATEGORY_PRICE_RANGE:
        lo, hi = CATEGORY_PRICE_RANGE[category]
        if unit_price < lo * 0.2 or unit_price > hi * 10:
            return True
        return False

    # No anchor: use generic sanity check (reject if > 50000 Bs for a single unit)
    return unit_price > 50000


# ── Helpers ──────────────────────────────────────────────────
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
    # Exclude refs starting with MDO
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


def clean_phone(phone):
    """Normalize phone number for Bolivia."""
    if not phone:
        return ""
    phone = re.sub(r"[^\d+]", "", phone)
    phone = phone.lstrip("+")
    # Remove leading 591 country code for local analysis
    if phone.startswith("591"):
        local = phone[3:]
    else:
        local = phone
    # Bolivia numbers: 8 digits mobile (6,7 start), 7 digits landline
    if len(local) >= 7:
        if not phone.startswith("591"):
            phone = "591" + local
        return phone
    return ""


def infer_department(address, phone):
    """Infer department from address text and phone prefix."""
    combined = (address or "").upper()
    phone_clean = re.sub(r"[^\d]", "", phone or "")

    # By address keywords
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

    # By phone prefix
    if phone_clean.startswith("591"):
        phone_clean = phone_clean[3:]
    if len(phone_clean) >= 1:
        prefix = phone_clean[0]
        prefix_map = {
            "2": "La Paz", "7": "La Paz",  # 7 can be mobile from any dept
            "4": "Cochabamba",
            "3": "Santa Cruz",
            "5": "Potosi",
            "6": "Tarija",
        }
        if prefix in prefix_map and prefix != "7":
            return prefix_map[prefix]

    return "La Paz"  # default


def filter_outlier_prices(prices, factor=3.0):
    """Remove price outliers beyond factor * median."""
    if len(prices) < 3:
        return prices
    med = median(prices)
    if med == 0:
        return prices
    return [p for p in prices if p / med < factor and med / p < factor]


# ── Main processing ──────────────────────────────────────────
def main():
    print("=" * 60)
    print("CURACION DE DATOS v2 - APU Marketplace")
    print("Integrando: terceros + productos + pedidos")
    print("=" * 60)

    # ── Step 1: Read pedidos (purchase orders) ───────────────
    print("\n[1/6] Leyendo pedidos de compra...")
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
                "line_total_iva": row[35].strip(),  # total con IVA
                "line_type": row[37].strip(),  # 0=product, 1=service
                "product_id_doli": row[38].strip(),
                "product_ref": row[39].strip(),
                "product_label": row[40].strip(),
            })

    print(f"  {len(pedidos_lines)} lineas de pedido leidas")

    # Filter: only products (type=0), not services
    product_lines = [l for l in pedidos_lines if l["line_type"] == "0"]
    print(f"  {len(product_lines)} lineas de tipo producto (excluidos {len(pedidos_lines) - len(product_lines)} servicios)")

    # ── Step 2: Read products catalog ────────────────────────
    print("\n[2/6] Leyendo catalogo de productos...")
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
    print("\n[3/6] Leyendo terceros...")
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
    print("\n[4/6] Procesando y agregando datos...")

    # Group pedido lines by product
    product_data = defaultdict(lambda: {
        "refs": set(), "labels": set(), "descriptions": set(),
        "prices": [], "price_records": [], "suppliers": set(),
        "order_count": 0, "total_qty": 0,
    })

    supplier_products = defaultdict(set)  # supplier_name -> set of product_ids
    active_suppliers = {}  # supplier_name -> supplier info from pedidos

    excluded_count = 0
    outlier_count = 0

    for line in product_lines:
        pid = line["product_id_doli"]
        ref = line["product_ref"]
        label = line["product_label"]

        # Use catalog data if available for better labels
        if pid in product_catalog:
            cat_data = product_catalog[pid]
            if not label:
                label = cat_data["label"]
            if not ref:
                ref = cat_data["ref"]

        # Skip excluded items
        if is_excluded(label, ref):
            excluded_count += 1
            continue

        # Calculate unit price
        try:
            qty = float(line["line_qty"])
            total = float(line["line_total_iva"])
            if qty <= 0 or total <= 0:
                continue
            unit_price = total / qty
        except (ValueError, ZeroDivisionError):
            continue

        # Parse date
        order_date = line["order_date"]
        if not order_date:
            continue

        # Infer category early to use in outlier detection
        category = infer_category(label, ref)

        # Filter outlier prices (totals confused with unit prices)
        if is_price_outlier(unit_price, label, category):
            outlier_count += 1
            continue

        pd = product_data[pid]
        if ref:
            pd["refs"].add(ref)
        if label:
            pd["labels"].add(label)
        if line["line_desc"]:
            pd["descriptions"].add(line["line_desc"].split("\n")[0][:200])

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

        # Track supplier activity
        supplier_products[line["supplier_name"]].add(pid)
        if line["supplier_name"] not in active_suppliers:
            active_suppliers[line["supplier_name"]] = {
                "name": line["supplier_name"],
                "address": line["supplier_address"],
                "phone": line["supplier_phone"],
                "nit": line["supplier_nit"],
            }

    print(f"  {len(product_data)} productos unicos con compras reales")
    print(f"  {excluded_count} lineas excluidas (no construccion)")
    print(f"  {outlier_count} lineas excluidas (precio outlier)")
    print(f"  {len(active_suppliers)} proveedores con ventas")

    # ── Step 5: Curate products ──────────────────────────────
    print("\n[5/6] Curando productos...")

    curated_products = []
    review_products = []
    category_counts = Counter()
    uncategorized = []

    for pid, data in product_data.items():
        # Pick best label
        labels = list(data["labels"])
        label = max(labels, key=len) if labels else ""
        if not label:
            continue

        refs = list(data["refs"])
        ref = refs[0] if refs else ""

        # Clean prices (remove outliers)
        clean_prices = filter_outlier_prices(data["prices"])
        if not clean_prices:
            clean_prices = data["prices"]

        median_price = round(median(clean_prices), 2) if clean_prices else None

        # Categorize
        category = infer_category(label, ref)
        # Also check descriptions
        if not category and data["descriptions"]:
            for desc in data["descriptions"]:
                category = infer_category(desc)
                if category:
                    break

        # Infer UOM
        uom = infer_uom(label, ref)

        # Build product record
        product = {
            "name": label,
            "code": ref,
            "uom": uom,
            "category": category,
            "ref_price": median_price,
            "ref_currency": "BOB",
            "description": list(data["descriptions"])[0] if data["descriptions"] else "",
            "order_count": data["order_count"],
            "supplier_count": len(data["suppliers"]),
        }

        # Decide: curated vs review
        # Confident if: has category AND has >1 purchase AND median price makes sense
        if category and data["order_count"] >= 1 and median_price and median_price > 0:
            curated_products.append(product)
            category_counts[category] += 1
        else:
            product["_reason"] = []
            if not category:
                product["_reason"].append("sin_categoria")
            if not median_price or median_price <= 0:
                product["_reason"].append("sin_precio")
            if data["order_count"] < 1:
                product["_reason"].append("pocas_compras")
            review_products.append(product)

    # Sort curated by category then name
    curated_products.sort(key=lambda p: (p["category"] or "zzz", p["name"]))

    print(f"  {len(curated_products)} productos curados (listos para subir)")
    print(f"  {len(review_products)} productos para revision manual")
    print(f"\n  Categorias:")
    for cat, count in category_counts.most_common():
        print(f"    {cat}: {count}")

    # ── Step 6: Curate suppliers ─────────────────────────────
    print("\n[6/6] Curando proveedores...")

    # Only suppliers that sold construction materials (in curated products)
    curated_product_suppliers = set()
    for p in curated_products:
        pid_for_product = None
        for pid, data in product_data.items():
            if max(data["labels"], key=len) if data["labels"] else "" == p["name"]:
                curated_product_suppliers |= data["suppliers"]
                break

    curated_suppliers = []
    seen_names = set()

    for sup_name, sup_info in active_suppliers.items():
        # Deduplicate by normalized name
        name_norm = normalize(sup_name)
        if name_norm in seen_names:
            continue
        seen_names.add(name_norm)

        # Enrich from supplier catalog
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

        # Clean phone
        whatsapp = clean_phone(enriched.get("phone", ""))

        # Infer department
        department = infer_department(enriched.get("address", ""), enriched.get("phone", ""))

        # Infer categories from products sold
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

        supplier = {
            "name": sup_name,
            "whatsapp": whatsapp or "0000000000",
            "city": enriched.get("city") or department,
            "department": department,
            "categories": sorted(sup_categories) if sup_categories else [],
            "verification_state": "verified",
        }
        if enriched.get("phone"):
            supplier["phone"] = clean_phone(enriched["phone"])
        if enriched.get("email"):
            supplier["email"] = enriched["email"]
        if enriched.get("nit"):
            supplier["nit"] = enriched["nit"]
        if enriched.get("address"):
            supplier["address"] = enriched["address"]

        curated_suppliers.append(supplier)

    curated_suppliers.sort(key=lambda s: s["name"])
    print(f"  {len(curated_suppliers)} proveedores curados")

    # ── Build price history ──────────────────────────────────
    print("\nGenerando historial de precios...")
    price_history = []
    for pid, data in product_data.items():
        labels = list(data["labels"])
        label = max(labels, key=len) if labels else ""
        if not label:
            continue

        # Only for curated products
        is_curated = any(p["name"] == label for p in curated_products)
        if not is_curated:
            continue

        for rec in data["price_records"]:
            price_history.append({
                "product_name": label,
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

    with open(DATA_DIR / "curated_suppliers.json", "w", encoding="utf-8") as f:
        json.dump(curated_suppliers, f, ensure_ascii=False, indent=2)
    print(f"  curated_suppliers.json: {len(curated_suppliers)} proveedores")

    with open(DATA_DIR / "curated_products.json", "w", encoding="utf-8") as f:
        json.dump(curated_products, f, ensure_ascii=False, indent=2)
    print(f"  curated_products.json: {len(curated_products)} productos")

    with open(DATA_DIR / "curated_prices.json", "w", encoding="utf-8") as f:
        json.dump(price_history, f, ensure_ascii=False, indent=2)
    print(f"  curated_prices.json: {len(price_history)} registros de precio")

    with open(DATA_DIR / "curated_review.json", "w", encoding="utf-8") as f:
        json.dump(review_products, f, ensure_ascii=False, indent=2)
    print(f"  curated_review.json: {len(review_products)} items para revision")

    # ── Report ───────────────────────────────────────────────
    report_lines = [
        "=" * 60,
        "REPORTE DE CURACION v2",
        "=" * 60,
        "",
        f"Fuentes:",
        f"  Pedidos: {len(pedidos_lines)} lineas ({len(product_lines)} productos, {len(pedidos_lines) - len(product_lines)} servicios)",
        f"  Catalogo productos: {len(product_catalog)}",
        f"  Catalogo proveedores: {len(supplier_catalog)}",
        "",
        f"Resultados:",
        f"  Productos curados: {len(curated_products)}",
        f"  Productos para revision: {len(review_products)}",
        f"  Proveedores curados: {len(curated_suppliers)}",
        f"  Registros de precio: {len(price_history)}",
        "",
        "Categorias:",
    ]
    for cat, count in category_counts.most_common():
        report_lines.append(f"  {cat}: {count}")

    report_lines.extend([
        "",
        "Top 20 productos por frecuencia de compra:",
    ])
    top_products = sorted(curated_products, key=lambda p: p["order_count"], reverse=True)[:20]
    for p in top_products:
        report_lines.append(
            f"  {p['name'][:45]:45s}  x{p['order_count']:4d}  {p['ref_price']:>10.2f} Bs/{p['uom']}"
        )

    report_lines.extend([
        "",
        "Productos sin categoria (revision manual):",
        f"  Total: {len([p for p in review_products if 'sin_categoria' in p.get('_reason', [])])}",
    ])

    report_text = "\n".join(report_lines)
    with open(DATA_DIR / "curated_report.txt", "w", encoding="utf-8") as f:
        f.write(report_text)

    print("\n" + report_text)
    print("\nCuracion completada!")


if __name__ == "__main__":
    main()

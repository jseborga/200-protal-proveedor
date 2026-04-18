"""Re-mapea mkt_supplier.categories segun la informacion disponible de cada proveedor.

Fuentes por supplier (en orden de confianza):
  1. Categorias distintas de sus productos en mkt_insumo (via price_history)
  2. Rubros declarados (mkt_supplier_rubro.rubro + .description)
  3. Nombre + descripcion del supplier
  4. Ciudad / direccion como hint

Aplica reglas de keywords contra el texto agregado y devuelve el set de
categorias canonicas. Hace PUT solo si el nuevo set difiere del actual.

Uso: python scripts/remap_supplier_categories.py [--dry-run]
"""
import json
import os
import re
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx

API_BASE = os.environ.get("APU_API_BASE", "https://apu-marketplace-app.q8waob.easypanel.host")
API_KEY = os.environ.get("APU_API_KEY", "mkt_z3dccrUc8-ZyCyaYPkEUMNy6WOwt8muzvRR-E3iM9vs")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
BASE = Path(__file__).resolve().parent.parent
LOG = BASE / "data" / "remap_supplier_categories_log.json"
DRY_RUN = "--dry-run" in sys.argv

# Canonical category keys
CANONICAL = {
    "cemento", "acero", "agregados", "ladrillos", "hormigon", "prefabricados",
    "madera", "techos", "pisos", "ceramica", "vidrios", "pinturas", "adhesivos",
    "impermeabilizantes", "aislantes", "plomeria", "sanitario", "gas", "hvac",
    "electrico", "iluminacion", "redes_datos", "ferreteria", "fijaciones",
    "herramientas", "maquinaria", "equipos", "mano_obra", "seguridad",
    "quimicos_concreto", "quimicos_agua", "jardineria", "urbanismo", "varios",
}

# Legacy keys → canonical mapping (mantenemos categorias existentes sin romper)
LEGACY_MAP = {
    "pintura": "pinturas",
    "maquinarias": "maquinaria",
    "equipo": "equipos",
    "mano de obra": "mano_obra",
    "redes": "redes_datos",
    "climatizacion": "hvac",
    "ferreteria_general": "ferreteria",
}

# Keyword → set de categorias canonicas. El texto normalizado se escanea entero.
RULES: list[tuple[str, list[str]]] = [
    # Ceramica / revestimientos
    (r"\bcerami|porcelanato|azulejo|gres\b", ["ceramica"]),
    # Cemento
    (r"\bcemento|soboce|fancesa|itacamba\b", ["cemento"]),
    # Acero / hierros / estructuras
    (r"\bacero|hierro|perfil|viga|varilla|corrug|galvani|barra\b", ["acero"]),
    # Agregados
    (r"\barena|grava|ripio|canto rodado|piedra|agregado\b", ["agregados"]),
    # Ladrillos
    (r"\bladrill|teja|adoquin|bloque\b", ["ladrillos"]),
    # Hormigon / premezclado
    (r"\bhormig[oó]n|premezclad|concreto premez\b", ["hormigon"]),
    # Prefabricados
    (r"\bprefabric|premoldead|panelit\b", ["prefabricados"]),
    # Madera
    (r"\bmadera|aserrad|parquet|maderera|tableros\b", ["madera", "pisos"]),
    # Techos
    (r"\btecho|cubiert|calamin|teja|policarbon\b", ["techos"]),
    # Pisos
    (r"\bpiso|parquet|vinil|alfombr|flotante|laminado\b", ["pisos"]),
    # Vidrios / aluminio
    (r"\bvidrio|crist|aluminio|ventana|mampar\b", ["vidrios"]),
    # Pinturas
    (r"\bpintur|monopol|sherwin|barniz|esmalte|latex\b", ["pinturas"]),
    # Adhesivos / selladores
    (r"\badhesiv|sellador|silicona|pegamento|cola|poxipol\b", ["adhesivos"]),
    # Impermeabilizantes
    (r"\bimpermeabil|membrana asfalt|hidrofug\b", ["impermeabilizantes"]),
    # Aislantes
    (r"\baislant|lana de vidrio|poliester|espuma pu\b", ["aislantes"]),
    # Plomeria
    (r"\bplomer|tuberi|tuber[ií]a|tigre|cpvc|pex\b", ["plomeria"]),
    # Sanitario
    (r"\bsanitari|inodor|lavaman|griferi|duch\b", ["sanitario"]),
    # Gas
    (r"\bgas natural|gnv|gas licuado|glp|conexion gas\b", ["gas"]),
    # HVAC
    (r"\baire acondicionad|climatizac|ventilaci|extractor|split\b", ["hvac"]),
    # Electrico
    (r"\bel[eé]ctric|cable|cablead|electricidad|tablero|breaker|interruptor\b", ["electrico"]),
    # Iluminacion
    (r"\biluminaci|l[aá]mpar|luminari|foco|led\b", ["iluminacion"]),
    # Redes / datos
    (r"\bred de datos|cableado estructurad|fibra [oó]ptic|cat6|utp\b", ["redes_datos"]),
    # Ferreteria
    (r"\bferreteri|tornill|perno|clavo\b", ["ferreteria", "fijaciones"]),
    # Fijaciones
    (r"\btornil|perno|tuerca|arandela|anclaje|taco\b", ["fijaciones"]),
    # Herramientas
    (r"\bherramient|taladro|amoladora|sierra\b", ["herramientas"]),
    # Maquinaria
    (r"\bmaquinari|retroexcavad|volquet|motonivel|excavador|tractor\b", ["maquinaria"]),
    # Equipos (mas generico: rental / alquiler)
    (r"\balquiler de equip|renta de equip|equipos de construc\b", ["equipos", "maquinaria"]),
    # Mano de obra / servicios
    (r"\bmano de obra|servicio de albañ|construc civil|subcontrat\b", ["mano_obra"]),
    # Seguridad
    (r"\bseguridad industri|epp|casco|guante|arn[eé]s|chaleco\b", ["seguridad"]),
    # Quimicos
    (r"\baditiv|sika|acelerant|retardant|plastific\b", ["quimicos_concreto"]),
    (r"\bqu[ií]mic.*agua|tratamiento de agua|cloro|sulfato\b", ["quimicos_agua"]),
    # Jardineria
    (r"\bjardiner|vivero|planta|semilla|cesped\b", ["jardineria"]),
    # Urbanismo
    (r"\burbanismo|se[nñ]aliz|vialidad|asfalto|pavimento\b", ["urbanismo"]),
]


def normalize(text: str) -> str:
    if not text:
        return ""
    return text.lower().strip()


def infer_from_text(text: str) -> set[str]:
    t = normalize(text)
    out: set[str] = set()
    for pattern, cats in RULES:
        if re.search(pattern, t):
            out.update(cats)
    return out


def canonize(existing: list[str] | None) -> set[str]:
    out: set[str] = set()
    for c in (existing or []):
        k = normalize(c)
        k = LEGACY_MAP.get(k, k)
        if k in CANONICAL:
            out.add(k)
    return out


def list_suppliers(client: httpx.Client) -> list[dict]:
    all_s: list[dict] = []
    offset = 0
    while True:
        r = client.get(f"{API_BASE}/api/v1/integration/suppliers",
                       params={"offset": offset, "limit": 500}, timeout=60)
        r.raise_for_status()
        d = r.json()
        batch = d.get("data", [])
        all_s.extend(batch)
        total = d.get("total", 0)
        offset += len(batch)
        if not batch or offset >= total:
            break
    return all_s


def get_rubros(client: httpx.Client, supplier_id: int) -> list[dict]:
    r = client.get(f"{API_BASE}/api/v1/integration/supplier-rubros/{supplier_id}", timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("data", [])


def apu_product_categories(client: httpx.Client) -> set[str]:
    """APU Ingenieria (3525) es el unico supplier con productos importados,
    por lo que las categorias de mkt_insumo representan su portafolio."""
    r = client.get(f"{API_BASE}/api/v1/prices/categories/list", timeout=30)
    if r.status_code != 200:
        return set()
    data = r.json().get("data") or []
    return {c["name"] for c in data if c.get("name") in CANONICAL}


def update_supplier_categories(client: httpx.Client, sid: int, categories: list[str]) -> dict:
    r = client.put(f"{API_BASE}/api/v1/integration/suppliers/{sid}",
                   json={"categories": categories}, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    print(f"[mode] {'DRY-RUN' if DRY_RUN else 'LIVE'}")
    with httpx.Client(headers=HEADERS) as client:
        suppliers = list_suppliers(client)
        print(f"[suppliers] total {len(suppliers)}")

        apu_cats = apu_product_categories(client) if not DRY_RUN or True else set()
        print(f"[apu 3525 product cats] {sorted(apu_cats)}")

        log = {"dry_run": DRY_RUN, "changes": [], "unchanged": 0, "errors": []}
        for s in suppliers:
            sid = s["id"]
            current = canonize(s.get("categories") or [])
            text_blob = " ".join([s.get("name", ""), s.get("description") or "", s.get("trade_name") or ""])
            try:
                rubros = get_rubros(client, sid)
            except Exception as e:
                rubros = []
                log["errors"].append({"supplier_id": sid, "stage": "rubros", "error": str(e)})
            for r in rubros:
                text_blob += f" {r.get('rubro') or ''} {r.get('description') or ''}"

            inferred = infer_from_text(text_blob)

            # APU Ingenieria (3525): agregar todas las cats de sus productos
            if sid == 3525:
                inferred |= apu_cats

            new_set = current | inferred
            new_set = {c for c in new_set if c in CANONICAL}

            if new_set == current or not new_set:
                log["unchanged"] += 1
                continue

            added = sorted(new_set - current)
            entry = {
                "supplier_id": sid,
                "name": s.get("name"),
                "before": sorted(current),
                "after": sorted(new_set),
                "added": added,
            }
            log["changes"].append(entry)
            print(f"  [{sid}] {s.get('name')[:40]:40s}  +{added}")

            if not DRY_RUN:
                try:
                    update_supplier_categories(client, sid, sorted(new_set))
                except Exception as e:
                    log["errors"].append({"supplier_id": sid, "stage": "update", "error": str(e)})

        print(f"\n[summary] changed={len(log['changes'])} unchanged={log['unchanged']} errors={len(log['errors'])}")
        LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[log] {LOG}")


if __name__ == "__main__":
    main()

"""
Normalizacion de nombres de productos - Paso 2 del curado.

Lee curated_ai_normalize.json (items con nombres pobres) y:
1. Aplica reglas deterministicas para casos obvios
2. Opcionalmente usa IA (OpenRouter) para los ambiguos

Uso:
    python scripts/ai_normalize.py              # solo reglas
    python scripts/ai_normalize.py --ai         # reglas + IA

Genera:
    data/curated_products.json  (actualizado con nombres normalizados)
"""

import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# ── Reglas deterministicas de normalizacion ──────────────────
DETERMINISTIC_FIXES = {
    # Nombres genericos que estan bien como estan (no cambiar)
    "Anclaje": None,  # None = mantener como esta
    "Bisagra": None,
    "Tuerca": None,
    "Pernos": None,
    "Pala": None,
    "DUCHA": "Ducha",  # solo title case
    "GRIFO": "Grifo",
    "SIFON": "Sifon",
    "FOCO": "Foco",
    "GRAVA": "Grava",
    "GRUA": "Grua",
    "Barras": "Barras de acero",
    "Mezcladora": "Mezcladora de concreto",
    "Porcelanato": "Porcelanato",
    "Pintura": "Pintura",
    "Agregados": "Agregados",
}

def apply_deterministic_rules(item):
    """Aplica reglas fijas para normalizar nombres obvios."""
    name = item["current_name"]

    # 1. Fix en el dict de fixes
    if name in DETERMINISTIC_FIXES:
        fixed = DETERMINISTIC_FIXES[name]
        return fixed if fixed else name  # None = mantener

    # 2. Dimension de madera: "1x35x3" -> "Madera 1x35x3"
    if re.match(r'^\d+[xX]\d+[xX]?\d*', name) and item.get("category") == "madera":
        # Normalizar formato: "1x35x350" -> "1x35x3.50" si parece cm
        dim = name.strip()
        return f"Madera {dim}"

    # 3. Dimension con texto: "2x3x4 mt" -> "Madera 2x3x4m"
    match = re.match(r'^(\d+[xX]\d+[xX]?\d*)\s*(mt|m|metros?)?$', name, re.IGNORECASE)
    if match and item.get("category") == "madera":
        return f"Madera {match.group(1)}"

    return name


def normalize_with_ai(items, api_key, model="anthropic/claude-3-haiku"):
    """Usa OpenRouter para normalizar nombres ambiguos."""
    try:
        import urllib.request
    except ImportError:
        print("  ERROR: urllib no disponible")
        return {}

    prompt = """Eres un experto en materiales de construccion en Bolivia.
Te doy una lista de productos con nombres pobres. Para cada uno, sugiere un nombre
estandarizado, claro y especifico para un catalogo de materiales de construccion.

Reglas:
- Usa espanol, primera letra mayuscula
- Incluye especificaciones si las puedes inferir (dimensiones, tipo, marca)
- Si el nombre ya es correcto, devuelvelo tal cual
- No inventes datos que no estan en la info dada

Responde SOLO en formato JSON: {"items": [{"original": "...", "normalized": "..."}]}

Items a normalizar:
"""
    for item in items:
        prompt += f'\n- nombre="{item["current_name"]}", categoria={item["category"]}, precio={item["ref_price"]} {item["uom"]}, desc="{item.get("description","")}"'

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2000,
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]

        # Extraer JSON de la respuesta
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            return {item["original"]: item["normalized"] for item in result.get("items", [])}
    except Exception as e:
        print(f"  ERROR IA: {e}")

    return {}


def main():
    use_ai = "--ai" in sys.argv

    print("=" * 60)
    print("NORMALIZACION DE NOMBRES - APU Marketplace")
    print("=" * 60)

    # Load data
    with open(DATA_DIR / "curated_ai_normalize.json", "r", encoding="utf-8") as f:
        ai_items = json.load(f)

    with open(DATA_DIR / "curated_products.json", "r", encoding="utf-8") as f:
        products = json.load(f)

    print(f"\n{len(ai_items)} items para normalizar")

    # Step 1: Deterministic fixes
    print("\n[1/2] Aplicando reglas deterministicas...")
    changes = {}
    remaining = []

    for item in ai_items:
        fixed = apply_deterministic_rules(item)
        if fixed != item["current_name"]:
            changes[item["current_name"]] = fixed
            print(f'  "{item["current_name"]}" -> "{fixed}"')
        else:
            remaining.append(item)
            print(f'  "{item["current_name"]}" -> (sin cambio)')

    print(f"\n  {len(changes)} nombres corregidos, {len(remaining)} sin cambio")

    # Step 2: AI (optional)
    if use_ai and remaining:
        print("\n[2/2] Normalizando con IA...")

        # Try to get API key
        api_key = os.environ.get("AI_API_KEY", "")
        if not api_key:
            env_file = BASE_DIR / ".env"
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").split("\n"):
                    if line.startswith("AI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"')
                        break

        if not api_key:
            print("  WARN: No AI_API_KEY encontrada. Saltando IA.")
        else:
            ai_model = os.environ.get("AI_MODEL", "anthropic/claude-3-haiku")
            ai_changes = normalize_with_ai(remaining, api_key, ai_model)
            changes.update(ai_changes)
            for orig, fixed in ai_changes.items():
                print(f'  [IA] "{orig}" -> "{fixed}"')
            print(f"  {len(ai_changes)} nombres normalizados con IA")
    elif use_ai:
        print("\n[2/2] No hay items restantes para IA.")
    else:
        print("\n[2/2] IA deshabilitada (usar --ai para habilitar)")

    # Apply changes to products
    if changes:
        print(f"\nAplicando {len(changes)} cambios a curated_products.json...")
        updated = 0
        for p in products:
            if p["name"] in changes:
                old = p["name"]
                p["name"] = changes[old]
                updated += 1

        with open(DATA_DIR / "curated_products.json", "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        print(f"  {updated} productos actualizados")

        # Also update price history product names
        prices_file = DATA_DIR / "curated_prices.json"
        if prices_file.exists():
            with open(prices_file, "r", encoding="utf-8") as f:
                prices = json.load(f)
            price_updated = 0
            for p in prices:
                if p["product_name"] in changes:
                    p["product_name"] = changes[p["product_name"]]
                    price_updated += 1
            with open(prices_file, "w", encoding="utf-8") as f:
                json.dump(prices, f, ensure_ascii=False, indent=2)
            print(f"  {price_updated} registros de precio actualizados")
    else:
        print("\nSin cambios que aplicar.")

    print("\nNormalizacion completada!")


if __name__ == "__main__":
    main()

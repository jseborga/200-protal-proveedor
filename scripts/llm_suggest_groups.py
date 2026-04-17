"""Sugerir agrupaciones de productos (familias + variantes) usando LLM via OpenRouter.

Lee todos los insumos del catalogo via /prices/public, los envia en batches al LLM
agrupando por categoria, y produce un JSON de propuestas para revision manual.

Flujo recomendado:
    1. python scripts/llm_suggest_groups.py
    2. Revisar data/group_suggestions.json (editar / remover grupos no deseados)
    3. python scripts/apply_group_suggestions.py

Uso:
    python scripts/llm_suggest_groups.py
    python scripts/llm_suggest_groups.py --api=http://localhost:8000
    python scripts/llm_suggest_groups.py --model=anthropic/claude-sonnet-4
    python scripts/llm_suggest_groups.py --batch=25

Requiere AI_API_KEY en .env o env var (OpenRouter key).
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DEFAULT_API = "https://apu-marketplace-app.q8waob.easypanel.host"
DEFAULT_MODEL = "google/gemini-2.5-flash-preview-05-20"
DEFAULT_BATCH = 30
OUT_FILE = DATA_DIR / "group_suggestions.json"

SYSTEM_PROMPT = """Eres un experto en materiales de construccion en Bolivia.

Tu tarea: analizar una lista de productos y agruparlos en FAMILIAS cuando corresponda.

Reglas criticas:
- Un grupo es una familia donde los miembros solo difieren en UNA variante (diametro, medida, color, capacidad, presentacion, espesor).
- Agrupa sinonimos que son el MISMO material: fierro = hierro = acero corrugado; fierro liso = acero liso; cemento = cemento portland.
- Solo crea un grupo si tiene 2+ miembros.
- NO agrupes productos de categorias diferentes.
- NO agrupes si las variantes no son comparables (ej: "fierro liso" y "fierro corrugado" son grupos distintos).
- Productos unicos NO deben agruparse.
- El nombre del grupo debe ser claro y general (sin dimensiones). Ej: "Fierro de construccion (acero corrugado)".

Variantes validas (usa exactamente uno): Diametro, Medida, Capacidad, Color, Presentacion, Espesor, Tipo, Longitud.

Devuelve SOLO JSON valido (sin texto adicional) con esta estructura:
{
  "groups": [
    {
      "name": "Fierro de construccion (acero corrugado)",
      "category": "acero",
      "variant_label": "Diametro",
      "reasoning": "Todos son fierro corrugado en distintos diametros",
      "member_ids": [12, 15, 23]
    }
  ]
}

Si ningun grupo aplica al batch, devuelve {"groups": []}."""


def parse_args():
    cfg = {"api": DEFAULT_API, "model": DEFAULT_MODEL, "batch": DEFAULT_BATCH}
    for a in sys.argv[1:]:
        if a.startswith("--api="):
            cfg["api"] = a.split("=", 1)[1].rstrip("/")
        elif a.startswith("--model="):
            cfg["model"] = a.split("=", 1)[1]
        elif a.startswith("--batch="):
            cfg["batch"] = int(a.split("=", 1)[1])
    return cfg


def load_api_key():
    key = os.environ.get("AI_API_KEY", "").strip()
    if key:
        return key
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("AI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def fetch_all_insumos(api_url):
    print(f"Descargando productos de {api_url}...")
    items = []
    offset = 0
    page_size = 50
    while True:
        url = f"{api_url}/api/v1/prices/public?limit={page_size}&offset={offset}"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            print(f"  ERROR HTTP {e.code}: {e.reason}")
            break
        except Exception as e:
            print(f"  ERROR: {e}")
            break
        if not data.get("ok"):
            break
        batch = data.get("data", [])
        if not batch:
            break
        items.extend(batch)
        total = data.get("total", "?")
        print(f"  +{len(batch)} (total acumulado: {len(items)} / {total})")
        if len(batch) < page_size:
            break
        offset += page_size
        time.sleep(0.2)
    return items


def call_llm(items, api_key, model):
    items_text = "\n".join(
        f"  id={i['id']} | name='{i['name']}' | uom={i['uom']} | "
        f"category={i.get('category') or '-'} | ref_price={i.get('ref_price') or '-'}"
        for i in items
    )
    user_msg = f"Productos a analizar:\n{items_text}\n\nDevuelve el JSON con grupos."

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://apu-marketplace-app.q8waob.easypanel.host",
            "X-Title": "Nexo Base Group Suggester",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"  ERROR HTTP {e.code}: {body[:300]}")
        return []
    except Exception as e:
        print(f"  ERROR: {e}")
        return []

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    m = re.search(r'\{[\s\S]*\}', content)
    if not m:
        print("  WARN: respuesta sin JSON valido")
        return []
    try:
        parsed = json.loads(m.group())
    except json.JSONDecodeError as e:
        print(f"  WARN: JSON invalido ({e})")
        return []
    return parsed.get("groups", [])


def main():
    cfg = parse_args()
    api_key = load_api_key()
    if not api_key:
        print("ERROR: AI_API_KEY no encontrada. Definir en .env o como env var.")
        sys.exit(1)

    items = fetch_all_insumos(cfg["api"])
    if not items:
        print("No hay productos para analizar.")
        sys.exit(1)
    print(f"\n{len(items)} productos cargados. Modelo: {cfg['model']}\n")

    by_cat = defaultdict(list)
    for it in items:
        by_cat[it.get("category") or "sin_categoria"].append(it)

    all_groups = []
    for cat, lst in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        print(f"[{cat}] {len(lst)} items")
        for i in range(0, len(lst), cfg["batch"]):
            batch = lst[i:i + cfg["batch"]]
            print(f"  batch {i}..{i + len(batch)} ({len(batch)} items)", end=" ", flush=True)
            t0 = time.time()
            groups = call_llm(batch, api_key, cfg["model"])
            dt = time.time() - t0
            print(f"-> {len(groups)} grupos ({dt:.1f}s)")

            id_to_item = {x["id"]: x for x in batch}
            for g in groups:
                mids = [mid for mid in g.get("member_ids", []) if mid in id_to_item]
                if len(mids) < 2:
                    continue
                g["member_ids"] = mids
                g["members"] = [
                    {
                        "id": mid,
                        "name": id_to_item[mid]["name"],
                        "uom": id_to_item[mid]["uom"],
                        "ref_price": id_to_item[mid].get("ref_price"),
                    }
                    for mid in mids
                ]
                all_groups.append(g)
            time.sleep(0.5)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model": cfg["model"],
                "total_items": len(items),
                "total_groups": len(all_groups),
                "groups": all_groups,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    total_members = sum(len(g["members"]) for g in all_groups)
    print(f"\n{'=' * 60}")
    print(f"OK: {len(all_groups)} grupos sugeridos cubren {total_members} items")
    print(f"Archivo: {OUT_FILE}")
    print(f"{'=' * 60}")
    print("\nSiguiente paso: revisar el JSON y ajustar (remover / renombrar)")
    print("Luego: python scripts/apply_group_suggestions.py")


if __name__ == "__main__":
    main()

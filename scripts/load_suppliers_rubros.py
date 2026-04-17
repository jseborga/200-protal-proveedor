"""Carga de proveedores con rubros desde datasets curados.

Ejecutar: python scripts/load_suppliers_rubros.py
Requiere: APP_URL y API_KEY (o usa defaults de produccion)
"""

import httpx
import os

APP_URL = os.getenv("APP_URL", "https://apu-marketplace-app.q8waob.easypanel.host")
API_KEY = os.getenv("API_KEY", "mkt_z3dccrUc8-ZyCyaYPkEUMNy6WOwt8muzvRR-E3iM9vs")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# ── Dataset 1: Proveedores (info contacto) ────────────────────
SUPPLIERS = [
    {
        "id": 1, "name": "Acermax", "categories": ["acero", "techos"],
        "operating_cities": ["LPZ", "EL ALTO", "SCZ"],
        "phone": "+591 67007501", "phone2": "+591 2 2830778",
        "email": "info@acermax.com.bo", "website": "www.acermax.com.bo",
        "description": "Fabrica de calaminas plana/ondulada/trapezoidal, teja americana/colonial/espanola, cumbreras; corte, plegado y cilindrado de planchas de acero",
    },
    {
        "id": 2, "name": "Aceros Arequipa", "categories": ["acero", "ferreteria"],
        "operating_cities": ["SCZ", "LPZ", "CBBA", "EL ALTO"],
        "phone": "+591 76303499", "phone2": "+591 77641656",
        "email": None, "website": None,
        "description": "Produccion de acero de construccion, estribos corrugados, clavos, alambres, conectores mecanicos, mallas electrosoldadas, perfiles, planchas y tubos",
    },
    {
        "id": 3, "name": "Aceros Torrico", "categories": ["acero", "techos"],
        "operating_cities": ["LPZ", "SCZ", "CBBA"],
        "phone": "+591 78970158", "phone2": "+591 78504206",
        "email": None, "website": "www.acerostorrico.com",
        "description": "Fabrica calaminas zinc-alum y pre-pintadas, perfiles C y U, pernos auto-perforantes, clavos galvanizados, sistema K-span/Arcotecho",
    },
    {
        "id": 4, "name": "Acustica.bo", "categories": ["aislantes"],
        "operating_cities": ["SCZ"],
        "phone": "+591 69830577", "phone2": None,
        "email": "contacto@acustica.bo", "website": "www.acustica.bo",
        "description": "Soluciones acusticas para viviendas, oficinas, industrias y espacios multiples",
    },
    {
        "id": 5, "name": "Ayudante de tu Hogar", "categories": ["herramientas"],
        "operating_cities": ["NACIONAL"],
        "phone": "+591 75221344", "phone2": None,
        "email": "contacto@ayudantedetuhogar.com", "website": "www.ayudantedetuhogar.com",
        "description": "Plataforma/app que conecta expertos con clientes para servicios del hogar, mantenimiento y reparacion de electrodomesticos",
    },
    {
        "id": 6, "name": "Bacheo.com.bo", "categories": ["agregados"],
        "operating_cities": ["LPZ", "SCZ"],
        "phone": "+591 2 2118292", "phone2": "+591 72072067",
        "email": None, "website": "www.bacheo.com.bo",
        "description": "Asfalto frio EZ Street para mantenimiento vial, canchas deportivas, garajes y parqueos",
    },
]

# ── Dataset 2: Rubros por proveedor ───────────────────────────
RUBROS = [
    {"supplier_id": 1, "rubro": "Calaminas", "category_key": "techos",
     "description": "Calamina plana, ondulada, rectangular, trapezoidal y trapezoidal alto; teja americana, colonial y espanola; cumbreras"},
    {"supplier_id": 1, "rubro": "Metalmecanica", "category_key": "acero",
     "description": "Corte, plegado y cilindrado de planchas de acero"},
    {"supplier_id": 2, "rubro": "Acero de construccion", "category_key": "acero",
     "description": "Acero corrugado, estribos, clavos, alambres, conectores mecanicos"},
    {"supplier_id": 2, "rubro": "Mallas / Perfiles", "category_key": "acero",
     "description": "Mallas electrosoldadas, perfiles de acero, planchas y tubos"},
    {"supplier_id": 3, "rubro": "Calaminas", "category_key": "techos",
     "description": "Calaminas zinc-alum, pre-pintadas, corrugadas; teja americana/colonial"},
]


def _city_to_dept(city: str) -> str:
    """Map city abbreviation to department."""
    mapping = {
        "LPZ": "La Paz", "EL ALTO": "La Paz", "SCZ": "Santa Cruz",
        "CBBA": "Cochabamba", "ORU": "Oruro", "SUC": "Chuquisaca",
        "TJA": "Tarija", "PTI": "Potosi", "BEN": "Beni", "PAN": "Pando",
        "NACIONAL": "Nacional",
    }
    return mapping.get(city.upper(), city)


def main():
    print(f"Cargando proveedores a {APP_URL}...")

    # Step 1: Create suppliers via integration API (all fields supported now)
    created = 0
    supplier_id_map = {}  # local_id → server_id

    for s in SUPPLIERS:
        local_id = s["id"]
        payload = {
            "name": s["name"],
            "categories": s.get("categories", []),
            "city": s["operating_cities"][0] if s.get("operating_cities") else None,
            "department": _city_to_dept(s["operating_cities"][0]) if s.get("operating_cities") else None,
            "phone": s.get("phone"),
            "phone2": s.get("phone2"),
            "email": s.get("email"),
            "website": s.get("website"),
            "description": s.get("description"),
            "operating_cities": s.get("operating_cities"),
            "country": "BO",
        }

        resp = httpx.post(f"{APP_URL}/api/v1/integration/suppliers", json=payload, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                server_id = data["data"]["id"]
                supplier_id_map[local_id] = server_id
                created += 1
                print(f"  + {s['name']} (id={server_id})")
            else:
                print(f"  ! {s['name']}: {data.get('error', 'unknown error')}")
        else:
            print(f"  ! {s['name']}: HTTP {resp.status_code} — {resp.text[:100]}")

    print(f"\nProveedores creados: {created}/{len(SUPPLIERS)}")

    # Step 2: Create rubros
    rubros_created = 0
    for r in RUBROS:
        server_sid = supplier_id_map.get(r["supplier_id"])
        if not server_sid:
            print(f"  ! Rubro '{r['rubro']}': supplier_id {r['supplier_id']} not found")
            continue

        payload = {
            "supplier_id": server_sid,
            "rubro": r["rubro"],
            "description": r.get("description", ""),
            "category_key": r.get("category_key", ""),
        }
        resp = httpx.post(f"{APP_URL}/api/v1/integration/supplier-rubros", json=payload, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                rubros_created += 1
                print(f"  + {r['rubro']} -> supplier {server_sid}")
            else:
                print(f"  ! {r['rubro']}: {data.get('error', 'unknown error')}")
        else:
            print(f"  ! {r['rubro']}: HTTP {resp.status_code} — {resp.text[:100]}")

    print(f"\nRubros creados: {rubros_created}/{len(RUBROS)}")
    print("Done.")


if __name__ == "__main__":
    main()

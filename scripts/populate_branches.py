"""Populate supplier branches for 6 big suppliers via integration API."""
import json
import urllib.error
import urllib.request

API_URL = "https://apu-marketplace-app.q8waob.easypanel.host/api/v1/integration"
API_KEY = "mkt_z3dccrUc8-ZyCyaYPkEUMNy6WOwt8muzvRR-E3iM9vs"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

branches = [
    # ── Hansa (3343) ───────────────────────────────
    {"supplier_id": 3343, "branch_name": "Hansa La Paz", "city": "LPZ", "department": "La Paz",
     "address": "Calle Yanacocha esq. Mercado 1004, Edif. Hansa, La Paz",
     "phone": "+591 2 2407777", "latitude": -16.4970443, "longitude": -68.1359618, "is_main": False},
    {"supplier_id": 3343, "branch_name": "Hansa Santa Cruz", "city": "SCZ", "department": "Santa Cruz",
     "address": "Av. Cristo Redentor 470 entre 2do y 3er anillo, Santa Cruz",
     "phone": "+591 3 2149800", "latitude": -17.7636694, "longitude": -63.1810056, "is_main": False},
    {"supplier_id": 3343, "branch_name": "Hansa Cochabamba", "city": "CBBA", "department": "Cochabamba",
     "address": "Av. Blanco Galindo Km 4.5, Cochabamba",
     "phone": "+591 4 4441824", "latitude": -17.3912537, "longitude": -66.2302035, "is_main": True},

    # ── Monopol (3362) ────────────────────────────
    {"supplier_id": 3362, "branch_name": "Monopol La Paz Villa Fatima", "city": "LPZ", "department": "La Paz",
     "address": "Villa Fatima, Calle Covendo N 1, La Paz",
     "phone": "+591 2 2180222", "latitude": -16.4859, "longitude": -68.1242, "is_main": False},
    {"supplier_id": 3362, "branch_name": "Monopol Santa Cruz Parque Industrial", "city": "SCZ", "department": "Santa Cruz",
     "address": "4to Anillo esq. Av. Brasil, Parque Industrial Liviano, Santa Cruz",
     "phone": "+591 3 3470707", "latitude": -17.7933, "longitude": -63.1669, "is_main": False},
    {"supplier_id": 3362, "branch_name": "Monopol Cochabamba planta", "city": "CBBA", "department": "Cochabamba",
     "address": "Calle Claudio Tolomeo 258 entre Av. Beijing y Grover Suarez, Cochabamba",
     "phone": "+591 4 4432121", "latitude": -17.3953312, "longitude": -66.1860835, "is_main": True},

    # ── Plastiforte (3368) ────────────────────────
    {"supplier_id": 3368, "branch_name": "Plastiforte Cochabamba sede", "city": "CBBA", "department": "Cochabamba",
     "address": "Av. Blanco Galindo Km 3.8 N 3011, Villa Busch, Cochabamba",
     "phone": "+591 4 4433270", "email": "ventas@plastiforte.com",
     "latitude": -17.3930813, "longitude": -66.1944890, "is_main": True},
    {"supplier_id": 3368, "branch_name": "Plastiforte La Paz Obrajes", "city": "LPZ", "department": "La Paz",
     "address": "Av. Hernando Siles 5593 esq. Calle 10 de Obrajes, Edif. Tunupa, Local 4, La Paz",
     "latitude": -16.5266749, "longitude": -68.1072640, "is_main": False},
    {"supplier_id": 3368, "branch_name": "Plastiforte La Paz Rio Seco", "city": "LPZ", "department": "La Paz",
     "address": "Calle Pucara 4227, Urb. Nueva Jerusalen, Rio Seco, El Alto",
     "latitude": -16.4797486, "longitude": -68.1990129, "is_main": False},
    {"supplier_id": 3368, "branch_name": "Plastiforte Santa Cruz", "city": "SCZ", "department": "Santa Cruz",
     "address": "Av. Los Sauces 361 entre Roble y Jorori, Barrio 24 de Septiembre, zona norte 7mo-8vo anillo, Santa Cruz",
     "phone": "+591 3 3425108", "latitude": -17.7821997, "longitude": -63.1815966, "is_main": False},

    # ── Duralit (3331) ────────────────────────────
    {"supplier_id": 3331, "branch_name": "Duralit Cochabamba sede", "city": "CBBA", "department": "Cochabamba",
     "address": "Calle J. Miguel Lanza 205, Zona Florida Norte (Av. Blanco Galindo Km 7.2), Cochabamba",
     "phone": "+591 4 4268311", "email": "cba@duralit.com",
     "latitude": -17.3931718, "longitude": -66.2701944, "is_main": True},
    {"supplier_id": 3331, "branch_name": "Duralit Santa Cruz", "city": "SCZ", "department": "Santa Cruz",
     "address": "Doble Via La Guardia Km 6, Santa Cruz de la Sierra",
     "latitude": -17.8914980, "longitude": -63.3207053, "is_main": False},
    {"supplier_id": 3331, "branch_name": "Duralit La Paz", "city": "LPZ", "department": "La Paz",
     "address": "El Alto, La Paz",
     "latitude": -16.5089596, "longitude": -68.1645465, "is_main": False},

    # ── SOBOCE (3514) ─────────────────────────────
    {"supplier_id": 3514, "branch_name": "SOBOCE La Paz oficina central", "city": "LPZ", "department": "La Paz",
     "address": "Av. Aniceto Arce 2333, Edif. SOBOCE, La Paz",
     "phone": "+591 2 2406040", "latitude": -16.5087250, "longitude": -68.1250079, "is_main": True},
    {"supplier_id": 3514, "branch_name": "SOBOCE Santa Cruz oficina", "city": "SCZ", "department": "Santa Cruz",
     "address": "Equipetrol Norte, Santa Cruz de la Sierra",
     "phone": "+591 3 3449939", "latitude": -17.7573336, "longitude": -63.1960260, "is_main": False},
    {"supplier_id": 3514, "branch_name": "SOBOCE Planta Viacha", "city": "LPZ", "department": "La Paz",
     "address": "Viacha, La Paz (planta cemento)",
     "latitude": -16.6559, "longitude": -68.2967, "is_main": False},
    {"supplier_id": 3514, "branch_name": "SOBOCE Planta Warnes", "city": "SCZ", "department": "Santa Cruz",
     "address": "Parque Industrial Warnes, Santa Cruz",
     "latitude": -17.5075, "longitude": -63.1597, "is_main": False},

    # ── Fancesa (3496) ────────────────────────────
    {"supplier_id": 3496, "branch_name": "Fancesa Agencia 335 Sucre", "city": "SUCRE", "department": "Chuquisaca",
     "address": "Av. Ostria Gutierrez, Sucre",
     "phone": "+591 72861260", "latitude": -19.0405294, "longitude": -65.2508643, "is_main": True},
]


def main():
    created = updated = failed = 0
    for b in branches:
        body = json.dumps(b).encode()
        req = urllib.request.Request(
            f"{API_URL}/supplier-branches",
            data=body, headers=HEADERS, method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=20)
            data = json.loads(resp.read())
            act, bid = data.get("action"), data.get("id")
            if act == "created":
                created += 1
            elif act == "updated":
                updated += 1
            print(f'{b["branch_name"][:42]:42s} {act:8s} id={bid}')
        except urllib.error.HTTPError as e:
            print(f'{b["branch_name"][:42]:42s} HTTP {e.code} {e.read()[:150]!r}')
            failed += 1
        except Exception as e:
            print(f'{b["branch_name"][:42]:42s} ERR {e}')
            failed += 1

    print(f"\nResumen: creadas={created} actualizadas={updated} fallidas={failed}")


if __name__ == "__main__":
    main()

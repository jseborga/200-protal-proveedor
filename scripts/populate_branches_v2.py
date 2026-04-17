"""Populate supplier branches extracted from description paragraphs.

Second batch: Tecnopreco, Acermax, Aceros Arequipa, Faboce, Electrored,
Mamut, Synergy. Branches come from analyzing supplier description text
that lumps multiple branches into one paragraph.
"""
import json
import urllib.error
import urllib.request

API_URL = "https://apu-marketplace-app.q8waob.easypanel.host/api/v1/integration"
API_KEY = "mkt_z3dccrUc8-ZyCyaYPkEUMNy6WOwt8muzvRR-E3iM9vs"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


branches = [
    # ── Tecnopreco (3388) — 4 branches LPZ/El Alto ────────────
    {"supplier_id": 3388, "branch_name": "Tecnopreco Miraflores", "city": "LPZ", "department": "La Paz",
     "address": "Edificio Casso, Miraflores, La Paz",
     "latitude": -16.4969, "longitude": -68.1193, "is_main": True},
    {"supplier_id": 3388, "branch_name": "Tecnopreco Cota Cota", "city": "LPZ", "department": "La Paz",
     "address": "Av. Munoz Reyes N 1210, Edificio Michelle, Cota Cota, La Paz",
     "latitude": -16.5524, "longitude": -68.0666, "is_main": False},
    {"supplier_id": 3388, "branch_name": "Tecnopreco Villa Bolivar B", "city": "LPZ", "department": "La Paz",
     "address": "Av. Ladislao Cabrera N 1080, Villa Bolivar B, Cruce Viacha, El Alto",
     "latitude": -16.5295, "longitude": -68.2124, "is_main": False},
    {"supplier_id": 3388, "branch_name": "Tecnopreco Rio Seco", "city": "EL ALTO", "department": "La Paz",
     "address": "Av. Juan Pablo II N 67, Rio Seco, El Alto",
     "phone": "800162023",
     "latitude": -16.4844, "longitude": -68.2014, "is_main": False},

    # ── Acermax (3314) — 3 branches LPZ/El Alto ───────────────
    {"supplier_id": 3314, "branch_name": "Acermax Oficina La Paz", "city": "LPZ", "department": "La Paz",
     "address": "Calle Hermanos Manchego N 2420, Piso 2, entre Belisario Salinas y Pedro Salazar, La Paz",
     "phone": "+591 77285847",
     "latitude": -16.5085, "longitude": -68.1260, "is_main": True},
    {"supplier_id": 3314, "branch_name": "Acermax Planta El Alto", "city": "EL ALTO", "department": "La Paz",
     "address": "Carretera Viacha Km 6, Zona Acribol, El Alto",
     "phone": "+591 71543559",
     "latitude": -16.5775, "longitude": -68.2385, "is_main": False},
    {"supplier_id": 3314, "branch_name": "Acermax Sucursal Av. 6 de Marzo", "city": "EL ALTO", "department": "La Paz",
     "address": "Av. 6 de Marzo, El Alto",
     "latitude": -16.5263, "longitude": -68.1860, "is_main": False},

    # ── Aceros Arequipa (3315) — 2 branches con direccion ────
    {"supplier_id": 3315, "branch_name": "Aceros Arequipa Santa Cruz", "city": "SCZ", "department": "Santa Cruz",
     "address": "Av. Sexto Anillo 6455, Zona Sur, Santa Cruz de la Sierra",
     "latitude": -17.8366, "longitude": -63.1912, "is_main": False},
    {"supplier_id": 3315, "branch_name": "Aceros Arequipa La Paz Calacoto", "city": "LPZ", "department": "La Paz",
     "address": "Av. Munoz Reyes N 26, Edificio Torre Grandezza, Calacoto, La Paz",
     "latitude": -16.5471, "longitude": -68.0741, "is_main": True},

    # ── Faboce (3335) — 2 plantas con direccion ──────────────
    {"supplier_id": 3335, "branch_name": "Faboce Planta Cochabamba", "city": "CBBA", "department": "Cochabamba",
     "address": "Carretera a Sacaba Km 8, Cochabamba",
     "latitude": -17.3972, "longitude": -66.0785, "is_main": True},
    {"supplier_id": 3335, "branch_name": "Faboce Planta Santa Cruz", "city": "SCZ", "department": "Santa Cruz",
     "address": "Carretera a Cotoca Km 13, Av. Cristo Redentor esq. 3er anillo externo, Santa Cruz",
     "latitude": -17.7596, "longitude": -63.1063, "is_main": False},

    # ── Electrored (3333) — 1 sucursal con direccion ─────────
    {"supplier_id": 3333, "branch_name": "Electrored El Alto", "city": "EL ALTO", "department": "La Paz",
     "address": "Calle 1 N 3760, El Alto",
     "latitude": -16.5084, "longitude": -68.1836, "is_main": False},

    # ── Mamut (3358) — 3 oficinas con telefonos ─────────────
    {"supplier_id": 3358, "branch_name": "Mamut Cochabamba", "city": "CBBA", "department": "Cochabamba",
     "address": "Cochabamba",
     "phone": "+591 4 4486243", "whatsapp": "+591 70341775",
     "email": "ventas@pisosmamut.com",
     "latitude": -17.3935, "longitude": -66.1570, "is_main": True},
    {"supplier_id": 3358, "branch_name": "Mamut Santa Cruz", "city": "SCZ", "department": "Santa Cruz",
     "address": "Santa Cruz de la Sierra",
     "whatsapp": "+591 79954484",
     "latitude": -17.7833, "longitude": -63.1821, "is_main": False},
    {"supplier_id": 3358, "branch_name": "Mamut La Paz", "city": "LPZ", "department": "La Paz",
     "address": "La Paz",
     "whatsapp": "+591 60179790",
     "latitude": -16.5000, "longitude": -68.1193, "is_main": False},

    # ── Synergy (3384) — sucursales principales ──────────────
    {"supplier_id": 3384, "branch_name": "Synergy Cochabamba Blanco Galindo", "city": "CBBA", "department": "Cochabamba",
     "address": "Av. Blanco Galindo, Villa Busch, Cochabamba",
     "latitude": -17.3925, "longitude": -66.1885, "is_main": True},
    {"supplier_id": 3384, "branch_name": "Synergy Santa Cruz", "city": "SCZ", "department": "Santa Cruz",
     "address": "Santa Cruz de la Sierra",
     "latitude": -17.7833, "longitude": -63.1821, "is_main": False},
    {"supplier_id": 3384, "branch_name": "Synergy La Paz", "city": "LPZ", "department": "La Paz",
     "address": "La Paz",
     "latitude": -16.5000, "longitude": -68.1193, "is_main": False},
    {"supplier_id": 3384, "branch_name": "Synergy Tarija", "city": "TJA", "department": "Tarija",
     "address": "Tarija",
     "latitude": -21.5355, "longitude": -64.7296, "is_main": False},
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

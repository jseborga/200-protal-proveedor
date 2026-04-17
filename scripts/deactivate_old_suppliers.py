"""Desactiva proveedores duplicados antiguos (sin datos enriquecidos).

Las entradas antiguas (IDs 3313-3398) fueron creadas antes del enriquecimiento.
Las nuevas (IDs 3399-3482) tienen description, operating_cities, phone2, website.

Tambien actualiza Gestual Arquitectura (3341) que no tenia version nueva.

Ejecutar: python scripts/deactivate_old_suppliers.py
"""

import httpx
import os

APP_URL = os.getenv("APP_URL", "https://apu-marketplace-app.q8waob.easypanel.host")
API_KEY = os.getenv("API_KEY", "mkt_z3dccrUc8-ZyCyaYPkEUMNy6WOwt8muzvRR-E3iM9vs")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# Old duplicate IDs to deactivate (IDs 3313-3398, excluding unique ones)
OLD_IDS_TO_DEACTIVATE = list(range(3313, 3399))

# Gestual Arquitectura (3341) - update with enriched data instead of deactivating
GESTUAL_UPDATE = {
    "name": "Gestual Arquitectura",
    "phone": "+591 62322006",
    "description": "Estudio de arquitectura, diseno arquitectonico y de interiores",
    "categories": [],
    "is_active": True,
}


def main():
    print(f"Limpiando proveedores duplicados en {APP_URL}...")

    # Step 1: Update Gestual Arquitectura with enriched data
    print("\n1. Actualizando Gestual Arquitectura (id=3341)...")
    resp = httpx.put(
        f"{APP_URL}/api/v1/integration/suppliers/3341",
        json=GESTUAL_UPDATE, headers=HEADERS, timeout=15,
    )
    if resp.status_code == 200:
        print(f"  + Gestual Arquitectura actualizado")
    else:
        print(f"  ! Error: HTTP {resp.status_code}")

    # Step 2: Deactivate old entries (except 3341 which we just updated)
    print(f"\n2. Desactivando {len(OLD_IDS_TO_DEACTIVATE)} entradas antiguas...")
    deactivated = 0
    errors = 0

    for sid in OLD_IDS_TO_DEACTIVATE:
        if sid == 3341:
            print(f"  = id={sid} Gestual Arquitectura (conservado)")
            continue

        resp = httpx.put(
            f"{APP_URL}/api/v1/integration/suppliers/{sid}",
            json={"name": "_", "is_active": False},
            headers=HEADERS, timeout=10,
        )
        if resp.status_code == 200:
            deactivated += 1
        elif resp.status_code == 404:
            pass  # Already gone
        else:
            errors += 1
            if errors <= 3:
                print(f"  ! id={sid}: HTTP {resp.status_code}")

    print(f"\nResultado: {deactivated} desactivados, {errors} errores")
    print("Done.")


if __name__ == "__main__":
    main()

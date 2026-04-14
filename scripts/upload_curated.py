"""
Sube los datos curados al portal APU Marketplace via API.

Uso:
    python scripts/upload_curated.py

Requiere que el portal este desplegado y la API key sea valida.
"""

import json
import time
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Instalando httpx...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
    import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

API_URL = "https://apu-marketplace-app.q8waob.easypanel.host"
API_KEY = "mkt_z3dccrUc8-ZyCyaYPkEUMNy6WOwt8muzvRR-E3iM9vs"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
BASE = f"{API_URL}/api/v1/integration"

BATCH_SIZE = 50


def upload_suppliers():
    with open(DATA_DIR / "curated_suppliers.json", encoding="utf-8") as f:
        suppliers = json.load(f)

    print(f"Subiendo {len(suppliers)} proveedores en lotes de {BATCH_SIZE}...")

    created = 0
    errors = 0
    skipped = 0

    for i in range(0, len(suppliers), BATCH_SIZE):
        batch = suppliers[i:i + BATCH_SIZE]
        # Prepare batch data (remove 'suppliers' field from products relationship)
        batch_data = []
        for s in batch:
            item = {
                "name": s["name"],
                "whatsapp": s.get("whatsapp") or "0000000000",
                "city": s.get("city") or "La Paz",
                "department": s.get("department") or "La Paz",
                "categories": s.get("categories") or [],
                "verification_state": "verified",
            }
            if s.get("phone"):
                item["phone"] = s["phone"]
            if s.get("email"):
                item["email"] = s["email"]
            if s.get("nit"):
                item["nit"] = s["nit"]
            if s.get("address"):
                item["address"] = s["address"]
            batch_data.append(item)

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{BASE}/suppliers/bulk",
                    headers=HEADERS,
                    json={"suppliers": batch_data},
                )
                result = resp.json()

            if result.get("ok"):
                batch_created = result.get("created", len(batch_data))
                batch_skipped = result.get("skipped", 0)
                created += batch_created
                skipped += batch_skipped
            else:
                errors += len(batch_data)
                print(f"  Error lote {i//BATCH_SIZE + 1}: {result.get('detail', 'unknown')}")

        except Exception as e:
            errors += len(batch_data)
            print(f"  Error lote {i//BATCH_SIZE + 1}: {e}")

        # Progress
        done = min(i + BATCH_SIZE, len(suppliers))
        pct = done / len(suppliers) * 100
        print(f"  [{done}/{len(suppliers)}] {pct:.0f}% - creados: {created}, saltados: {skipped}, errores: {errors}")
        time.sleep(0.3)

    print(f"\nProveedores: {created} creados, {skipped} saltados, {errors} errores")
    return created


def upload_products():
    with open(DATA_DIR / "curated_products.json", encoding="utf-8") as f:
        products = json.load(f)

    print(f"\nSubiendo {len(products)} productos en lotes de {BATCH_SIZE}...")

    created = 0
    errors = 0
    skipped = 0

    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i:i + BATCH_SIZE]
        batch_data = []
        for p in batch:
            item = {
                "name": p["name"],
                "uom": p.get("uom") or "pza",
            }
            if p.get("category"):
                item["category"] = p["category"]
            if p.get("code"):
                item["code"] = p["code"]
            if p.get("ref_price"):
                item["ref_price"] = p["ref_price"]
            if p.get("ref_currency"):
                item["ref_currency"] = p["ref_currency"]
            if p.get("description"):
                item["description"] = p["description"]
            batch_data.append(item)

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{BASE}/products/bulk",
                    headers=HEADERS,
                    json={"products": batch_data},
                )
                result = resp.json()

            if result.get("ok"):
                batch_created = result.get("created", len(batch_data))
                batch_skipped = result.get("skipped", 0)
                created += batch_created
                skipped += batch_skipped
            else:
                errors += len(batch_data)
                print(f"  Error lote {i//BATCH_SIZE + 1}: {result.get('detail', 'unknown')}")

        except Exception as e:
            errors += len(batch_data)
            print(f"  Error lote {i//BATCH_SIZE + 1}: {e}")

        done = min(i + BATCH_SIZE, len(products))
        pct = done / len(products) * 100
        print(f"  [{done}/{len(products)}] {pct:.0f}% - creados: {created}, saltados: {skipped}, errores: {errors}")
        time.sleep(0.3)

    print(f"\nProductos: {created} creados, {skipped} saltados, {errors} errores")
    return created


def main():
    print("=" * 60)
    print("UPLOAD DE DATOS CURADOS - APU Marketplace")
    print("=" * 60)

    # Check API
    print("\nVerificando conexion...")
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{BASE}/stats", headers=HEADERS)
            stats = resp.json()
        print(f"Portal actual: {stats.get('suppliers', 0)} proveedores, {stats.get('products', 0)} productos")
    except Exception as e:
        print(f"Error conectando al portal: {e}")
        return

    print()
    sup_count = upload_suppliers()
    prod_count = upload_products()

    # Final stats
    print("\n" + "=" * 60)
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{BASE}/stats", headers=HEADERS)
            stats = resp.json()
        print(f"Portal final: {stats.get('suppliers', 0)} proveedores, {stats.get('products', 0)} productos")
    except:
        pass
    print("Upload completado!")


if __name__ == "__main__":
    main()

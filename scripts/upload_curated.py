"""
Sube los datos curados v3 al portal APU Marketplace via API.

Flujo: purge -> suppliers -> products -> prices

Uso:
    python scripts/upload_curated.py              # upload solo (sin purge)
    python scripts/upload_curated.py --purge      # purge + upload completo
    python scripts/upload_curated.py --prices     # solo precios (asume productos ya existen)
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

BATCH_SIZE = 25  # smaller batches to avoid timeouts


def purge_all():
    """Delete ALL data from the portal."""
    print("PURGANDO todos los datos...")
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.delete(f"{BASE}/purge?confirm=yes", headers=HEADERS)
            result = resp.json()
        if result.get("ok"):
            print(f"  Purgado: {result.get('deleted', {})}")
        else:
            print(f"  Error: {result}")
    except Exception as e:
        print(f"  Error purgando: {e}")


def upload_suppliers():
    with open(DATA_DIR / "curated_suppliers.json", encoding="utf-8") as f:
        suppliers = json.load(f)

    print(f"\nSubiendo {len(suppliers)} proveedores en lotes de {BATCH_SIZE}...")

    created = 0
    errors = 0
    skipped = 0

    for i in range(0, len(suppliers), BATCH_SIZE):
        batch = suppliers[i:i + BATCH_SIZE]
        batch_data = []
        for s in batch:
            item = {
                "name": s["name"],
                "whatsapp": s.get("whatsapp") or "",
                "city": s.get("city") or "La Paz",
                "department": s.get("department") or "La Paz",
                "categories": s.get("categories") or [],
                "verification_state": s.get("verification_state", "pending"),
            }
            if s.get("phone"): item["phone"] = s["phone"]
            if s.get("email"): item["email"] = s["email"]
            if s.get("nit"): item["nit"] = s["nit"]
            if s.get("address"): item["address"] = s["address"]
            batch_data.append(item)

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(f"{BASE}/suppliers/bulk", headers=HEADERS,
                                   json={"suppliers": batch_data})
                result = resp.json()
            if result.get("ok"):
                created += result.get("created", 0)
                skipped += result.get("skipped", 0)
            else:
                errors += len(batch_data)
                print(f"  Error lote {i//BATCH_SIZE + 1}: {result.get('detail', 'unknown')}")
        except Exception as e:
            errors += len(batch_data)
            print(f"  Error lote {i//BATCH_SIZE + 1}: {e}")

        done = min(i + BATCH_SIZE, len(suppliers))
        print(f"  [{done}/{len(suppliers)}] +{created} creados, {skipped} existentes, {errors} errores")
        time.sleep(0.5)

    print(f"  Proveedores: {created} creados, {skipped} existentes, {errors} errores")
    return created


def upload_products():
    with open(DATA_DIR / "curated_products.json", encoding="utf-8") as f:
        products = json.load(f)

    print(f"\nSubiendo {len(products)} productos en lotes de {BATCH_SIZE}...")

    created = 0
    errors = 0
    skipped = 0
    error_items = []

    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i:i + BATCH_SIZE]
        batch_data = []
        for p in batch:
            item = {"name": p["name"], "uom": p.get("uom") or "pza"}
            if p.get("category"): item["category"] = p["category"]
            if p.get("code"): item["code"] = p["code"]
            if p.get("ref_price"): item["ref_price"] = p["ref_price"]
            if p.get("ref_currency"): item["ref_currency"] = p["ref_currency"]
            if p.get("description"): item["description"] = p["description"]
            batch_data.append(item)

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(f"{BASE}/products/bulk", headers=HEADERS,
                                   json={"products": batch_data})
                result = resp.json()
            if result.get("ok"):
                created += result.get("created", 0)
                skipped += result.get("skipped", 0)
            else:
                errors += len(batch_data)
                error_items.extend(batch_data)
                print(f"  Error lote {i//BATCH_SIZE + 1}: {result.get('detail', 'unknown')}")
        except Exception as e:
            errors += len(batch_data)
            error_items.extend(batch_data)
            print(f"  Error lote {i//BATCH_SIZE + 1}: {e}")

        done = min(i + BATCH_SIZE, len(products))
        print(f"  [{done}/{len(products)}] +{created} creados, {skipped} existentes, {errors} errores")
        time.sleep(0.5)

    # Retry failed items one by one
    if error_items:
        print(f"\n  Reintentando {len(error_items)} items uno a uno...")
        retry_created = 0
        for item in error_items:
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.post(f"{BASE}/products/bulk", headers=HEADERS,
                                       json={"products": [item]})
                    result = resp.json()
                if result.get("ok"):
                    retry_created += result.get("created", 0)
            except:
                pass
            time.sleep(0.3)
        created += retry_created
        errors -= retry_created
        print(f"  Retry: +{retry_created} recuperados")

    print(f"  Productos: {created} creados, {skipped} existentes, {errors} errores")
    return created


def upload_prices():
    with open(DATA_DIR / "curated_prices.json", encoding="utf-8") as f:
        prices = json.load(f)

    print(f"\nSubiendo {len(prices)} registros de precio en lotes de {BATCH_SIZE}...")

    created = 0
    errors = 0
    not_found = 0

    for i in range(0, len(prices), BATCH_SIZE):
        batch = prices[i:i + BATCH_SIZE]
        batch_data = []
        for p in batch:
            batch_data.append({
                "product_name": p["product_name"],
                "supplier_name": p.get("supplier_name") or "",
                "unit_price": p["unit_price"],
                "currency": p.get("currency", "BOB"),
                "quantity": p.get("quantity"),
                "observed_date": p["observed_date"],
                "source": p.get("source", "pedido"),
                "source_ref": p.get("source_ref"),
            })

        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(f"{BASE}/prices/bulk", headers=HEADERS,
                                   json={"records": batch_data})
                result = resp.json()
            if result.get("ok"):
                created += result.get("created", 0)
                not_found += result.get("errors", 0)
            else:
                errors += len(batch_data)
                print(f"  Error lote {i//BATCH_SIZE + 1}: {result.get('detail', 'unknown')}")
        except Exception as e:
            errors += len(batch_data)
            print(f"  Error lote {i//BATCH_SIZE + 1}: {e}")

        done = min(i + BATCH_SIZE, len(prices))
        print(f"  [{done}/{len(prices)}] +{created} creados, {not_found} no encontrados, {errors} errores")
        time.sleep(0.5)

    print(f"  Precios: {created} creados, {not_found} producto no encontrado, {errors} errores")
    return created


def main():
    do_purge = "--purge" in sys.argv
    prices_only = "--prices" in sys.argv

    print("=" * 60)
    print("UPLOAD DE DATOS CURADOS v3 - APU Marketplace")
    print("=" * 60)

    # Check API
    print("\nVerificando conexion...")
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{BASE}/stats", headers=HEADERS)
            stats = resp.json()
        print(f"Portal actual: {stats.get('suppliers', 0)} proveedores, "
              f"{stats.get('products', 0)} productos, "
              f"{stats.get('price_records', 0)} precios")
    except Exception as e:
        print(f"Error conectando: {e}")
        return

    if do_purge:
        purge_all()
        time.sleep(1)

    if prices_only:
        upload_prices()
    else:
        upload_suppliers()
        upload_products()
        time.sleep(1)
        upload_prices()

    # Final stats
    print("\n" + "=" * 60)
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{BASE}/stats", headers=HEADERS)
            stats = resp.json()
        print(f"Portal final: {stats.get('suppliers', 0)} proveedores, "
              f"{stats.get('products', 0)} productos, "
              f"{stats.get('price_records', 0)} precios")
    except:
        pass
    print("Upload completado!")


if __name__ == "__main__":
    main()

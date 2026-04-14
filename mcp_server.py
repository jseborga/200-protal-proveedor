"""MCP Server for APU Marketplace — Manage suppliers and products via Claude Code."""

import os
import json
import httpx
from mcp.server.fastmcp import FastMCP

API_URL = os.environ.get("MKT_API_URL", "https://apu-marketplace-app.q8waob.easypanel.host")
API_KEY = os.environ.get("MKT_API_KEY", "")

mcp = FastMCP("APU Marketplace")

HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
BASE = f"{API_URL}/api/v1/integration"


async def _get(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE}{path}", headers=HEADERS, params=params)
        return resp.json()


async def _post(path: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE}{path}", headers=HEADERS, json=data)
        return resp.json()


async def _put(path: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(f"{BASE}{path}", headers=HEADERS, json=data)
        return resp.json()


# ── Stats ──────────────────────────────────────────────────────
@mcp.tool()
async def get_stats() -> str:
    """Get marketplace stats: total suppliers and products count."""
    result = await _get("/stats")
    return json.dumps(result, ensure_ascii=False)


# ── Suppliers ──────────────────────────────────────────────────
@mcp.tool()
async def list_suppliers(
    query: str = "",
    city: str = "",
    department: str = "",
    category: str = "",
    limit: int = 50,
) -> str:
    """List suppliers from the marketplace.

    Args:
        query: Search by name
        city: Filter by city
        department: Filter by department (Santa Cruz, La Paz, Cochabamba, etc.)
        category: Filter by category (ferreteria, agregados, acero, electrico, sanitario, madera, cemento, pintura, ceramica, herramientas)
        limit: Max results (default 50)
    """
    params = {"limit": limit}
    if query:
        params["q"] = query
    if city:
        params["city"] = city
    if department:
        params["department"] = department
    if category:
        params["category"] = category

    result = await _get("/suppliers", params)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def create_supplier(
    name: str,
    whatsapp: str,
    city: str,
    department: str,
    categories: list[str],
    trade_name: str = "",
    phone: str = "",
    email: str = "",
    nit: str = "",
    address: str = "",
) -> str:
    """Register a new construction material supplier.

    Args:
        name: Legal name (razon social)
        whatsapp: WhatsApp number with country code (e.g. 59177889900)
        city: City (e.g. Santa Cruz de la Sierra)
        department: Department (Santa Cruz, La Paz, Cochabamba, Tarija, Sucre, Oruro, Potosi, Beni, Pando)
        categories: Product categories list (ferreteria, agregados, acero, electrico, sanitario, madera, cemento, pintura, ceramica, herramientas)
        trade_name: Commercial name
        phone: Phone number
        email: Email address
        nit: Tax ID (NIT)
        address: Physical address
    """
    data = {
        "name": name,
        "whatsapp": whatsapp,
        "city": city,
        "department": department,
        "categories": categories,
        "verification_state": "verified",
    }
    if trade_name:
        data["trade_name"] = trade_name
    if phone:
        data["phone"] = phone
    if email:
        data["email"] = email
    if nit:
        data["nit"] = nit
    if address:
        data["address"] = address

    result = await _post("/suppliers", data)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def create_suppliers_bulk(suppliers: list[dict]) -> str:
    """Create multiple suppliers at once. Each supplier dict should have: name, whatsapp, city, department, categories.

    Args:
        suppliers: List of supplier dicts. Required fields per supplier: name (str), whatsapp (str), city (str), department (str), categories (list[str]). Optional: trade_name, phone, email, nit, address.
    """
    # Ensure verification_state is set
    for s in suppliers:
        s.setdefault("verification_state", "verified")

    result = await _post("/suppliers/bulk", {"suppliers": suppliers})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def update_supplier(supplier_id: int, **fields) -> str:
    """Update an existing supplier by ID.

    Args:
        supplier_id: Supplier ID
        **fields: Fields to update (name, whatsapp, city, department, categories, etc.)
    """
    result = await _put(f"/suppliers/{supplier_id}", fields)
    return json.dumps(result, ensure_ascii=False)


# ── Products ───────────────────────────────────────────────────
@mcp.tool()
async def list_products(
    query: str = "",
    category: str = "",
    limit: int = 50,
) -> str:
    """List construction products/materials from the catalog.

    Args:
        query: Search by name
        category: Filter by category
        limit: Max results (default 50)
    """
    params = {"limit": limit}
    if query:
        params["q"] = query
    if category:
        params["category"] = category

    result = await _get("/products", params)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def create_product(
    name: str,
    uom: str,
    category: str = "",
    code: str = "",
    ref_price: float = 0,
    ref_currency: str = "BOB",
    description: str = "",
) -> str:
    """Add a new construction product/material to the catalog.

    Args:
        name: Product name (e.g. Cemento Portland IP-30)
        uom: Unit of measure (bls, kg, tn, m3, m2, ml, pza, lt, gl, glb, rollo, varilla)
        category: Category (Ferreteria, Agregados, Acero, Electrico, Sanitario, Madera, Cemento, Pintura, Ceramica, Herramientas)
        code: Product code (e.g. CEM-001)
        ref_price: Reference price
        ref_currency: Currency (BOB or USD)
        description: Product description
    """
    data = {"name": name, "uom": uom}
    if category:
        data["category"] = category
    if code:
        data["code"] = code
    if ref_price:
        data["ref_price"] = ref_price
    if ref_currency:
        data["ref_currency"] = ref_currency
    if description:
        data["description"] = description

    result = await _post("/products", data)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def create_products_bulk(products: list[dict]) -> str:
    """Create multiple products at once. Each product dict should have: name, uom.

    Args:
        products: List of product dicts. Required: name (str), uom (str). Optional: category, code, ref_price, ref_currency, description.
    """
    result = await _post("/products/bulk", {"products": products})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def update_product(product_id: int, **fields) -> str:
    """Update an existing product by ID.

    Args:
        product_id: Product ID
        **fields: Fields to update (name, uom, category, ref_price, etc.)
    """
    result = await _put(f"/products/{product_id}", fields)
    return json.dumps(result, ensure_ascii=False)


# ── Price History ─────────────────────────────────────────────
@mcp.tool()
async def create_price_history_bulk(records: list[dict]) -> str:
    """Upload price history records in bulk.

    Args:
        records: List of price records. Each dict should have:
            - product_name (str) or insumo_id (int): identifies the product
            - unit_price (float): observed price
            - observed_date (str): date in YYYY-MM-DD format
            - supplier_name (str) or supplier_id (int): optional, identifies the supplier
            - currency (str): default "BOB"
            - quantity (float): optional
            - uom (str): optional
            - source (str): default "import" (pedido, cotizacion, manual, import)
            - source_ref (str): optional reference number
    """
    result = await _post("/prices/bulk", {"records": records})
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_price_history(
    insumo_id: int,
    supplier_id: int = 0,
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
) -> str:
    """Get price history for a specific product/insumo.

    Args:
        insumo_id: Product/insumo ID
        supplier_id: Optional filter by supplier ID
        date_from: Optional start date (YYYY-MM-DD)
        date_to: Optional end date (YYYY-MM-DD)
        limit: Max results (default 100)
    """
    params = {"limit": limit}
    if supplier_id:
        params["supplier_id"] = supplier_id
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to

    result = await _get(f"/prices/history/{insumo_id}", params)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_price_evolution(insumo_id: int) -> str:
    """Get price evolution stats per year for a product: avg, min, max, median.

    Args:
        insumo_id: Product/insumo ID
    """
    result = await _get(f"/prices/evolution/{insumo_id}")
    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")

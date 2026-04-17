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
async def update_supplier(
    supplier_id: int,
    name: str = "",
    trade_name: str = "",
    nit: str = "",
    email: str = "",
    phone: str = "",
    phone2: str = "",
    whatsapp: str = "",
    website: str = "",
    city: str = "",
    department: str = "",
    address: str = "",
    description: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    operating_cities: list[str] | None = None,
    categories: list[str] | None = None,
) -> str:
    """Update an existing supplier by ID. Only non-empty fields are updated.

    Args:
        supplier_id: Supplier ID (required)
        name, trade_name, nit: Identificadores
        email, phone, phone2, whatsapp, website: Contactos
        city, department, address: Ubicacion principal
        description: Descripcion del proveedor
        latitude, longitude: Coordenadas (-90..90, -180..180)
        operating_cities: Ciudades donde opera (ej: ["LPZ","SCZ","CBBA"])
        categories: Categorias del catalogo (ej: ["cemento","acero"])
    """
    fields: dict = {}
    if name: fields["name"] = name
    if trade_name: fields["trade_name"] = trade_name
    if nit: fields["nit"] = nit
    if email: fields["email"] = email
    if phone: fields["phone"] = phone
    if phone2: fields["phone2"] = phone2
    if whatsapp: fields["whatsapp"] = whatsapp
    if website: fields["website"] = website
    if city: fields["city"] = city
    if department: fields["department"] = department
    if address: fields["address"] = address
    if description: fields["description"] = description
    if latitude is not None: fields["latitude"] = latitude
    if longitude is not None: fields["longitude"] = longitude
    if operating_cities is not None: fields["operating_cities"] = operating_cities
    if categories is not None: fields["categories"] = categories

    result = await _put(f"/suppliers/{supplier_id}", fields)
    return json.dumps(result, ensure_ascii=False)


# ── Supplier Detail + Branches ─────────────────────────────────
@mcp.tool()
async def get_supplier_detail(supplier_id: int) -> str:
    """Get full supplier detail including branches and branch contacts.

    Args:
        supplier_id: Supplier ID
    """
    result = await _get(f"/suppliers/{supplier_id}/detail")
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def list_branches(supplier_id: int, include_contacts: bool = False) -> str:
    """List active branches of a supplier.

    Args:
        supplier_id: Supplier ID
        include_contacts: If True, include branch contacts
    """
    params = {"include_contacts": "true" if include_contacts else "false"}
    result = await _get(f"/branches/{supplier_id}", params)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def create_branch(
    supplier_id: int,
    branch_name: str,
    city: str = "",
    department: str = "",
    address: str = "",
    phone: str = "",
    whatsapp: str = "",
    email: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    is_main: bool = False,
) -> str:
    """Create a branch for a supplier.

    Args:
        supplier_id: Supplier ID
        branch_name: Nombre de la sucursal (ej: "Central Av Arce", "Sucursal El Alto")
        city, department, address: Ubicacion
        phone, whatsapp, email: Contacto de la sucursal
        latitude, longitude: Coordenadas
        is_main: True para marcarla como principal (desmarca otras)
    """
    data = {
        "supplier_id": supplier_id,
        "branch_name": branch_name,
        "is_main": is_main,
    }
    if city: data["city"] = city
    if department: data["department"] = department
    if address: data["address"] = address
    if phone: data["phone"] = phone
    if whatsapp: data["whatsapp"] = whatsapp
    if email: data["email"] = email
    if latitude is not None: data["latitude"] = latitude
    if longitude is not None: data["longitude"] = longitude
    result = await _post("/branches", data)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def update_branch(
    branch_id: int,
    branch_name: str = "",
    city: str = "",
    department: str = "",
    address: str = "",
    phone: str = "",
    whatsapp: str = "",
    email: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    is_main: bool | None = None,
    is_active: bool | None = None,
) -> str:
    """Update a branch. Only non-empty / non-None fields are updated.

    Args:
        branch_id: Branch ID
        branch_name, city, department, address: Ubicacion / nombre
        phone, whatsapp, email: Contacto
        latitude, longitude: Coordenadas
        is_main: True marca como principal (desmarca otras)
        is_active: False la desactiva
    """
    fields: dict = {}
    if branch_name: fields["branch_name"] = branch_name
    if city: fields["city"] = city
    if department: fields["department"] = department
    if address: fields["address"] = address
    if phone: fields["phone"] = phone
    if whatsapp: fields["whatsapp"] = whatsapp
    if email: fields["email"] = email
    if latitude is not None: fields["latitude"] = latitude
    if longitude is not None: fields["longitude"] = longitude
    if is_main is not None: fields["is_main"] = is_main
    if is_active is not None: fields["is_active"] = is_active
    result = await _put(f"/branches/{branch_id}", fields)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def delete_branch(branch_id: int) -> str:
    """Deactivate a branch (soft delete).

    Args:
        branch_id: Branch ID
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(f"{BASE}/branches/{branch_id}", headers=HEADERS)
        return json.dumps(resp.json(), ensure_ascii=False)


# ── Branch Contacts ────────────────────────────────────────────
@mcp.tool()
async def create_branch_contact(
    branch_id: int,
    full_name: str,
    position: str = "",
    phone: str = "",
    whatsapp: str = "",
    email: str = "",
    is_primary: bool = False,
) -> str:
    """Add a contact person to a branch.

    Args:
        branch_id: Branch ID
        full_name: Nombre completo
        position: Cargo (ej: "Gerente de Ventas", "Ejecutivo Comercial")
        phone, whatsapp, email: Contacto
        is_primary: Marcar como contacto principal
    """
    data = {
        "branch_id": branch_id,
        "full_name": full_name,
        "is_primary": is_primary,
    }
    if position: data["position"] = position
    if phone: data["phone"] = phone
    if whatsapp: data["whatsapp"] = whatsapp
    if email: data["email"] = email
    result = await _post("/branch-contacts", data)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def update_branch_contact(
    contact_id: int,
    full_name: str = "",
    position: str = "",
    phone: str = "",
    whatsapp: str = "",
    email: str = "",
    is_primary: bool | None = None,
    is_active: bool | None = None,
) -> str:
    """Update a branch contact.

    Args:
        contact_id: Contact ID
        full_name, position, phone, whatsapp, email: Campos a actualizar
        is_primary: Marcar como principal
        is_active: False desactiva el contacto
    """
    fields: dict = {}
    if full_name: fields["full_name"] = full_name
    if position: fields["position"] = position
    if phone: fields["phone"] = phone
    if whatsapp: fields["whatsapp"] = whatsapp
    if email: fields["email"] = email
    if is_primary is not None: fields["is_primary"] = is_primary
    if is_active is not None: fields["is_active"] = is_active
    result = await _put(f"/branch-contacts/{contact_id}", fields)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def delete_branch_contact(contact_id: int) -> str:
    """Deactivate a branch contact.

    Args:
        contact_id: Contact ID
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(f"{BASE}/branch-contacts/{contact_id}", headers=HEADERS)
        return json.dumps(resp.json(), ensure_ascii=False)


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

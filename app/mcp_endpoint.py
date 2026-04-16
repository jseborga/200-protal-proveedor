"""MCP Server embebido en FastAPI — expone tools via SSE para Claude Code Routines.

Este modulo crea una instancia FastMCP con las mismas tools que mcp_server.py,
pero ejecuta las queries directamente contra la DB (sin pasar por HTTP).
Se monta como sub-aplicacion ASGI en /mcp-sse.

Autenticacion: el query param ?api_key= se valida contra las API keys del sistema.
"""

import json
from datetime import date

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select

from app.core.database import async_session


mcp = FastMCP("APU Marketplace")


# ── Stats ──────────────────────────────────────────────────────
@mcp.tool()
async def get_stats() -> str:
    """Get marketplace stats: total suppliers, products, prices count."""
    from app.models.supplier import Supplier
    from app.models.insumo import Insumo
    from app.models.price_history import PriceHistory

    async with async_session() as db:
        suppliers = (await db.execute(select(func.count(Supplier.id)))).scalar() or 0
        products = (await db.execute(select(func.count(Insumo.id)))).scalar() or 0
        prices = (await db.execute(select(func.count(PriceHistory.id)))).scalar() or 0

    return json.dumps({"suppliers": suppliers, "products": products, "prices": prices})


# ── Suppliers ──────────────────────────────────────────────────
@mcp.tool()
async def list_suppliers(
    query: str = "",
    city: str = "",
    department: str = "",
    category: str = "",
    limit: int = 50,
) -> str:
    """List suppliers. Filter by name (query), city, department, or category."""
    from app.models.supplier import Supplier

    async with async_session() as db:
        q = select(Supplier).where(Supplier.is_active == True).limit(min(limit, 200))
        if query:
            q = q.where(Supplier.name.ilike(f"%{query}%"))
        if city:
            q = q.where(Supplier.city.ilike(f"%{city}%"))
        if department:
            q = q.where(Supplier.department.ilike(f"%{department}%"))
        if category:
            q = q.where(Supplier.categories.any(category.lower()))

        result = await db.execute(q)
        items = result.scalars().all()

    return json.dumps([{
        "id": s.id, "name": s.name, "trade_name": s.trade_name,
        "city": s.city, "department": s.department,
        "categories": s.categories or [], "whatsapp": s.whatsapp,
        "nit": s.nit, "phone": s.phone, "email": s.email,
    } for s in items], ensure_ascii=False)


@mcp.tool()
async def create_supplier(
    name: str,
    city: str = "La Paz",
    department: str = "La Paz",
    categories: list[str] | None = None,
    whatsapp: str = "",
    trade_name: str = "",
    phone: str = "",
    email: str = "",
    nit: str = "",
    address: str = "",
) -> str:
    """Register a new supplier. Required: name. Optional: city, department, categories, whatsapp, etc."""
    from app.models.supplier import Supplier

    async with async_session() as db:
        supplier = Supplier(
            name=name, trade_name=trade_name or name,
            city=city, department=department,
            categories=categories or [],
            whatsapp=whatsapp, phone=phone, email=email,
            nit=nit, address=address,
            verification_state="verified", is_active=True,
        )
        db.add(supplier)
        await db.commit()
        await db.refresh(supplier)

    return json.dumps({"ok": True, "id": supplier.id, "name": supplier.name}, ensure_ascii=False)


@mcp.tool()
async def create_suppliers_bulk(suppliers: list[dict]) -> str:
    """Create multiple suppliers at once. Each dict: name (required), city, department, categories, whatsapp, etc."""
    from app.models.supplier import Supplier

    created = []
    async with async_session() as db:
        for s in suppliers:
            if not s.get("name"):
                continue
            supplier = Supplier(
                name=s["name"], trade_name=s.get("trade_name", s["name"]),
                city=s.get("city", "La Paz"), department=s.get("department", "La Paz"),
                categories=s.get("categories", []),
                whatsapp=s.get("whatsapp", ""), phone=s.get("phone", ""),
                email=s.get("email", ""), nit=s.get("nit", ""),
                address=s.get("address", ""),
                verification_state="verified", is_active=True,
            )
            db.add(supplier)
            created.append(s["name"])
        await db.commit()

    return json.dumps({"ok": True, "created": len(created), "names": created}, ensure_ascii=False)


# ── Products ──────────────────────────────────────────────────
@mcp.tool()
async def list_products(
    query: str = "",
    category: str = "",
    limit: int = 50,
) -> str:
    """List products/materials. Filter by name (query) or category."""
    from app.models.insumo import Insumo

    async with async_session() as db:
        q = select(Insumo).where(Insumo.is_active == True).limit(min(limit, 200))
        if query:
            q = q.where(Insumo.name.ilike(f"%{query}%"))
        if category:
            q = q.where(Insumo.category.ilike(f"%{category}%"))

        result = await db.execute(q)
        items = result.scalars().all()

    return json.dumps([{
        "id": i.id, "name": i.name, "uom": i.uom,
        "category": i.category, "ref_price": i.ref_price,
        "code": i.code,
    } for i in items], ensure_ascii=False)


@mcp.tool()
async def create_product(
    name: str,
    uom: str = "pza",
    category: str = "",
    code: str = "",
    ref_price: float = 0,
    description: str = "",
) -> str:
    """Create a new product/material. Required: name, uom."""
    from app.models.insumo import Insumo

    async with async_session() as db:
        product = Insumo(
            name=name, uom=uom, category=category,
            code=code, ref_price=ref_price or None,
            description=description, is_active=True,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)

    return json.dumps({"ok": True, "id": product.id, "name": product.name}, ensure_ascii=False)


@mcp.tool()
async def create_products_bulk(products: list[dict]) -> str:
    """Create multiple products at once. Each dict: name (required), uom, category, ref_price, code."""
    from app.models.insumo import Insumo

    created = []
    async with async_session() as db:
        for p in products:
            if not p.get("name"):
                continue
            product = Insumo(
                name=p["name"], uom=p.get("uom", "pza"),
                category=p.get("category", ""), code=p.get("code", ""),
                ref_price=p.get("ref_price") or None,
                description=p.get("description", ""), is_active=True,
            )
            db.add(product)
            created.append(p["name"])
        await db.commit()

    return json.dumps({"ok": True, "created": len(created), "names": created}, ensure_ascii=False)


@mcp.tool()
async def update_product(product_id: int, name: str = "", uom: str = "", category: str = "", ref_price: float = 0) -> str:
    """Update a product by ID. Only provided fields are updated."""
    from app.models.insumo import Insumo

    async with async_session() as db:
        product = await db.get(Insumo, product_id)
        if not product:
            return json.dumps({"ok": False, "error": f"Product {product_id} not found"})
        if name:
            product.name = name
        if uom:
            product.uom = uom
        if category:
            product.category = category
        if ref_price:
            product.ref_price = ref_price
        await db.commit()

    return json.dumps({"ok": True, "id": product_id}, ensure_ascii=False)


# ── Price History ─────────────────────────────────────────────
@mcp.tool()
async def create_price_history_bulk(records: list[dict]) -> str:
    """Register price records in bulk.

    Each record dict:
    - product_name (str) or insumo_id (int): identifies the product
    - unit_price (float): observed price
    - observed_date (str): YYYY-MM-DD (default: today)
    - supplier_name (str) or supplier_id (int): optional
    - currency (str): default BOB
    - source (str): default 'import'
    """
    from app.models.price_history import PriceHistory
    from app.models.insumo import Insumo
    from app.models.supplier import Supplier

    created = 0
    errors = []
    async with async_session() as db:
        for r in records:
            # Resolve product
            insumo_id = r.get("insumo_id")
            if not insumo_id and r.get("product_name"):
                result = await db.execute(
                    select(Insumo.id).where(Insumo.name.ilike(f"%{r['product_name']}%")).limit(1)
                )
                row = result.first()
                if row:
                    insumo_id = row[0]

            if not insumo_id:
                errors.append(f"Product not found: {r.get('product_name', '?')}")
                continue

            # Resolve supplier
            supplier_id = r.get("supplier_id")
            supplier_name = r.get("supplier_name", "")
            if not supplier_id and supplier_name:
                result = await db.execute(
                    select(Supplier.id).where(Supplier.name.ilike(f"%{supplier_name}%")).limit(1)
                )
                row = result.first()
                if row:
                    supplier_id = row[0]

            # Parse date
            obs_date = r.get("observed_date")
            if obs_date and isinstance(obs_date, str):
                try:
                    obs_date = date.fromisoformat(obs_date)
                except ValueError:
                    obs_date = date.today()
            else:
                obs_date = date.today()

            price = PriceHistory(
                insumo_id=insumo_id,
                supplier_id=supplier_id,
                supplier_name_text=supplier_name or None,
                unit_price=float(r.get("unit_price", 0)),
                currency=r.get("currency", "BOB"),
                observed_date=obs_date,
                source=r.get("source", "import"),
                source_ref=r.get("source_ref"),
            )
            db.add(price)
            created += 1

        await db.commit()

    return json.dumps({
        "ok": True, "created": created, "errors": errors[:10],
    }, ensure_ascii=False)


@mcp.tool()
async def get_price_history(insumo_id: int, limit: int = 50) -> str:
    """Get price history for a product by insumo_id."""
    from app.models.price_history import PriceHistory

    async with async_session() as db:
        result = await db.execute(
            select(PriceHistory)
            .where(PriceHistory.insumo_id == insumo_id)
            .order_by(PriceHistory.observed_date.desc())
            .limit(min(limit, 200))
        )
        items = result.scalars().all()

    return json.dumps([{
        "id": p.id, "unit_price": p.unit_price, "currency": p.currency,
        "observed_date": p.observed_date.isoformat() if p.observed_date else None,
        "supplier_name": p.supplier_name_text, "source": p.source,
    } for p in items], ensure_ascii=False)


@mcp.tool()
async def get_price_evolution(insumo_id: int) -> str:
    """Get price stats (avg, min, max) per year for a product."""
    from app.models.price_history import PriceHistory

    async with async_session() as db:
        result = await db.execute(
            select(
                func.extract("year", PriceHistory.observed_date).label("year"),
                func.avg(PriceHistory.unit_price).label("avg"),
                func.min(PriceHistory.unit_price).label("min"),
                func.max(PriceHistory.unit_price).label("max"),
                func.count(PriceHistory.id).label("count"),
            )
            .where(PriceHistory.insumo_id == insumo_id)
            .group_by("year")
            .order_by("year")
        )
        rows = result.all()

    return json.dumps([{
        "year": int(r[0]) if r[0] else None,
        "avg": round(float(r[1]), 2) if r[1] else 0,
        "min": float(r[2]) if r[2] else 0,
        "max": float(r[3]) if r[3] else 0,
        "count": r[4],
    } for r in rows], ensure_ascii=False)


def get_mcp_sse_app():
    """Return the MCP SSE Starlette app ready to mount in FastAPI."""
    return mcp.sse_app()


def get_mcp_http_app():
    """Return the MCP Streamable HTTP Starlette app (proxy-friendly, no long-lived connections)."""
    return mcp.streamable_http_app()

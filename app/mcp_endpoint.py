"""MCP Server embebido en FastAPI — expone tools via SSE para Claude Code Routines.

Este modulo crea una instancia FastMCP con las mismas tools que mcp_server.py,
pero ejecuta las queries directamente contra la DB (sin pasar por HTTP).
Se monta como sub-aplicacion ASGI en /mcp.
"""

import json
from datetime import date

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import func, select

from app.core.database import async_session


# Disable DNS rebinding protection — the app runs behind a reverse proxy
# (EasyPanel/Traefik) with HTTPS, so host validation is handled upstream.
mcp = FastMCP(
    "APU Marketplace",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


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


@mcp.tool()
async def update_supplier(
    supplier_id: int,
    name: str = "",
    trade_name: str = "",
    city: str = "",
    department: str = "",
    categories: list[str] | None = None,
    whatsapp: str = "",
    phone: str = "",
    email: str = "",
    nit: str = "",
    address: str = "",
) -> str:
    """Update a supplier by ID. Only provided (non-empty) fields are updated."""
    from app.models.supplier import Supplier

    async with async_session() as db:
        supplier = await db.get(Supplier, supplier_id)
        if not supplier:
            return json.dumps({"ok": False, "error": f"Supplier {supplier_id} not found"})
        if name:
            supplier.name = name
        if trade_name:
            supplier.trade_name = trade_name
        if city:
            supplier.city = city
        if department:
            supplier.department = department
        if categories is not None:
            supplier.categories = categories
        if whatsapp:
            supplier.whatsapp = whatsapp
        if phone:
            supplier.phone = phone
        if email:
            supplier.email = email
        if nit:
            supplier.nit = nit
        if address:
            supplier.address = address
        await db.commit()

    return json.dumps({"ok": True, "id": supplier_id, "name": supplier.name}, ensure_ascii=False)


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
    from app.services.matching import normalize_text, normalize_uom

    async with async_session() as db:
        product = Insumo(
            name=name, name_normalized=normalize_text(name),
            uom=uom, uom_normalized=normalize_uom(uom),
            category=category, code=code,
            ref_price=ref_price or None,
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
    from app.services.matching import normalize_text, normalize_uom

    created = []
    async with async_session() as db:
        for p in products:
            if not p.get("name"):
                continue
            name = p["name"]
            uom = p.get("uom", "pza")
            product = Insumo(
                name=name, name_normalized=normalize_text(name),
                uom=uom, uom_normalized=normalize_uom(uom),
                category=p.get("category", ""), code=p.get("code", ""),
                ref_price=p.get("ref_price") or None,
                description=p.get("description", ""), is_active=True,
            )
            db.add(product)
            created.append(name)
        await db.commit()

    return json.dumps({"ok": True, "created": len(created), "names": created}, ensure_ascii=False)


@mcp.tool()
async def update_product(product_id: int, name: str = "", uom: str = "", category: str = "", ref_price: float = 0) -> str:
    """Update a product by ID. Only provided fields are updated."""
    from app.models.insumo import Insumo
    from app.services.matching import normalize_text, normalize_uom

    async with async_session() as db:
        product = await db.get(Insumo, product_id)
        if not product:
            return json.dumps({"ok": False, "error": f"Product {product_id} not found"})
        if name:
            product.name = name
            product.name_normalized = normalize_text(name)
        if uom:
            product.uom = uom
            product.uom_normalized = normalize_uom(uom)
        if category:
            product.category = category
        if ref_price:
            product.ref_price = ref_price
        await db.commit()

    return json.dumps({"ok": True, "id": product_id}, ensure_ascii=False)


# ── Price History ─────────────────────────────────────────────
@mcp.tool()
async def create_price_history_bulk(records: list[dict]) -> str:
    """Register price records in bulk. Also creates supplier↔product links (ProductMatch).

    Each record dict:
    - product_name (str) or insumo_id (int): identifies the product
    - unit_price (float): observed price
    - observed_date (str): YYYY-MM-DD (default: today)
    - supplier_name (str) or supplier_id (int): optional
    - currency (str): default BOB
    - source (str): default 'import'
    - notes (str): optional notes (brand, etc.)
    """
    from app.models.price_history import PriceHistory
    from app.models.insumo import Insumo
    from app.models.supplier import Supplier
    from app.models.match import ProductMatch
    from app.services.matching import normalize_text

    created = 0
    matched = 0
    errors = []
    async with async_session() as db:
        for r in records:
            # Resolve product
            insumo_id = r.get("insumo_id")
            product_name = r.get("product_name", "")
            if not insumo_id and product_name:
                result = await db.execute(
                    select(Insumo.id).where(Insumo.name.ilike(f"%{product_name}%")).limit(1)
                )
                row = result.first()
                if row:
                    insumo_id = row[0]

            if not insumo_id:
                errors.append(f"Product not found: {product_name or '?'}")
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

            # Build notes from supplier_name + brand + explicit notes
            notes_parts = []
            if supplier_name and not supplier_id:
                notes_parts.append(f"Proveedor: {supplier_name}")
            if r.get("brand"):
                notes_parts.append(f"Marca: {r['brand']}")
            if r.get("notes"):
                notes_parts.append(r["notes"])
            notes = "; ".join(notes_parts) or None

            price = PriceHistory(
                insumo_id=insumo_id,
                supplier_id=supplier_id,
                unit_price=float(r.get("unit_price", 0)),
                currency=r.get("currency", "BOB"),
                observed_date=obs_date,
                source=r.get("source", "import"),
                source_ref=r.get("source_ref"),
                notes=notes,
            )
            db.add(price)
            created += 1

            # Auto-create ProductMatch if supplier and product are known
            if supplier_id and insumo_id and product_name:
                name_norm = normalize_text(product_name)
                existing = await db.execute(
                    select(ProductMatch.id).where(
                        ProductMatch.supplier_id == supplier_id,
                        ProductMatch.insumo_id == insumo_id,
                        ProductMatch.product_name_normalized == name_norm,
                    ).limit(1)
                )
                if not existing.first():
                    pm = ProductMatch(
                        supplier_id=supplier_id,
                        insumo_id=insumo_id,
                        product_name=product_name,
                        product_name_normalized=name_norm,
                        uom_original=r.get("uom"),
                        method="auto",
                        confidence=0.8,
                        usage_count=1,
                    )
                    db.add(pm)
                    matched += 1

        await db.commit()

    return json.dumps({
        "ok": True, "created": created, "matched": matched, "errors": errors[:10],
    }, ensure_ascii=False)


@mcp.tool()
async def get_price_history(insumo_id: int, limit: int = 50) -> str:
    """Get price history for a product by insumo_id. Includes supplier name."""
    from app.models.price_history import PriceHistory
    from app.models.supplier import Supplier

    async with async_session() as db:
        result = await db.execute(
            select(PriceHistory, Supplier.name.label("sup_name"))
            .outerjoin(Supplier, PriceHistory.supplier_id == Supplier.id)
            .where(PriceHistory.insumo_id == insumo_id)
            .order_by(PriceHistory.observed_date.desc())
            .limit(min(limit, 200))
        )
        rows = result.all()

    return json.dumps([{
        "id": p.id, "unit_price": p.unit_price, "currency": p.currency,
        "observed_date": p.observed_date.isoformat() if p.observed_date else None,
        "supplier_id": p.supplier_id, "supplier_name": sup_name,
        "source": p.source, "notes": p.notes,
    } for p, sup_name in rows], ensure_ascii=False)


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


# ── Supplier-Product Matching ────────────────────────────────
@mcp.tool()
async def search_product_fuzzy(query: str, limit: int = 10) -> str:
    """Fuzzy search for products using trigram similarity (pg_trgm).
    Better than ilike for matching variations like 'Cemento IP30' vs 'CEMENTO PORTLAND IP-30'.
    Returns products sorted by similarity score."""
    from app.models.insumo import Insumo
    from sqlalchemy import text as sql_text

    async with async_session() as db:
        result = await db.execute(
            sql_text("""
                SELECT id, name, uom, category, ref_price,
                       similarity(name, :q) AS score
                FROM mkt_insumo
                WHERE name % :q AND is_active = true
                ORDER BY score DESC
                LIMIT :lim
            """),
            {"q": query, "lim": min(limit, 20)},
        )
        rows = result.all()

    return json.dumps([{
        "id": r[0], "name": r[1], "uom": r[2], "category": r[3],
        "ref_price": r[4], "similarity": round(r[5], 3),
    } for r in rows], ensure_ascii=False)


@mcp.tool()
async def link_supplier_product(
    supplier_id: int,
    insumo_id: int,
    product_name: str,
    uom_original: str = "",
    confidence: float = 0.9,
) -> str:
    """Link a supplier to a product (ProductMatch). Records that this supplier
    sells this product under this name. Prevents duplicates."""
    from app.models.match import ProductMatch
    from app.services.matching import normalize_text

    name_norm = normalize_text(product_name)

    async with async_session() as db:
        # Check existing
        existing = await db.execute(
            select(ProductMatch).where(
                ProductMatch.supplier_id == supplier_id,
                ProductMatch.insumo_id == insumo_id,
                ProductMatch.product_name_normalized == name_norm,
            ).limit(1)
        )
        pm = existing.scalar_one_or_none()

        if pm:
            pm.usage_count += 1
            if confidence > pm.confidence:
                pm.confidence = confidence
            await db.commit()
            return json.dumps({"ok": True, "action": "updated", "id": pm.id, "usage_count": pm.usage_count})

        pm = ProductMatch(
            supplier_id=supplier_id,
            insumo_id=insumo_id,
            product_name=product_name,
            product_name_normalized=name_norm,
            uom_original=uom_original or None,
            method="routine",
            confidence=confidence,
            usage_count=1,
        )
        db.add(pm)
        await db.commit()
        await db.refresh(pm)

    return json.dumps({"ok": True, "action": "created", "id": pm.id})


@mcp.tool()
async def get_supplier_products(supplier_id: int) -> str:
    """Get all products linked to a supplier (via ProductMatch)."""
    from app.models.match import ProductMatch
    from app.models.insumo import Insumo

    async with async_session() as db:
        result = await db.execute(
            select(ProductMatch, Insumo.name.label("catalog_name"), Insumo.category)
            .join(Insumo, ProductMatch.insumo_id == Insumo.id)
            .where(ProductMatch.supplier_id == supplier_id)
            .order_by(ProductMatch.usage_count.desc())
        )
        rows = result.all()

    return json.dumps([{
        "match_id": pm.id, "insumo_id": pm.insumo_id,
        "supplier_name": pm.product_name, "catalog_name": cat_name,
        "category": cat, "confidence": pm.confidence,
        "usage_count": pm.usage_count, "validated": pm.is_validated,
    } for pm, cat_name, cat in rows], ensure_ascii=False)


# ── Telegram notification (for Routine → user feedback) ───────

@mcp.tool()
async def notify_telegram(chat_id: str, message: str) -> str:
    """Send a message to a Telegram user. Use this to report results back
    after processing their documents.

    IMPORTANT: Always call this when you finish processing a task from Telegram.
    Include a summary of what was done: products created, prices registered, etc.
    Use HTML formatting: <b>bold</b>, <i>italic</i>, <code>code</code>.
    """
    from app.services.messaging import send_telegram

    success = await send_telegram(chat_id, message)
    if success:
        return json.dumps({"ok": True, "message": "Notification sent"})
    return json.dumps({"ok": False, "error": "Failed to send Telegram message"})


# ── Uploaded image retrieval (for Routine vision) ─────────────

@mcp.tool()
async def get_uploaded_image(token: str) -> list:
    """Retrieve an uploaded image by token. Returns the image so you can see it
    with your vision capabilities. Use this to view photos/PDFs sent by Telegram users.

    Call this tool for each image token provided in the task instructions."""
    import base64
    from mcp.types import ImageContent, TextContent
    from app.services.temp_files import get_temp_file

    entry = get_temp_file(token)
    if not entry:
        return [TextContent(type="text", text=f"Error: image token '{token}' not found or expired.")]

    b64 = base64.b64encode(entry["data"]).decode()
    return [
        ImageContent(type="image", data=b64, mimeType=entry["media_type"]),
        TextContent(type="text", text=f"Image: {entry['filename']} ({len(entry['data'])} bytes)"),
    ]


@mcp.tool()
async def get_uploaded_excel(token: str) -> str:
    """Retrieve an uploaded Excel file by token. Parses the Excel and returns
    the data as JSON (rows with headers). Use this for Excel files sent by Telegram users.

    If parsing fails, returns error details. In that case, notify the user
    via notify_telegram explaining the issue."""
    from app.services.temp_files import get_temp_file

    entry = get_temp_file(token)
    if not entry:
        return json.dumps({"error": f"Token '{token}' not found or expired. The file may have been cleaned up (max 1 hour)."})

    try:
        from app.services.ai_extract import _extract_from_excel
        result = _extract_from_excel(entry["data"], entry["filename"])
    except Exception as e:
        return json.dumps({
            "error": f"Excel parsing error: {str(e)[:200]}",
            "filename": entry["filename"],
            "size": len(entry["data"]),
            "hint": "The file may be corrupted, password-protected, or in an unsupported format (.xls old format).",
        })

    if result and result.get("lines"):
        return json.dumps({
            "ok": True,
            "filename": entry["filename"],
            "items": result["lines"],
            "metadata": result.get("metadata", {}),
        }, ensure_ascii=False)

    return json.dumps({
        "error": "No data could be extracted from the Excel file.",
        "filename": entry["filename"],
        "size": len(entry["data"]),
        "hint": "The file may not contain a price list format (needs columns for product name and price). "
                "Try sending a screenshot of the relevant sheet instead.",
    })


def get_mcp_sse_app():
    """Return the MCP SSE Starlette app with proxy-friendly response headers."""
    sse_app = mcp.sse_app()

    async def sse_proxy_wrapper(scope, receive, send):
        if scope["type"] == "http":
            original_send = send

            async def patched_send(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-accel-buffering", b"no"))
                    headers.append((b"cache-control", b"no-cache, no-transform"))
                    message = {**message, "headers": headers}
                await original_send(message)

            await sse_app(scope, receive, patched_send)
        else:
            await sse_app(scope, receive, send)

    return sse_proxy_wrapper

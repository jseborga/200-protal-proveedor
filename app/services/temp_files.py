"""Almacenamiento temporal de archivos para enviar a Claude Code Routine.

Flujo:
1. Telegram descarga foto/PDF
2. Si es PDF → PyMuPDF convierte cada pagina a PNG
3. Se guarda en memoria con token aleatorio
4. Claude Code Routine llama al MCP tool `get_uploaded_image(token)` para ver la imagen
5. Auto-limpieza despues de 1 hora
"""

import io
import secrets
from datetime import datetime, timedelta

# In-memory store: token → {data: bytes, media_type: str, filename: str, created_at: datetime}
_temp_store: dict[str, dict] = {}
_MAX_AGE_SECONDS = 3600  # 1 hour
_MAX_ITEMS = 100


def save_temp_file(content: bytes, media_type: str, filename: str = "") -> str:
    """Save content and return a unique token."""
    _cleanup_expired()
    token = secrets.token_urlsafe(24)
    _temp_store[token] = {
        "data": content,
        "media_type": media_type,
        "filename": filename or token,
        "created_at": datetime.utcnow(),
    }
    # Evict oldest if too many
    if len(_temp_store) > _MAX_ITEMS:
        oldest = min(_temp_store, key=lambda k: _temp_store[k]["created_at"])
        del _temp_store[oldest]
    return token


def get_temp_file(token: str) -> dict | None:
    """Get temp file by token. Returns {data, media_type, filename} or None."""
    entry = _temp_store.get(token)
    if not entry:
        return None
    if datetime.utcnow() - entry["created_at"] > timedelta(seconds=_MAX_AGE_SECONDS):
        del _temp_store[token]
        return None
    return entry


def delete_temp_file(token: str):
    """Remove a temp file."""
    _temp_store.pop(token, None)


def _cleanup_expired():
    """Remove expired entries."""
    now = datetime.utcnow()
    expired = [
        t for t, e in _temp_store.items()
        if now - e["created_at"] > timedelta(seconds=_MAX_AGE_SECONDS)
    ]
    for t in expired:
        del _temp_store[t]


def pdf_to_images(content: bytes, max_pages: int = 10, dpi: int = 200) -> list[bytes]:
    """Convert PDF pages to PNG images using PyMuPDF.

    Returns list of PNG bytes, one per page (up to max_pages).
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=content, filetype="pdf")
    images = []
    for page_num in range(min(len(doc), max_pages)):
        page = doc[page_num]
        # Render at specified DPI (default 200 for good quality)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        images.append(pix.tobytes("png"))
    doc.close()
    return images


def save_media_for_routine(
    content: bytes, filename: str, source_type: str,
) -> list[dict]:
    """Process and save media for Claude Code Routine consumption.

    For photos: saves as-is.
    For PDFs: converts each page to PNG.
    For Excel: saves as-is (Routine processes via MCP tools, not vision).

    Returns list of {token, media_type, filename, page} dicts.
    """
    results = []

    if source_type == "pdf":
        try:
            images = pdf_to_images(content)
            for i, img_bytes in enumerate(images):
                token = save_temp_file(img_bytes, "image/png", f"{filename}_p{i+1}.png")
                results.append({
                    "token": token,
                    "media_type": "image/png",
                    "filename": f"{filename}_p{i+1}.png",
                    "page": i + 1,
                    "size": len(img_bytes),
                })
            print(f"[TempFiles] PDF '{filename}': {len(images)} pages converted to PNG")
        except Exception as e:
            print(f"[TempFiles] PDF conversion failed: {e}, saving raw")
            token = save_temp_file(content, "application/pdf", filename)
            results.append({
                "token": token,
                "media_type": "application/pdf",
                "filename": filename,
                "page": 0,
                "size": len(content),
            })
    elif source_type == "photo":
        token = save_temp_file(content, "image/jpeg", filename)
        results.append({
            "token": token,
            "media_type": "image/jpeg",
            "filename": filename,
            "page": 0,
            "size": len(content),
        })
    elif source_type == "excel":
        token = save_temp_file(content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename)
        results.append({
            "token": token,
            "media_type": "application/excel",
            "filename": filename,
            "page": 0,
            "size": len(content),
        })
    else:
        token = save_temp_file(content, "application/octet-stream", filename)
        results.append({
            "token": token,
            "media_type": "application/octet-stream",
            "filename": filename,
            "page": 0,
            "size": len(content),
        })

    return results

"""Helpers de busqueda textual tolerantes a espacios y orden de palabras."""

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement


def tokens(q: str | None) -> list[str]:
    """Normaliza la query: colapsa espacios, descarta tokens vacios y <=1 caracter."""
    if not q:
        return []
    return [t for t in q.strip().split() if len(t) >= 2]


def tokenized_ilike(column: ColumnElement, q: str | None) -> ColumnElement | None:
    """AND de ILIKE por cada token. Cada token puede aparecer en cualquier orden.

    Ejemplos:
      q="cemento portland"      -> col ILIKE '%cemento%' AND col ILIKE '%portland%'
      q="portland  cemento"     -> lo mismo
      q="cem"                   -> col ILIKE '%cem%'
      q=None / "" / " "         -> None (sin filtro)
    """
    toks = tokens(q)
    if not toks:
        return None
    return and_(*[column.ilike(f"%{t}%") for t in toks])


def tokenized_ilike_any(columns: list[ColumnElement], q: str | None) -> ColumnElement | None:
    """Cada token debe matchear en AL MENOS una de las columnas (OR), y todos los
    tokens deben matchear (AND)."""
    toks = tokens(q)
    if not toks:
        return None
    return and_(*[or_(*[c.ilike(f"%{t}%") for c in columns]) for t in toks])

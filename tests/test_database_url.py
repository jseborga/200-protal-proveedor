"""Tests para app.core.database._clean_url.

Verifica que:
- Remueve `sslmode` (asyncpg no lo acepta)
- No corrompe URLs de sqlite (bug histórico con urlparse/urlunparse)
- Preserva otros parámetros de query string
- Short-circuit cuando no hay query string
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")

from app.core.database import _clean_url


class TestSqliteUrls:
    def test_sqlite_memory_unchanged(self):
        u = "sqlite+aiosqlite:///:memory:"
        assert _clean_url(u) == u

    def test_sqlite_relative_unchanged(self):
        u = "sqlite+aiosqlite:///./test.db"
        assert _clean_url(u) == u

    def test_sqlite_absolute_unchanged(self):
        u = "sqlite+aiosqlite:////var/data/app.db"
        assert _clean_url(u) == u

    def test_sqlite_sync_unchanged(self):
        u = "sqlite:///data.db"
        assert _clean_url(u) == u


class TestSslmodeRemoval:
    def test_sslmode_only(self):
        assert _clean_url("postgresql+asyncpg://u:p@h/db?sslmode=require") \
            == "postgresql+asyncpg://u:p@h/db"

    def test_sslmode_with_other_params(self):
        assert _clean_url("postgresql+asyncpg://u:p@h/db?sslmode=require&foo=bar") \
            == "postgresql+asyncpg://u:p@h/db?foo=bar"

    def test_other_param_before_sslmode(self):
        assert _clean_url("postgresql+asyncpg://u:p@h/db?foo=bar&sslmode=disable") \
            == "postgresql+asyncpg://u:p@h/db?foo=bar"

    def test_sslmode_removed_from_plain_postgres(self):
        assert _clean_url("postgresql://u:p@h/db?sslmode=require") \
            == "postgresql://u:p@h/db"


class TestPassthrough:
    def test_no_query_string_returned_as_is(self):
        u = "postgresql+asyncpg://u:p@h:5432/db"
        assert _clean_url(u) == u

    def test_preserves_unrelated_params(self):
        u = "postgresql+asyncpg://u:p@h/db?foo=bar&baz=qux"
        out = _clean_url(u)
        # Orden puede variar pero ambos params deben estar
        assert out.startswith("postgresql+asyncpg://u:p@h/db?")
        assert "foo=bar" in out
        assert "baz=qux" in out

    def test_empty_query_after_removal_drops_question_mark(self):
        # Si sólo había sslmode, el '?' final desaparece
        assert _clean_url("postgresql://u@h/db?sslmode=require") \
            == "postgresql://u@h/db"

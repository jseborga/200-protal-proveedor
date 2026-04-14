-- Extensiones necesarias
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Indice GIN para matching por trigrama (se crea despues de las tablas via Alembic)
-- CREATE INDEX IF NOT EXISTS idx_mkt_insumo_name_trgm ON mkt_insumo USING gin (normalized_name gin_trgm_ops);

---
name: enrich-suppliers
description: Enriquecer datos de proveedores (whatsapp, direcciones, coords, sucursales, contactos comerciales) via busqueda web y subir en batch via MCP. Uso tipico "/enrich-suppliers 30" o "/enrich-suppliers departamento=Santa Cruz 20".
---

# Skill: enrich-suppliers

Flujo para enriquecer proveedores con datos externos (Google Maps, sitios oficiales, redes sociales) y subir los cambios en batch via MCP server `apu-marketplace`.

## Argumentos

- `N` (int, default 30): cuantos proveedores procesar en el lote. Max recomendado 30.
- Filtros opcionales: `department=X`, `city=Y`, `category=Z`, `offset=N`, `only_missing=whatsapp|coords|address`
- `dry-run` (flag): generar JSON sin hacer upsert.

## Fase 1 — Seleccionar lote

1. Llamar `list_suppliers(limit=N, department=..., city=..., category=...)`.
2. Si hay filtro `only_missing=...`, filtrar localmente proveedores sin ese campo.
3. Barrido total: usar `offset` para siguientes lotes. Mantener indice de lotes procesados en `data/enrichment/_index.json`.

## Fase 2 — Enriquecer cada proveedor

Para cada proveedor, ejecutar busquedas en paralelo cuando sea posible:

### Queries a probar (en orden de confianza)
1. **Sitio oficial**: WebSearch `"<name>" "<city>" Bolivia sitio oficial` → WebFetch del primer resultado `.bo` o dominio propio.
2. **Google Maps**: WebSearch `"<name>" "<city>" google maps` → extraer direccion, telefono, coords, sucursales listadas.
3. **Facebook/Instagram**: WebSearch `"<name>" Bolivia facebook` → extraer whatsapp, email de contacto.
4. **Paginas amarillas / directorios**: si los anteriores fallan.

### Datos a extraer
- **Supplier root**: `whatsapp`, `phone`, `email`, `website`, `address` (HQ), `latitude`, `longitude`, `description` corta (1-2 lineas sobre que hace).
- **Branches**: cada sucursal con `branch_name`, `city`, `department`, `address`, `latitude`, `longitude`, `phone`, `whatsapp`, `email`, `is_main` (true para HQ).
- **Branch contacts** (personas): `branch_id` (post-upsert de la sucursal), `full_name`, `position` (gerente, vendedor, etc.), `whatsapp`, `email`, `is_primary`.

### Scoring de confianza (0-100)
- +40 si coincide dato entre 2+ fuentes independientes (ej: whatsapp en sitio oficial Y Google Maps).
- +30 si fuente es sitio oficial del proveedor (.bo o dominio propio).
- +20 si Google Maps tiene la ficha verificada.
- +10 por cada fuente extra concordante.
- Maximo 100. **Auto-upsert si confianza >= 70**. Si < 70, marcar `needs_review: true`.

## Fase 3 — Consolidar en JSON

Escribir a `data/enrichment/suppliers_<YYYYMMDD>_<batch_n>.json`:

```json
{
  "batch_id": "suppliers_20260417_001",
  "generated_at": "2026-04-17T18:00:00",
  "total": 30,
  "auto_confident": 18,
  "needs_review": 12,
  "items": [
    {
      "supplier_id": 123,
      "current": {"name": "...", "whatsapp": null, "address": null, "latitude": null},
      "enriched": {
        "supplier": {"whatsapp": "59177889900", "address": "Av. X #123", "latitude": -17.78, "longitude": -63.18, "website": "...", "email": "..."},
        "branches": [
          {"branch_name": "Casa Matriz", "city": "Santa Cruz", "is_main": true, "latitude": -17.78, "longitude": -63.18, "whatsapp": "59177889900"},
          {"branch_name": "Sucursal La Paz", "city": "La Paz", "latitude": -16.5, "longitude": -68.15}
        ],
        "contacts": [
          {"branch_name": "Casa Matriz", "full_name": "Juan Perez", "position": "Gerente Ventas", "whatsapp": "59177...", "is_primary": true}
        ]
      },
      "confidence": 85,
      "auto_apply": true,
      "sources": ["https://sitio-oficial.bo/contacto", "https://maps.google.com/?q=..."]
    }
  ]
}
```

## Fase 4 — Batch upsert

Si NO es `dry-run`:

1. **Auto-confident** (`confidence >= 70`): aplicar sin preguntar.
2. **Needs review**: mostrar tabla resumida al usuario, esperar OK por lote (no item por item).

### Orden de llamadas MCP
Por cada supplier que se va a aplicar:
1. `update_supplier(supplier_id, whatsapp=..., address=..., latitude=..., longitude=..., website=..., email=..., description=...)` — solo campos con valor nuevo.
2. Por cada branch → `upsert_supplier_branch(supplier_id, branch_name, ...)` → capturar `branch_id` retornado.
3. Por cada contact cuyo `branch_name` matchea → `upsert_branch_contact(branch_id, full_name, ...)`.

Respetar la regla **MCP upsert** (memoria): nunca borrar+recrear, siempre upsert.

Si una llamada MCP falla, registrar en el JSON bajo `errors` y continuar con el siguiente supplier. **No abortar el lote.**

## Fase 5 — Reporte final

Al terminar:
- Actualizar `data/enrichment/_index.json` con el batch procesado.
- Imprimir resumen: `X auto-aplicados, Y pendientes de review, Z errores`.
- Listar supplier IDs que necesitan revision manual.

## Reglas generales

- **Idempotencia**: si ya existe el mismo dato, no hacer update (waste MCP call). Comparar `current` vs `enriched`.
- **No sobrescribir con null**: si el enriquecimiento no encontro algo y el actual lo tiene, mantener el actual.
- **Formato whatsapp**: siempre con codigo pais `591...`, sin espacios ni guiones.
- **Coords**: latitud negativa para Bolivia (~-10 a -22), longitud negativa (~-57 a -70). Validar rango antes de guardar.
- **Sucursales**: `branch_name` debe ser unico por supplier. "Casa Matriz" o "Oficina Central" para la principal.
- **Rate limit**: si WebSearch empieza a fallar, pausar 30s y reintentar. Si persiste, escribir el batch parcial y reportar.
- **Dry-run**: siempre ofrecer como primera opcion si el lote es >20 items.

## Ejemplo de invocacion

```
/enrich-suppliers 25 department=Santa Cruz only_missing=whatsapp
```

Respuesta esperada: "Procesando 25 proveedores de Santa Cruz sin whatsapp. Generando batch en `data/enrichment/suppliers_20260417_003.json`..."

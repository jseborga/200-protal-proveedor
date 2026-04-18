---
name: enrich-product-images
description: Buscar imagenes representativas de productos (materiales de construccion) via web y subir URLs en batch via MCP. Uso tipico "/enrich-product-images 40" o "/enrich-product-images category=Cemento 30".
---

# Skill: enrich-product-images

Flujo para encontrar URLs de imagenes representativas de productos del catalogo y subirlas en batch via MCP server `apu-marketplace` usando `set_product_image`.

## Argumentos

- `N` (int, default 40): cuantos productos procesar. Max recomendado 50.
- Filtros opcionales: `category=X`, `offset=N`, `only_missing=true` (solo productos sin `image_url`, default true).
- `dry-run` (flag): generar JSON sin upsert.

## Fase 1 — Seleccionar lote

1. `list_products(limit=N, category=...)`.
2. Filtrar local: si `only_missing=true`, quedarse solo con los que tienen `image_url` null/vacio.
3. Mantener `data/enrichment/_images_index.json` con productos ya procesados.

## Fase 2 — Buscar imagen por producto

Para cada producto, WebSearch con queries en orden:

1. `"<name>" <category> Bolivia imagen producto`
2. `"<name>" <category> specification image`
3. `<name> <uom> producto construccion` (si no hay category)

**Prioridad de fuentes**:
1. Sitios de fabricantes/distribuidores (ej: cementoviacha.com, soboce.com).
2. Ecommerce confiable (mercadolibre, amazon) — solo la URL de la imagen, no del producto.
3. Wikipedia / commons.
4. Stock photos (ultimo recurso).

**NO usar**:
- Imagenes con marca de agua.
- Imagenes < 200x200 px.
- URLs que requieren auth o cookies.
- URLs que parecen temporales (query strings con tokens).

## Fase 3 — Validar la URL

Antes de guardar, verificar con WebFetch (HEAD request si es posible) o fetch simple:
- Responde 200 OK.
- Content-Type es `image/*`.
- URL estable (no tiene tokens efimeros en query string).

Si falla, probar la siguiente query. Si todas fallan, marcar `image_url: null, needs_manual: true`.

## Fase 4 — Scoring de confianza

- +50 si la imagen viene de sitio del fabricante (matchea la marca en el nombre).
- +30 si es de ecommerce reconocido.
- +20 si el alt text / contexto menciona el producto exacto.
- +10 si es de wikipedia/commons.
- **Auto-upsert si confianza >= 60** (umbral mas bajo que suppliers porque imagenes son menos criticas y facilmente reemplazables).

## Fase 5 — Consolidar JSON

Escribir a `data/enrichment/images_<YYYYMMDD>_<batch_n>.json`:

```json
{
  "batch_id": "images_20260417_001",
  "generated_at": "2026-04-17T18:00:00",
  "total": 40,
  "auto_confident": 32,
  "needs_review": 5,
  "failed": 3,
  "items": [
    {
      "product_id": 456,
      "product_name": "Cemento Portland IP-30 bolsa 50kg",
      "current_image_url": null,
      "new_image_url": "https://soboce.com/.../cemento-ip30.jpg",
      "description_update": "Cemento Portland IP-30 de SOBOCE, bolsa 50kg, uso estructural",
      "confidence": 85,
      "auto_apply": true,
      "source_page": "https://soboce.com/productos/cemento-ip30",
      "query_used": "\"Cemento Portland IP-30\" Cemento Bolivia imagen producto"
    }
  ]
}
```

## Fase 6 — Batch upsert

Para cada item con `auto_apply: true`:
- `set_product_image(product_id, image_url=new_image_url, description=description_update or "")`.

Para `needs_review`: mostrar tabla al usuario con thumbnails (si es posible) y esperar OK por lote.

Si una llamada falla, registrar y continuar.

## Fase 7 — Reporte final

- Actualizar `data/enrichment/_images_index.json`.
- Resumen: `X imagenes aplicadas, Y en review, Z fallaron`.
- Lista de `product_id` que necesitan revision manual.

## Reglas generales

- **No sobrescribir imagen existente sin preguntar**: si `current_image_url` no es null, solo aplicar si confianza es muy alta (>= 85) Y el usuario lo autorizo con `overwrite=true`.
- **Description update**: solo actualizar `description` si el producto actual NO tiene descripcion o la tiene muy corta (< 30 chars). Nunca sobrescribir descripciones largas.
- **URLs https**: preferir https siempre. Rechazar http puro.
- **Rate limit**: si WebSearch satura, pausar 30s. Si persiste, escribir batch parcial.
- **No usar imagenes con derechos de autor explicitos**: evitar stock de getty, shutterstock (marcadas con watermark).

## Ejemplo

```
/enrich-product-images 30 category=Cemento
```

Respuesta esperada: "Buscando imagenes para 30 productos de categoria Cemento. Generando `data/enrichment/images_20260417_002.json`..."

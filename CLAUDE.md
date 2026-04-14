# APU Marketplace — Portal de Proveedores y Precios de Construccion

## Que es este proyecto
Plataforma independiente (no Odoo) para:
1. **Portal publico de precios unitarios** de construccion por region (Bolivia inicialmente)
2. **Portal de proveedores** donde suben cotizaciones (web, Excel, PDF, foto, WhatsApp, Telegram)
3. **API REST** que cualquier ERP (Odoo, SAP, etc.) puede consumir para sincronizar precios
4. **Motor de matching semantico** que vincula nombres de proveedor con insumos estandarizados
5. **Analisis estadistico** de precios con validacion humana antes de actualizar la base

## Stack tecnologico
- **Backend**: FastAPI (Python 3.12+)
- **DB**: PostgreSQL 16 con pg_trgm para matching
- **ORM**: SQLAlchemy 2.0 + Alembic (migraciones)
- **Auth**: JWT (jose) + API keys para integraciones
- **Frontend**: SPA vanilla JS (similar al portal B-APU existente) → PWA
- **WhatsApp**: Evolution API (self-hosted, Docker)
- **Telegram**: Bot API oficial
- **AI Extraction**: OpenRouter / Anthropic / OpenAI / Gemini (configurable)
- **Deploy**: Docker Compose → EasyPanel (Docker Swarm)

## Estructura del proyecto
```
200-protal-proveedor/
├── app/                    # Backend FastAPI
│   ├── main.py             # App entry point
│   ├── core/               # Config, DB, security
│   │   ├── config.py       # Settings desde .env
│   │   ├── database.py     # SQLAlchemy engine + session
│   │   └── security.py     # JWT + API key auth
│   ├── models/             # SQLAlchemy models
│   │   ├── base.py         # Base declarativa
│   │   ├── supplier.py
│   │   ├── quotation.py
│   │   ├── insumo.py
│   │   ├── price.py
│   │   ├── rfq.py
│   │   └── match.py
│   ├── api/                # Routers FastAPI
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   ├── suppliers.py
│   │   │   ├── quotations.py
│   │   │   ├── prices.py
│   │   │   ├── rfq.py
│   │   │   ├── webhooks.py
│   │   │   └── admin.py
│   │   └── deps.py         # Dependencias comunes
│   └── services/           # Logica de negocio
│       ├── ai_extract.py   # Extraccion de datos con IA
│       ├── matching.py     # Motor matching semantico
│       ├── messaging.py    # WhatsApp + Telegram + Email
│       └── pricing.py      # Analisis estadistico
├── frontend/               # SPA frontend
│   ├── public/
│   │   ├── index.html
│   │   ├── manifest.json   # PWA manifest
│   │   └── sw.js           # Service worker
│   └── src/
│       ├── assets/
│       │   ├── app.js      # SPA principal
│       │   └── app.css
│       ├── components/
│       └── pages/
├── migrations/             # Alembic migrations
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
├── tests/
├── scripts/
├── .env                    # Variables de entorno (NO commitear)
├── .env.example            # Template de .env
├── docker-compose.yml      # Dev + Prod
├── Dockerfile
├── pyproject.toml
└── CLAUDE.md
```

## Convenciones
- Python: snake_case, type hints, docstrings breves
- SQL: tablas con prefijo `mkt_` (ej: `mkt_supplier`, `mkt_quotation`)
- API: RESTful, respuestas `{ok: bool, data: ..., error: ...}`
- Frontend: vanilla JS, CSS custom, sin frameworks pesados
- Git: conventional commits en espanol
- Idioma del codigo: ingles para nombres tecnicos, espanol para strings de UI

## Integraciones externas
- **Evolution API** (WhatsApp): self-hosted en Docker, webhook a `/api/v1/webhook/whatsapp`
- **Telegram Bot API**: webhook a `/api/v1/webhook/telegram`
- **OpenRouter**: API key en .env, soporta Claude/GPT/Gemini via un solo endpoint
- **SMTP**: para emails transaccionales (confirmacion registro, notificaciones)

## Deploy
- EasyPanel en servidor propio (Docker Swarm)
- GitHub repo para CI/CD
- Docker Compose con servicios: app, postgres, evolution-api
- Variables sensibles en EasyPanel (no en repo)

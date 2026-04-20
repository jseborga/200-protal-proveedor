# Conversation Hub — Estado del proyecto

Documento de continuidad para el hub de conversaciones cliente <-> operador.
Ultima actualizacion: **2026-04-20**.

---

## 1. Que es

Sistema que unifica en una sola sesion (`mkt_conversation_session`) la
conversacion de un cliente por WhatsApp (Evolution API) con el equipo interno
por Telegram (Forum Topics), y una vista web tipo ManyChat (`Inbox`).

Cada **Pedido** puede tener una sesion asociada. La sesion:

- Guarda el `client_phone`, `client_user_id`, `operator_id`, `tg_group_id`,
  `tg_topic_id`, y el estado (`waiting_first_contact`, `active`,
  `operator_engaged`, `quote_sent`, `closed`).
- Registra todos los mensajes en `mkt_conversation_message` (direction,
  channel, sender_type, body, media_*).
- Trackea `last_client_msg_at` y `last_operator_msg_at` para validar la
  ventana 24h de WhatsApp y el estado "no leido".

Modulos clave:

- `app/models/conversation.py` — `ConversationSession`, `Message`.
- `app/services/conversation_hub.py` — bridging (`mirror_client_to_topic`,
  `mirror_operator_to_client`, `deliver_quote_to_client`,
  `close_session_for_pedido`, `is_wa_window_open`).
- `app/services/messaging.py` — primitivos WA/TG/Email + comandos de operador.
- `app/api/routes/inbox.py` — API del inbox web.
- `frontend/public/assets/app.js` — UI del inbox (`renderInbox`, state `_inbox`).

---

## 2. Fase 1 — Pipeline cliente <-> operador

Completada. Lo que entrega:

### 2.1 Flujo basico
- Cliente escribe a WhatsApp -> crea/reactiva sesion -> se crea/reutiliza un
  **topic de Telegram** en el grupo interno -> el equipo responde en el topic
  y el mensaje se envia al WA del cliente via
  `mirror_operator_to_client`.
- Toda interaccion queda en `Message` con `direction`, `channel`, `body`,
  `media_*`.

### 2.2 Media relay WA -> TG
- Fotos, audios, documentos y videos enviados por el cliente se descargan
  desde Evolution API (`/chat/getBase64FromMediaMessage/{instance}`) y se
  reenvian al topic como `sendPhoto`/`sendDocument`/`sendAudio`/`sendVideo`
  via `send_telegram_media_bytes_to_topic`.
- Nota: el relay TG -> WA de media **no** esta implementado aun (pendiente).

### 2.3 Comandos del operador en el topic
- `/cerrar` — cierra la sesion.
- `/ayuda` — lista de comandos.

### 2.4 Entrega de cotizacion
- Boton **"Entregar cotizacion"** en el detalle del pedido completado.
  Llama a `deliver_quote_to_client` y devuelve `mode`:
  - `whatsapp` — enviado por WA.
  - `email` — fallback SMTP si la ventana 24h esta cerrada y hay email.
  - `window_closed`, `no_phone`, `no_session` — diagnosticos.

### 2.5 Cierre al completar pedido
- `POST /pedidos/{id}/complete` llama a `close_session_for_pedido`.

### 2.6 Reorganizacion de menu
- "Mis Pedidos" -> **"Cotizaciones"** (clave interna `pedidos` sin cambios).
- RFQ removido del nav principal.
- Ingestion antigua de cotizaciones: **Admin -> Catalogo -> "Importar precios"**.

---

## 3. Fase 2 — Inbox web (ManyChat-like)

Completada. Ruta: `staffPages.inbox` -> `/inbox`.

### 3.1 Hito A — Read-only
- Layout 2 paneles (lista + timeline) con polling cada 10s.
- Badge de estado + badge de ventana WA (24h restantes).
- Timeline con burbujas diferenciadas (cliente, operador, bot, sistema).

### 3.2 Hito B — Composer
- Textarea + boton Enviar, Enter envia, Shift+Enter nueva linea.
- Respeta ventana 24h: deshabilita el composer cuando esta cerrada.
- Espejo automatico al topic TG con prefijo `Web . <nombre>`.
- Endpoint: `POST /api/v1/inbox/sessions/{id}/send`.

### 3.3 Hito C — Filtros + busqueda + no-leidas
- **Search** por referencia de pedido, titulo, telefono, nombre, email (JOIN
  con `mkt_pedido` + `mkt_user`, `ilike`, debounce 300ms).
- **Toggle "Solo no leidas"** (`last_client_msg_at > last_operator_msg_at` o
  sin respuesta).
- **Badge rojo** en cabecera con total de pendientes globales.
- Items con fondo ambar + dot naranja + negrita cuando hay pendiente.
- Contador de sesiones bajo los controles.

---

## 4. Fase 3 — Asignacion de operador

Completada hoy (**2026-04-20**, commit `f8319bc`).

### 4.1 Backend — nuevos endpoints
- `POST /api/v1/inbox/sessions/{id}/claim` — staff reclama. Si la sesion ya
  esta asignada a otro staff: devuelve `{ok: false, conflict: true, ...}`
  salvo que el que llama sea `admin`/`superadmin`/`manager`.
- `POST /api/v1/inbox/sessions/{id}/release` — solo el operador actual o
  manager/admin. Deja `operator_id = NULL`.
- `POST /api/v1/inbox/sessions/{id}/assign` — manager/admin asigna a
  cualquier staff activo (body: `{operator_id: int | null}`).
- `GET /api/v1/inbox/operators` — lista staff activo (nombre, email, role)
  para el dropdown de asignacion.

### 4.2 Backend — list_sessions extendido
- Nuevo query param `assigned=mine|unassigned|<user_id>`.
- Cada item del listado trae ahora `operator_name`, `operator_email`,
  `last_operator_msg_at`, `unread`.
- La respuesta incluye `unread_count` global (sesiones abiertas pendientes)
  independiente de filtros.

### 4.3 Frontend
- Nuevo selector **"Mias / Sin asignar / Cualquier"** junto al buscador.
- Badge de operador en cada item: `Tu` azul si soy yo, nombre violeta si es
  otro, `Sin asignar` ambar.
- En el header del pane, segun rol/estado:
  - Sin asignar -> boton **Reclamar** (todos).
  - Asignada a mi -> boton **Liberar**.
  - Asignada a otro + soy manager -> botones **Tomar** y **Liberar**.
  - Manager siempre ve **Asignar...** (modal con dropdown de staff).

---

## 5. Lo que falta

### 5.1 Relay TG -> WA de media (riesgo medio)
El cliente puede enviar fotos/audio a WA y se ven en TG, pero lo inverso no
funciona: si el operador envia una foto en el topic, no llega al cliente por
WA. Falta:
- Detectar media en el webhook de Telegram (`message.photo`, `document`,
  `voice`, `audio`, `video`).
- Descargar el archivo via `getFile` de TG Bot API.
- Enviarlo al cliente por Evolution API (`/message/sendMedia/{instance}` con
  base64).
- Registrar el mensaje en `Message` con `media_type` + `media_url`.

### 5.2 Metricas / SLA (riesgo bajo)
Dashboard read-only con:
- Tiempo primera respuesta promedio por operador (diferencia entre primer
  `inbound` y primer `outbound` de tipo operator).
- Tiempo total de resolucion (hasta `state=closed`).
- Sesiones abiertas por operador.
- Sesiones sin responder > N horas (SLA breach).
- Volumen por canal/dia.

### 5.3 Notas / internal comments (riesgo bajo)
Tipo `sender_type="system"` pero visible solo en la web (no se propaga ni a
TG ni a WA). Util para handoff entre operadores.

### 5.4 Plantillas de respuesta rapida (riesgo bajo)
Tabla `mkt_inbox_template` con `title`, `body`, `scope` (global/personal).
Panel flotante en el composer para elegir una plantilla.

### 5.5 Notificaciones push al operador (riesgo medio)
Web Push / browser notification cuando llega un mensaje del cliente a una
sesion asignada al operador actual. Requiere service worker + suscripcion
VAPID.

### 5.6 Marcado explicito de "leido" (riesgo bajo)
Hoy "no leido" se calcula por timestamps. Podria agregarse una marca
explicita `operator_last_read_at` por sesion para que el badge no desaparezca
al enviar respuesta, sino al abrir la sesion.

### 5.7 Reglas de auto-asignacion (riesgo medio)
Round-robin entre operadores activos cuando llega un nuevo cliente, con
carga balanceada. Configurable por grupo/region.

---

## 6. Como levantar localmente

```bash
cp .env.example .env
# editar .env con DB, Evolution API, TG bot, SMTP, OpenRouter
docker compose -f docker-compose.dev.yml up
# migraciones
docker compose exec app alembic upgrade head
```

Endpoints clave para humo-testear el inbox:
- `GET /api/v1/inbox/sessions?state=open`
- `POST /api/v1/inbox/sessions/{id}/send` con `{"text": "hola"}`
- `POST /api/v1/inbox/sessions/{id}/claim`

---

## 7. Commits relevantes

| commit    | tema                                                       |
|-----------|------------------------------------------------------------|
| `24b819a` | Conversation Hub Fase 1 inicial                            |
| `11c658e` | Admin UI para Conversation Hub                             |
| `b22fa3e` | Fase 1 gaps + nav reorg + Inbox hitos A/B                  |
| `0e5bcfc` | Inbox hito C (busqueda + no-leidas + contador)             |
| `f8319bc` | Asignacion de operador (claim/release/assign)              |

---

## 8. Decisiones y reglas ya aplicadas (no re-discutir)

- La clave interna del nav se mantiene `pedidos` aunque el label sea
  "Cotizaciones" para no romper `navigate('pedidos')`.
- "Importar precios" vive dentro de Admin -> Catalogo, no en el nav principal.
- El modelo NO tiene campo `operator_last_read_at`: el "no leido" se deriva
  de timestamps. Cambiar esto implica migracion (ver 5.6).
- EasyPanel + BuildKit puede fallar con `No such image: ...:latest` al
  arrancar si no tiene containerd image store. Fix recomendado:
  `/etc/docker/daemon.json` -> `{"features":{"containerd-snapshotter":true}}`.

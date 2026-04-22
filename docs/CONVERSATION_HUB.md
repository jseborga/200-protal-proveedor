# Conversation Hub — Estado del proyecto

Documento de continuidad para el hub de conversaciones cliente <-> operador.
Ultima actualizacion: **2026-04-22** (Fase 5.10 auto-handoff por timeout SLA breach).

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
- El relay inverso TG -> WA de media ya esta implementado: ver Fase 5.1
  (`app/services/messaging.py` usa `_download_telegram_file` +
  Evolution API para reenviar al cliente).

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

## 5. Fase 5 — Operacion avanzada del inbox

### 5.1 Relay TG -> WA de media — **DONE**
Commit previo. El operador puede enviar fotos/audios/documentos/videos desde
el topic de Telegram y se entregan al cliente por Evolution API con el
Message correspondiente en DB (`media_type`, `media_url`).

### 5.2 Metricas / SLA — **DONE**
- Endpoint `GET /api/v1/inbox/metrics?days=7&sla_hours=1`:
  - `open_sessions`, `open_unassigned`, `open_assigned`.
  - `pending_response`, `sla_breach` (usando `sla_hours`).
  - `first_response_avg_seconds` (primer `inbound` vs primer `outbound`
    con `sender_type='operator'`).
  - `resolution_avg_hours` sobre sesiones cerradas en la ventana.
  - `volume_by_day` (inbound por dia).
  - `by_operator` con `open`, `closed_in_window`, `first_response_avg_seconds`.
- UI: boton **"Metricas / SLA"** en el header del inbox abre un modal con
  KPI cards + tabla por operador + barras de volumen diario.
- Tests: `tests/test_inbox_metrics.py` (9 casos).

### 5.3 Notas internas — **DONE**
- Mensaje en `Message` con `sender_type='note'`, `channel='web'`,
  `direction='internal'`. No se propaga a TG ni a WA por el hub (los bridging
  filtran por canal/direccion).
- Endpoint: `POST /api/v1/inbox/sessions/{id}/note` body `{"text": "..."}`.
  El body se guarda prefijado con `[<nombre_operador>]`.
- UI: boton **"Nota"** en el composer pide el texto con `prompt()` y lo
  renderiza con estilo distintivo (fondo ambar + italica, centrado).
- Tests: ver `TestInternalNotes` en
  `tests/test_inbox_notes_templates_read.py`.

### 5.4 Plantillas de respuesta rapida — **DONE**
- Modelo `InboxTemplate` (tabla `mkt_inbox_template`):
  `title`, `body`, `scope` (`global|personal`), `owner_id`.
- Endpoints: `GET/POST/PUT/DELETE /api/v1/inbox/templates`. RBAC:
  - `global`: solo `manager/admin/superadmin` pueden crear/editar/eliminar.
  - `personal`: solo el `owner` puede editar/eliminar; al listar se ven
    todas las globales + las propias del usuario.
- UI: boton **"Plantillas"** en el composer abre modal con picker + gestor
  (crear, editar, borrar). Al elegir una, el texto se inserta en el textarea.
- Tests: `TestTemplatesList`, `TestTemplatesCreate`, `TestTemplatesUpdate`,
  `TestTemplatesDelete`.

### 5.5 Notificaciones push del escritorio — **DONE (Web Push + VAPID)**
Implementacion completa con **Service Worker + VAPID + suscripciones
persistidas** en DB, con fallback gradual a Web Notifications API si el
servidor no tiene claves VAPID configuradas.

**Backend**
- Config (`app/core/config.py`): `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`,
  `VAPID_SUBJECT` (default `mailto:admin@localhost`).
- Modelo `PushSubscription` (`app/models/push_subscription.py`, tabla
  `mkt_push_subscription`): `user_id`, `endpoint` (unique), `p256dh`, `auth`,
  `user_agent`, `created_at`, `last_used_at`.
- Service `app/services/webpush.py`:
  - `send_push_to_user(db, user_id, payload)` envia a todas las subs del
    usuario via `pywebpush`; devuelve delivered count.
  - Purga subs expiradas (HTTP 404/410) y actualiza `last_used_at` en exitos.
  - No-op si `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` vacios.
- Endpoints en `app/api/routes/inbox.py`:
  - `GET /api/v1/inbox/push/vapid-public-key` -> `{enabled, public_key}`.
  - `POST /api/v1/inbox/push/subscribe` body `{endpoint, keys:{p256dh,auth}, user_agent?}`.
    Upsert por `endpoint` (reusa fila si ya existe) + reasigna owner.
  - `POST /api/v1/inbox/push/unsubscribe` body `{endpoint}`. Owner o manager+.
  - `POST /api/v1/inbox/push/test` envia un push de prueba al caller.
- Hook en `app/services/messaging.py`: al terminar `mirror_client_to_topic`,
  si la sesion tiene `operator_id` se dispara `send_push_to_user` con titulo
  `Inbox · <phone>`, body = preview del mensaje (140 chars) y
  `{url:'/#inbox', session_id}`. Errores se loggean sin romper el flujo WA.

**Frontend**
- Service Worker: `frontend/public/assets/inbox-sw.js`.
  - `push` event: muestra `Notification` con `tag=inbox-<session_id>`,
    icon/badge `/assets/icon-192.png`, `renotify:true`.
  - `notificationclick`: enfoca pestana existente y postMessage
    `{type:'inbox-open-session', session_id}`; si no hay, `openWindow(url)`.
- SPA (`frontend/public/assets/app.js`):
  - `toggleInboxNotifications()` pide permiso, llama a
    `_inboxRegisterWebPush()` que:
    1. GET `/inbox/push/vapid-public-key` -> si `enabled:false`, retorna
       'local' (modo solo Notifications API como antes).
    2. Registra `/assets/inbox-sw.js`, `pushManager.subscribe` con
       `applicationServerKey` (helper `_urlBase64ToUint8Array`).
    3. POST `/inbox/push/subscribe` con endpoint + keys. Guarda endpoint en
       `localStorage['inboxPushEndpoint']`.
  - `_inboxUnregisterWebPush()` hace `unsubscribe` del pushManager y POST
    `/inbox/push/unsubscribe`.
  - Boton **"Probar push"** en el header del inbox (solo visible cuando el
    toggle esta on) llama a `testInboxNotification` -> POST `/inbox/push/test`.
  - Listener `navigator.serviceWorker.addEventListener('message', ...)` para
    `inbox-open-session`: enfoca el inbox y `selectInboxSession(id)`.
  - Si VAPID no disponible, cae al comportamiento previo (Notifications API
    con polling + tab abierta).

**Generacion de claves VAPID**
- Script `scripts/generate_vapid_keys.py` usa `cryptography` (SECP256R1) y
  emite claves URL-safe base64 listas para `.env`.

**Tests**
- `tests/test_inbox_webpush.py` (11 casos): key publica
  disponible/no-disponible, subscribe/upsert/validacion, unsubscribe con
  RBAC (owner, unknown, non-owner 403, manager puede cualquiera), test
  endpoint sin VAPID = delivered:0, y auth requerida en los 4 endpoints.

### 5.6 Marcado explicito de "leido" — **DONE**
- Nueva columna `operator_last_read_at` (`DateTime` nullable) en
  `mkt_conversation_session`.
- `_is_unread(session)` ahora considera: si `operator_last_read_at >=
  last_client_msg_at`, la sesion se considera leida aunque no haya
  respondido el operador. El filtro `unread_only`, el `unread_count` global
  del header y las metricas de `pending_response`/`sla_breach` usan la misma
  regla.
- Endpoint: `POST /api/v1/inbox/sessions/{id}/mark-read`.
- UI:
  - Boton **"Leido"** en el composer (silencioso).
  - Auto mark-read al abrir una sesion (`loadInboxSession` con `{silent:true}`).
- Fix relacionado: helper `_as_utc()` para comparar timestamps mezclando
  aware/naive (SQLite).
- Tests: `TestMarkRead` en `tests/test_inbox_notes_templates_read.py`.

### 5.7 Reglas de auto-asignacion — **DONE**
Round-robin o least-loaded entre operadores activos cuando llega un nuevo
cliente, configurable por manager. Se dispara al **primer mensaje
inbound** del cliente en `handle_whatsapp_message` (tras
`mirror_client_to_topic`), no al crear la sesion; asi no se reservan
operadores para sesiones que quiza nunca reciban un mensaje.

**Backend**
- Service `app/services/inbox_autoassign.py`:
  - `get_config(db)` / `save_config(db, cfg)` sobre
    `SystemSetting(key='inbox_autoassign')` con normalizacion
    (strategy ∈ {round_robin, least_loaded}).
  - `_get_eligible_operators(db, pool_ids)`: staff con `role in STAFF_ROLES`
    + `is_active`. Si `pool_user_ids` vacio -> todos los staff activos.
  - `_pick_round_robin(eligible, last_id)`: siguiente por id > last_id,
    con wrap-around al primero.
  - `_pick_least_loaded(db, eligible)`: operador con menor conteo de
    sesiones `state != 'closed'`; desempate estable por id asc.
  - `auto_assign_if_needed(db, session)`: no-op si ya hay operador o
    `enabled=false`; en exito asigna, inserta `Message` de sistema
    (`direction='internal'`, `channel='web'`, `sender_type='system'`,
    body `"Auto-asignado a <nombre> (<strategy>)."`) y actualiza el
    cursor `last_assigned_user_id`.
- Hook en `app/services/messaging.py` tras `mirror_client_to_topic`:
  si `session.operator_id` es NULL, llama a `auto_assign_if_needed`;
  el webpush posterior (5.5) encuentra el operator_id recien asignado
  y notifica al operador.
- Endpoints `app/api/routes/admin.py` (require_manager):
  - `GET /api/v1/admin/inbox-autoassign` devuelve la config normalizada
    + `strategies` validos + lista `operators` de staff activo con su
    `open_sessions` actual (util para que el manager decida).
  - `PUT /api/v1/admin/inbox-autoassign` body
    `{enabled, strategy, pool_user_ids}`. Valida que `pool_user_ids` sean
    staff activo; rechaza 400 con la lista de ids invalidos. Preserva el
    cursor round-robin existente.

**Frontend**
- `frontend/public/assets/app.js`:
  - Nuevas API helpers `inboxAutoAssignGet` / `inboxAutoAssignSave`.
  - Boton **"Auto-asignacion"** en el header del inbox, solo visible
    para manager+ (uso de `isManager()`).
  - `openInboxAutoAssign()` abre un modal con:
    - Checkbox "Auto-asignacion activa".
    - Radios estrategia (round_robin / least_loaded) con descripciones.
    - Lista scrollable de operadores con checkbox para pool + badge
      con `open_sessions` actual de cada uno.
    - Guarda via PUT; toast de exito.

**Tests**
- `tests/test_inbox_autoassign.py` (22 casos unitarios):
  - `TestConfig`: defaults, save+read, normalizacion de strategy invalida,
    upsert.
  - `TestRoundRobin`: vacio, primer pick, cursor siguiente, wrap-around,
    cursor fuera de rango.
  - `TestLeastLoaded`: vacio, conteo correcto filtrando closed, desempate
    estable por id asc.
  - `TestAutoAssignIfNeeded`: no-op cuando disabled / ya asignado / sin
    eligibles; asignacion exitosa + mensaje de sistema; cursor avanza en
    round-robin consecutivo; filtro de pool restringe al subset.
  - `TestEndpoints`: GET devuelve defaults + operators, PUT guarda,
    validacion rechaza user_ids no-staff (400), Pydantic rechaza strategy
    invalida (422).
- `tests/test_messaging_autoassign_integration.py` (5 casos de
  integracion, end-to-end desde `handle_whatsapp_message`):
  - `test_assigns_on_first_inbound_when_enabled`: con `enabled=True` +
    `round_robin`, el primer inbound WA a una sesion sin operador asigna
    al primer elegible y registra el Message de sistema "Auto-asignado".
  - `test_no_assignment_when_disabled`: `enabled=False` deja
    `operator_id=None` y no crea mensaje de sistema.
  - `test_no_reassignment_when_already_assigned`: sesion con operador
    preexistente no se reasigna (idempotencia).
  - `test_webpush_fires_with_newly_assigned_operator`: verifica que el
    hook webpush posterior recibe `user_id = operador recien asignado`
    (mock de `send_push_to_user` con `await_args`).
  - `test_least_loaded_strategy_picks_less_busy`: con un operador ya
    cargado y otro libre, `least_loaded` elige al libre.
  - Mocks de red: `send_whatsapp`, `get_whatsapp_media_from_evolution`,
    `send_push_to_user`. La sesion se crea sin `tg_group_id/tg_topic_id`
    para que `mirror_client_to_topic` salga temprano y no intente TG.
- **Suite total**: 218 tests passing.

### 5.8 Horarios/turnos de operador — **DONE**
Filtra automaticamente por ventanas on-duty semanales en la
auto-asignacion. Operador sin schedule = siempre on-duty (backward compat
con 5.7).

**Backend**
- Modelo `OperatorSchedule` (`app/models/operator_schedule.py`, tabla
  `mkt_operator_schedule`): `user_id` (FK mkt_user ondelete=CASCADE),
  `weekday` (0=Mon..6=Sun, CheckConstraint), `start_time`, `end_time`,
  timestamps. Indices: `user_id`, `(user_id, weekday)`.
- Migracion Alembic `0003_operator_schedule.py` (down_revision=0002).
  Idempotente (inspector.has_table). Verificada contra Postgres:
  `CREATE TABLE mkt_operator_schedule (...)` con CheckConstraint y FK.
- Service `app/services/operator_availability.py`:
  - `now_local(tz='America/La_Paz')`: datetime aware en TZ fija (misma
    del scheduler).
  - `is_on_duty(schedule, now)`: True si schedule vacio (backward
    compat) o si `now.weekday()` y `now.time()` caen en alguna ventana
    (start inclusive, end exclusive).
  - `get_schedule_by_user(db, user_ids)`: bulk fetch `{user_id: [(wd, st, et)]}`.
  - `filter_on_duty(db, users, now=None)`: filtra preservando orden.
  - `save_schedule(db, user_id, windows)`: delete + insert atomico,
    valida weekday 0..6 y start < end. Formato entrada:
    `{"weekday": int, "start_time": "HH:MM", "end_time": "HH:MM"}`.
  - `list_schedule(db, user_id)`: devuelve windows normalizadas.
- Integracion en `inbox_autoassign._get_eligible_operators`: despues
  de filtrar por STAFF_ROLES + is_active + pool, aplica
  `filter_on_duty` usando `now_local()`. Transparente para el caller.
- Endpoints en `app/api/routes/admin.py` (require_manager):
  - `GET /api/v1/admin/operator-schedule/{user_id}` devuelve las
    ventanas. 404 si usuario no existe; 400 si no es staff activo.
  - `PUT /api/v1/admin/operator-schedule/{user_id}` body
    `{windows: [ScheduleWindow]}`. Reemplaza todas las ventanas.
    Valida weekday via Pydantic (ge=0, le=6) -> 422; valida
    `start < end` en service -> 400.
- Extension a `GET /api/v1/admin/inbox-autoassign`: cada operador del
  array `operators` trae ahora `has_schedule: bool` y
  `is_on_duty_now: bool` para que la UI muestre el estado actual.

**Frontend**
- `frontend/public/assets/app.js`:
  - Nuevos API helpers `operatorScheduleGet(userId)` /
    `operatorScheduleSave(userId, windows)`.
  - En el modal **Auto-asignacion**: cada fila de operador muestra un
    chip con estado del horario (verde "On-duty" / gris "Off-duty" /
    ambar "Sin horario") y boton **Horario**.
  - `openOperatorSchedule(userId, userName)` abre sub-modal con 7
    filas (Lun..Dom), cada una con lista de ventanas (inputs
    `<input type="time">`) + boton "Agregar ventana" + "Quitar". Boton
    **Borrar todas** limpia todo. Al guardar, vuelve al modal de
    Auto-asignacion para reflejar el estado actualizado.

**Tests**
- `tests/test_operator_availability.py` (24 casos unitarios +
  integracion):
  - `TestIsOnDuty`: schedule vacio, dentro, fuera, weekday equivocado,
    bordes (start inclusive / end exclusive), multi-ventana.
  - `TestGetScheduleByUser`: ids vacios, users sin filas, bulk fetch.
  - `TestFilterOnDuty`: todos pasan sin schedule, preserva orden,
    input vacio.
  - `TestSaveSchedule`: upsert reemplaza, empty clears, rechaza
    weekday invalido / start>=end / formato HH:MM invalido.
  - `TestEndpoints`: GET vacio, PUT guarda, 422 weekday, 400 rango,
    404 user inexistente, 400 user no-staff.
- `tests/test_inbox_autoassign_schedule.py` (5 casos de integracion):
  - `test_no_schedule_always_assigns`: operadores sin rows -> elegibles.
  - `test_respects_on_duty_window`: mock `now_local` a 10am -> asigna.
  - `test_off_duty_not_assigned`: mock a 20pm -> no asigna.
  - `test_picks_only_on_duty_operator`: A sin schedule, B off-duty -> A.
  - `test_all_off_duty_no_assignment`: ninguno on-duty -> no asigna,
    no system message.
- Fixtures `aa_db` e `integ_db` de Fase 5.7 actualizados para crear
  tambien `mkt_operator_schedule` en el engine SQLite.
- **Suite total**: 247 tests passing.

### 5.10 Auto-handoff por timeout SLA breach — **DONE**
Cuando una sesion asignada lleva mas de `threshold_hours` sin respuesta
del operador (y el cliente sigue esperando), un cron periodico la
reasigna a otro operador on-duty (o la libera al pool si no hay
candidato). Respeta pool, estrategia y filtros de 5.7/5.8.

**Backend**
- Columna `last_handoff_at TIMESTAMPTZ NULL` en
  `mkt_conversation_session` (migracion Alembic `0004_last_handoff_at.py`,
  idempotente con inspector). Se usa como cooldown anti-ping-pong:
  cooldown = `threshold_hours`, es decir una sesion no se re-handoff
  hasta que pasen `threshold_hours` desde el ultimo.
- Service `app/services/inbox_sla_handoff.py`:
  - Config persistida en `mkt_system_setting[inbox_sla_handoff]`:
    `{"enabled": bool, "threshold_hours": int}`. Default
    `{enabled: False, threshold_hours: 4}`.
  - `get_handoff_config` / `save_handoff_config` con normalize +
    clamp 1..72.
  - `find_breached_sessions(db, now, threshold_hours)`: reusa el
    criterio SLA del endpoint `/metrics` (inbox.py):
    `state != "closed"`, `operator_id IS NOT NULL`,
    `last_client_msg_at < now - threshold`, `operator_last_read_at`
    null o previa al ultimo inbound, `last_operator_msg_at` null o
    previo, y cooldown por `last_handoff_at`.
  - `handoff_session(db, session, now=None)`:
    1. Usa `pick_next_operator` (helper reusable de
       `inbox_autoassign`) con `exclude_user_id = operator actual`.
    2. Si hay candidato: reasigna, mensaje sistema
       "Reasignado por timeout SLA a ... (strategy)", actualiza cursor
       round-robin, dispara `webpush.send_push_to_user` al nuevo
       operador (best-effort).
    3. Si no hay candidato: libera (`operator_id=None`), mensaje
       sistema "Liberado al pool por timeout SLA (sin operadores
       on-duty)".
    4. Persiste `last_handoff_at = now` siempre (previene bucle).
    Devuelve `"reassigned"` / `"released"` / `"noop"`.
- Refactor en `app/services/inbox_autoassign.py`: nuevo helper
  publico `pick_next_operator(db, cfg, *, exclude_user_id=None)` que
  extrae la logica eligible + strategy pick. `auto_assign_if_needed`
  lo usa internamente sin cambio de comportamiento.
  `_get_eligible_operators` acepta ahora `exclude_user_id`.
- Tarea programada `app/tasks/inbox_sla_handoff.py` registrada en
  `app/core/scheduler.py` como job `inbox_sla_handoff` con cron
  `*/15 * * * *` (cada 15 min, TZ America/La_Paz). Devuelve stats
  `{threshold_hours, checked, handoffs, released}` persistidas en
  `mkt_task_log`. Si `enabled=False` sale temprano con
  `{"skipped": "disabled", ...}`.
- Endpoints en `app/api/routes/admin.py` (require_manager):
  - `GET /api/v1/admin/inbox-sla-handoff` -> config + limites.
  - `PUT /api/v1/admin/inbox-sla-handoff` body
    `{enabled: bool, threshold_hours: int (1..72)}`. Pydantic
    `InboxSlaHandoffIn` valida rango -> 422.

**Frontend**
- `frontend/public/assets/app.js`:
  - Nuevos helpers `inboxSlaHandoffGet()` / `inboxSlaHandoffSave(cfg)`.
  - Modal **Auto-asignacion** extendido con una seccion
    "Auto-handoff por timeout SLA": checkbox `enabled` + input
    numerico `threshold_hours` (min/max del backend). Se guarda en
    paralelo con la config de auto-asignacion al presionar Guardar.

**Tests**
- `tests/test_inbox_sla_handoff_service.py` (17 tests):
  - `TestConfig`: defaults, roundtrip, clamp low/high, invalid input
    cae a default.
  - `TestFindBreachedSessions`: sin operador -> no, operador leyo
    -> no, cliente reciente -> no, breached se encuentra, cooldown
    excluye, closed excluye.
  - `TestHandoffSession`: noop sin operador, release cuando no hay
    otro candidato, reasigna a otro operador, respeta filtro
    on-duty (5.8), excluye al actual del pick, llama push al
    reasignar.
- `tests/test_inbox_sla_handoff_task.py` (5 tests):
  - `test_returns_skipped_when_disabled`: no toca DB cuando
    `enabled=False`.
  - `test_reassigns_breached`: procesa y reasigna una sesion
    breached.
  - `test_releases_when_no_candidate`: libera cuando no hay otro.
  - `test_skips_non_breached`: ignora sesiones con mensaje cliente
    reciente.
  - `test_reports_threshold_hours`: incluye `threshold_hours` en
    stats.
- **Suite total**: 269 tests passing (247 previos + 22 nuevos).

**Verificacion migracion (offline postgres)**:
```
ALTER TABLE mkt_conversation_session ADD COLUMN last_handoff_at TIMESTAMP WITH TIME ZONE;
UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';
```

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
| `ff83e7d` | Docs: estado Conversation Hub + roadmap                     |
| `b0eb08a` | Admin webhook logs (endpoint + UI + tests)                  |
| `c325f71` | Inbox Fase 5.5 Web Push completo con VAPID + Service Worker |
| `6d33f6e` | Inbox Fase 5.7 auto-asignacion round-robin + least-loaded   |
| `056bf69` | Alembic 0001 mkt_push_subscription + mkt_system_setting     |
| `4892185` | Tests integracion auto-assign hook en handle_whatsapp_message |
| `5b3240f` | Alembic 0002 operator_last_read_at + fix doc Fase 1         |
| `002c3c0` | Inbox Fase 5.8 horarios/turnos de operador (on-duty windows) |
| `707a34d` | Inbox Fase 5.10 auto-handoff por timeout SLA breach + Alembic 0004 |

---

## 8. Decisiones y reglas ya aplicadas (no re-discutir)

- La clave interna del nav se mantiene `pedidos` aunque el label sea
  "Cotizaciones" para no romper `navigate('pedidos')`.
- "Importar precios" vive dentro de Admin -> Catalogo, no en el nav principal.
- El modelo incluye `operator_last_read_at` (Fase 5.6) en
  `mkt_conversation_session`. Declarada formalmente en la migracion
  Alembic `0002_operator_last_read_at.py` (idempotente: chequea columnas
  via inspector). `Base.metadata.create_all` en el boot sigue creandola
  en entornos frescos.
- Notificaciones: se implemento Web Push completo (Service Worker + VAPID +
  suscripciones persistidas en `mkt_push_subscription`). El cliente cae al
  modo Web Notifications API si el servidor no tiene `VAPID_PUBLIC_KEY`
  configurada. Script `scripts/generate_vapid_keys.py` genera el par.
- Horarios de operador (Fase 5.8) se almacenan en
  `mkt_operator_schedule` (migracion Alembic 0003). TZ fija
  `America/La_Paz` en `app/services/operator_availability.now_local` —
  misma TZ que el scheduler de APScheduler. Sin TZ por usuario por
  ahora (extension futura).
- Auto-handoff por timeout (Fase 5.10): el cron `inbox_sla_handoff`
  (cada 15 min) reasigna o libera sesiones con SLA breach. Config
  global en `mkt_system_setting[inbox_sla_handoff]`; `threshold_hours`
  clampea 1..72. El cooldown anti-ping-pong es igual al `threshold_hours`
  (una sesion no se re-handoff hasta que pase ese lapso desde el
  ultimo handoff). Disabled por default para no alterar el
  comportamiento al upgrade. Reusa `pick_next_operator` de
  `inbox_autoassign` para respetar pool + strategy + filtro on-duty.
- Migracion Alembic `0001_push_subscription_and_system_setting.py` crea
  `mkt_push_subscription` y `mkt_system_setting` explicitamente. Es
  idempotente (chequea `inspector.has_table` antes de crear/dropear) y
  coexiste con `Base.metadata.create_all` del boot (este ultimo usa
  `checkfirst` y omite tablas ya existentes).
- Plantillas globales: solo manager/admin/superadmin. Se aplica
  consistentemente en create/update/delete. Cambio de `scope` requiere
  manager+.
- Notas internas: usan `direction='internal'` + `channel='web'` +
  `sender_type='note'`. El bridging TG<->WA no toca mensajes con
  `direction='internal'`, por lo que no se filtran al cliente.
- EasyPanel + BuildKit puede fallar con `No such image: ...:latest` al
  arrancar si no tiene containerd image store. Fix recomendado:
  `/etc/docker/daemon.json` -> `{"features":{"containerd-snapshotter":true}}`.

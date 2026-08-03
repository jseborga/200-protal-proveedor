# HANDOFF — Estado del portal al 2026-08-03

Documento para retomar el trabajo más adelante. Escrito para alguien que
no estuvo en la sesión: dice qué hay, qué falta, y **por qué** se tomaron
las decisiones que no son obvias.

- Rama: `main`, sincronizada con `origin` en `bf41f19`.
- Punto de partida de la sesión: `b21ce5e`.
- Suite: **573 tests de backend** + 22 de cálculo y 17 de escapado en Node.
  Todo en verde. El job de tests pasa en CI.

---

## ⚠️ ACCIONES PENDIENTES QUE NO PUEDE HACER CLAUDE

Estas tres cosas están abiertas y son responsabilidad del dueño del proyecto.

### 1. Rotar dos credenciales comprometidas

| Credencial | Dónde estuvo expuesta | Qué hacer |
|---|---|---|
| API key de admin `mkt_z3d...` | Versionada en `.mcp.json` desde el commit `1db9801` | Admin → API Keys → revocar, crear otra, actualizar `.mcp.json` local (ya está en `.gitignore`) |
| API key de Evolution | El historial de webhooks la guardaba en claro en la BD | Cambiar en EasyPanel y en Integraciones (deben coincidir), y purgar con `DELETE /api/v1/admin/webhook-logs` |

La clave de `.mcp.json` **sigue en el historial de git**. Revocarla la deja
inútil, que es lo que importa. Borrarla del historial exige reescribirlo y un
push forzado; no se hizo por ser destructivo.

### 2. Configurar el secreto del despliegue

El deploy falla a propósito con un mensaje explicando esto:

1. EasyPanel → servicio `app` → Deployments → Webhook, copiar la URL.
2. GitHub → Settings → Secrets and variables → Actions → secreto
   `EASYPANEL_DEPLOY_HOOK`.

Hasta entonces, desplegar a mano desde EasyPanel.

### 3. Sacar los respaldos del servidor

La rutina de respaldo funciona pero **deja los archivos en el mismo disco que
la base**. Si se pierde la máquina, se pierden los dos. Hay que sincronizar
`BACKUP_DIR` a almacenamiento externo. Ver `docs/RESPALDOS.md`.

---

## Qué se construyó

### Auditoría de seguridad (commit `6ba4826`)

Se corrigieron, entre otras: un endpoint que ejecutaba SQL arbitrario con
cualquier API key, un borrado de 19 tablas sin autenticación real, el
endpoint `/mcp` público con herramientas de escritura, webhooks sin verificar
(se podía suplantar a un cliente), y ~105 puntos de XSS cuya causa raíz era
que `esc()` no escapaba comillas.

Detalle completo en el PR #1.

### Módulo de precios unitarios y presupuestos

Réplica deliberada de la semántica del módulo Odoo `ssa_construction_apu`,
para que un presupuesto migre al ERP sin traducción.

| Pieza | Archivo |
|---|---|
| Modelo | `app/models/apu.py` |
| Motor de cálculo | `app/services/apu_engine.py` |
| API (29 endpoints) | `app/api/routes/apu.py` |
| Exportador Excel | `app/services/apu_export.py` |
| Plantillas por defecto | `app/services/apu_seed.py` |

### Biblioteca por empresa y curación de precios

| Pieza | Archivo |
|---|---|
| Modelo | `app/models/company_insumo.py` |
| Compuerta estadística | `app/services/price_curation.py` |
| Emisión y resolución | `app/services/price_suggestions.py` |
| API | `app/api/routes/company_insumos.py` |

### Planes, cuotas y operación

| Pieza | Archivo |
|---|---|
| Estados y cuotas | `app/services/quota.py` |
| Respaldo programado | `app/tasks/db_backup.py` |
| Respaldo con restauración verificada | `scripts/backup_db.sh` |
| Migración | `migrations/versions/0006_apu_presupuestos_y_curacion.py` |

---

## Decisiones que NO hay que deshacer sin entender por qué

Son las que costó descubrir. Cambiarlas sin leer esto rompe cosas sutiles.

### El redondeo es medio-arriba, no el de Python ni el de JavaScript

`round()` de Python usa redondeo bancario y `toFixed()` de JavaScript opera
sobre el binario. Odoo redondea medio-arriba. Los tres dan distinto:

```
10.555  ->  Python round: 10.55  |  JS toFixed: 10.55  |  Odoo y nosotros: 10.56
```

Por eso existen `apu_round()` en el backend (con `Decimal`) y `apuRound()` en
el frontend (desplazando la coma sobre el **string** decimal). **Toda cuenta
de dinero pasa por ahí.** `toFixed` solo se usa para mostrar texto ya
redondeado. `tests/test_frontend_calc.js` lo vigila en CI.

### Los sub-APU se desagregan en mat/mo/eq

Una línea de tipo `sub` no suma como bloque: aporta los materiales, mano de
obra y equipo de la partida enlazada, multiplicados por el rendimiento. Si
todo cayera en materiales, los porcentajes que van sobre mano de obra
(cargas sociales) darían de menos. Hay un test que compara ambas formas y
muestra la diferencia.

### Los indirectos son datos, no columnas

Gastos generales, utilidad e impuestos **no** son campos: son filas de
`ApuTemplateLine` evaluadas en orden acumulando variables, igual que
`apu.template.line` de Odoo. Es la decisión que hace posible la migración.
Convertirlas en columnas rompería la compatibilidad.

### Las fórmulas se evalúan con un intérprete restringido

Las escriben usuarios desde la interfaz. `safe_eval_formula` acepta solo
números, variables ya definidas y `+ - * / **`. Nada de llamadas, atributos
ni builtins. **Nunca reemplazar por `eval()`.**

### Un presupuesto no se mueve solo

`ApuLine` guarda copia del nombre, unidad y precio del insumo. Refrescar
precios de mercado es una acción explícita, y **respeta los precios cargados
a mano** (negociados con un proveedor) salvo que se pida `include_manual`.

### Aceptar una sugerencia no escribe el precio

Escribe una observación en el histórico y deja que `ref_price` se recalcule
por **mediana**. Verificado: entra un 120 sobre un histórico de ~58 y el
precio público queda en 58.25, no en 120. Así un dato aceptado por error
mueve centavos, no rompe el catálogo.

### El opt-in de aporte de datos es real

Sin `Company.contributes_prices` no sale ningún dato, y hay test que lo
verifica. `ref_price` exige al menos dos observaciones antes de publicarse,
para no exponer el precio de una sola empresa identificable.

### Al vencer una suscripción no se corta el acceso

Se degrada a los límites gratuitos tras un período de gracia: se conserva
todo lo hecho y solo se corta **crear más**. Cortar de golpe hace perder
clientes y datos.

### Las plantillas globales no se editan

Editarlas cambiaría el cálculo de todas las empresas. El camino es clonar.
Tres alcances: global → empresa → proyecto.

---

## Qué falta, por prioridad

### Alto

1. **Cerrar el único camino sin curar.** La tarea `_update_from_pedidos`
   (`app/tasks/price_refresh.py`) todavía sobrescribe `ref_price`
   automáticamente desde pedidos completados, sin revisión. Es la última
   puerta abierta al catálogo público. Debería reenrutarse por
   `price_suggestions` para que todo entre por la misma compuerta.

2. **Actualización masiva por PDF/Excel.** La extracción con IA ya existe
   (`app/services/ai_extract.py`, se usa para cotizaciones) pero no está
   conectada al circuito. Lo natural: que una lista de precios genere
   sugerencias en lote que pasen por la compuerta.

3. **Exportar el presupuesto a PDF.** Hoy solo hay Excel. Un presupuesto se
   presenta al cliente en PDF; se va a pedir el primer día.

### Medio

4. **Cronograma básico.** Nunca se empezó. `ApuProject` tiene
   `start_date`/`end_date`, pero programar exige fechas y dependencias por
   partida. El resumen de recursos (`GET /apu/projects/{id}/resources`) ya
   da las cantidades por partida, que es el insumo natural.

5. **Login con Google.** No existe nada. Requiere `authlib`, hacer
   `hashed_password` nullable y agregar `auth_provider`/`google_sub`.
   `_build_tokens` en `app/api/routes/auth.py` es el embudo unico por donde
   se emiten los tokens: ahi engancharia sin tocar nada mas.

6. **Dinero en `Numeric(16,2)` en vez de `Float`.** Se midió la deriva: 4.8e-10
   Bs sobre 4000 líneas, o sea despreciable **porque se redondea en cada
   paso**. `Numeric` es el tipo correcto igual. El riesgo real aparece el día
   que alguien sume sin pasar por `apu_round`.

### Bajo

7. **Postgres administrado** (Neon, Supabase, RDS) cuando el negocio lo
   justifique, por la recuperación a un punto en el tiempo. **No es cambiar
   de motor**: el código depende de `pg_trgm`, `pgvector`, `PERCENTILE_CONT`
   y `JSONB` en decenas de archivos. Migrar a otro motor destruiría la
   búsqueda semántica y el matching.

---

## Integración con Odoo (todavía sin cablear)

El módulo Odoo en `E:\00 JSP PERSONAL\600 ERP-odoo-construccion\addons\obra_v2`
**ya tiene el enganche diseñado**:

- `apu.company.insumo` tiene `source_type` (`manual`/`marketplace`),
  `source_ref` y `last_price_update`.
- `_fetch_price_from_marketplace()` en
  `ssa_construction_apu/models/apu_company_db.py:100` devuelve `None` con el
  comentario «Pendiente de cablear contra el marketplace».
- `apu.portal.config` ya modela `base_url`, `api_key`, `source_name`,
  `auto_resync_threshold` y `require_review`.

Dos caminos, y el primero **no requiere escribir código en Odoo**:

1. **Excel canónico.** `GET /api/v1/apu/projects/{id}/export.xlsx` genera las
   siete hojas que `apu.import.wizard` ya sabe leer.
2. **Conector en vivo.** Un módulo nuevo que haga `_inherit` de
   `apu.company.insumo` y complete ese método. No toca nada existente.

Clave de mapeo: `Insumo.code` del portal (único en BD, formato `APUI-*`) →
`source_ref` en Odoo. Las unidades y categorías son texto libre en ambos
lados, así que no hay que reconciliar catálogos maestros.

---

## Cómo verificar que todo sigue sano

```bash
python -m pytest tests/ -q          # 573
node tests/test_frontend_calc.js    # 22 — redondeo navegador vs backend
node tests/test_frontend_escaping.js # 17 — XSS
node --check frontend/public/assets/app.js
```

El CI corre los cuatro y **bloquea el despliegue** si alguno falla.

---

## Lecciones de la sesión

**Revisar lo que entregan los subagentes.** Uno se cortó a mitad y dejó el
archivo *pareciendo* sano: parseaba y los tests pasaban, pero cinco funciones
estaban referenciadas desde el HTML sin existir y dos más se invocaban desde
JS, lo que habría roto el editor al abrir cualquier partida. Otro envió los
tipos de recurso como `material`/`labor`/`equipment` cuando la API espera
`mat`/`mo`/`eq`.

**Verificar por uso, no por lectura.** El módulo estuvo "completo" con el
backend probado y la interfaz sin forma de crear rubros ni partidas: se podía
crear un proyecto y quedaba un presupuesto vacío sin manera de poblarlo. Lo
detectó el dueño usándolo, no los tests.

**El CI paga solo.** En su primera corrida encontró que `mcp[cli]>=1.0.0` no
tenía tope de versión: un build nuevo instalaba la 2.x, el import fallaba, el
`try/except` se lo tragaba y `/mcp` quedaba sin montar en silencio.

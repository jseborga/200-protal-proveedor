# Respaldos de la base de datos

Hay dos formas de correrlo. Usá la primera; la segunda es para restaurar o
para correrlo desde fuera del contenedor.

## 1. Tarea programada (la que queda andando sola)

Ya está registrada en el planificador de la app como **"Respaldo de Base de
Datos"** (`db_backup`), diaria a las 02:15. Se ve y se dispara a mano desde
**Admin → Tareas**, igual que las demás.

Qué hace en cada corrida:

1. Genera un dump comprimido con `pg_dump --format=custom`.
2. Verifica que no esté corrupto leyendo su índice con `pg_restore --list`.
   Un archivo truncado se detecta ahí y se descarta; no queda un respaldo
   inservible aparentando estar bien.
3. Borra los que superan la retención.

Variables de entorno:

| Variable | Default | Para qué |
|---|---|---|
| `BACKUP_DIR` | `/app/backups` | Dónde se guardan |
| `BACKUP_KEEP_DAYS` | `30` | Retención |
| `BACKUP_TIMEOUT_SEC` | `900` | Corte si `pg_dump` se cuelga |

> **Importante:** montá `BACKUP_DIR` en un volumen **distinto** al de la base.
> Un respaldo en el mismo disco que la base no protege contra la pérdida del
> disco, que es justamente el caso para el que existe.

## 2. Script manual

`scripts/backup_db.sh` hace lo mismo y además **restaura la copia en una base
descartable** para comprobar que las tablas críticas traen filas. Es más lento
pero es la verificación de verdad.

```bash
./scripts/backup_db.sh              # respalda y verifica restaurando
./scripts/backup_db.sh --no-verify  # solo respalda
```

Lee `DATABASE_URL` del entorno o del `.env`.

## Restaurar

```bash
# A una base nueva (recomendado: primero probá acá, no encima de la buena)
createdb apu_restaurada
pg_restore --dbname=apu_restaurada --no-owner --no-privileges --exit-on-error \
           backups/apu_20260803_021500.dump

# Sobre la base existente, reemplazando todo
pg_restore --dbname="$DATABASE_URL" --clean --if-exists --no-owner \
           --no-privileges --exit-on-error backups/apu_20260803_021500.dump
```

`--exit-on-error` no es opcional: sin eso `pg_restore` sigue de largo ante
errores y terminás con una restauración parcial creyendo que salió bien.

## Lo que todavía falta

**Copia fuera del servidor.** Hoy los respaldos quedan en el disco del
servidor. Si se pierde la máquina, se pierden base y respaldos juntos.
Sincronizá `BACKUP_DIR` a almacenamiento externo (S3, Backblaze, otro host)
con `rclone` o `aws s3 sync` en un cron.

**Prueba de restauración periódica.** El script la hace; la tarea programada
solo verifica el índice, porque restaurar de verdad exige crear una base
temporal y eso no siempre está permitido desde el contenedor. Corré
`./scripts/backup_db.sh` a mano una vez por mes.

**Recuperación a un punto en el tiempo.** Un dump diario significa que en el
peor caso perdés hasta 24 horas de trabajo. Si eso deja de ser tolerable, es
el momento de pasar a un Postgres administrado (Neon, Supabase, RDS), que da
PITR sin que administres nada. Verificá que soporte `pgvector`, del que
depende la búsqueda semántica.

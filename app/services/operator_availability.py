"""Disponibilidad de operadores por horario (Fase 5.8).

Ventanas horarias semanales definidas en `mkt_operator_schedule`. Un
operador sin ninguna fila se considera "siempre on-duty" (backward compat
con Fase 5.7).

TZ fija: America/La_Paz (misma que `app/core/scheduler.py`).
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operator_schedule import OperatorSchedule
from app.models.user import User

DEFAULT_TZ = "America/La_Paz"


def now_local(tz_name: str = DEFAULT_TZ) -> datetime:
    """now() en la tz configurada."""
    return datetime.now(ZoneInfo(tz_name))


async def get_schedule_by_user(
    db: AsyncSession, user_ids: list[int]
) -> dict[int, list[tuple[int, time, time]]]:
    """Devuelve {user_id: [(weekday, start, end), ...]}.

    Los user_ids que no tengan filas quedan ausentes del dict.
    """
    if not user_ids:
        return {}
    stmt = (
        select(
            OperatorSchedule.user_id,
            OperatorSchedule.weekday,
            OperatorSchedule.start_time,
            OperatorSchedule.end_time,
        )
        .where(OperatorSchedule.user_id.in_(user_ids))
        .order_by(
            OperatorSchedule.user_id,
            OperatorSchedule.weekday,
            OperatorSchedule.start_time,
        )
    )
    out: dict[int, list[tuple[int, time, time]]] = {}
    for uid, wd, st, et in (await db.execute(stmt)).all():
        out.setdefault(int(uid), []).append((int(wd), st, et))
    return out


def is_on_duty(
    schedule: list[tuple[int, time, time]] | None,
    now: datetime,
) -> bool:
    """True si el schedule esta vacio (backward compat) o si `now`
    cae en alguna ventana del schedule.

    Regla: start <= now_time < end, matchando weekday. Python datetime
    usa Monday=0 .. Sunday=6 (mismo convenio que la DB).
    """
    if not schedule:
        return True
    wd = now.weekday()
    t = now.time()
    for day, st, et in schedule:
        if day == wd and st <= t < et:
            return True
    return False


async def filter_on_duty(
    db: AsyncSession,
    users: list[User],
    now: datetime | None = None,
) -> list[User]:
    """Filtra users que esten on-duty ahora (preserva orden original).

    Users sin filas en mkt_operator_schedule pasan siempre.
    """
    if not users:
        return []
    if now is None:
        now = now_local()
    schedules = await get_schedule_by_user(db, [u.id for u in users])
    return [
        u for u in users
        if is_on_duty(schedules.get(u.id), now)
    ]


def _parse_hhmm(value: str) -> time:
    """Acepta 'HH:MM' o 'HH:MM:SS'. Lanza ValueError si es invalido."""
    parts = value.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"hora invalida: {value!r}")
    hh = int(parts[0])
    mm = int(parts[1])
    ss = int(parts[2]) if len(parts) == 3 else 0
    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        raise ValueError(f"hora fuera de rango: {value!r}")
    return time(hh, mm, ss)


async def save_schedule(
    db: AsyncSession,
    user_id: int,
    windows: list[dict],
) -> list[dict]:
    """Reemplaza las ventanas del operador (delete + insert en una
    transaccion). Valida weekday 0..6 y start < end. Devuelve la lista
    de ventanas guardadas normalizadas.

    Cada window = {"weekday": int, "start_time": "HH:MM", "end_time": "HH:MM"}.
    """
    # Validacion antes de tocar la DB.
    normalized: list[tuple[int, time, time]] = []
    for w in windows:
        wd = w.get("weekday")
        if not isinstance(wd, int) or not (0 <= wd <= 6):
            raise ValueError(f"weekday invalido: {wd!r}")
        st_raw = w.get("start_time")
        et_raw = w.get("end_time")
        if not isinstance(st_raw, str) or not isinstance(et_raw, str):
            raise ValueError("start_time/end_time deben ser strings HH:MM")
        st = _parse_hhmm(st_raw)
        et = _parse_hhmm(et_raw)
        if not (st < et):
            raise ValueError(
                f"start_time debe ser < end_time (wd={wd} {st_raw}-{et_raw})"
            )
        normalized.append((wd, st, et))

    # Reemplazo atomico.
    await db.execute(
        delete(OperatorSchedule).where(OperatorSchedule.user_id == user_id)
    )
    for wd, st, et in normalized:
        db.add(
            OperatorSchedule(
                user_id=user_id,
                weekday=wd,
                start_time=st,
                end_time=et,
            )
        )
    await db.commit()

    return [
        {
            "weekday": wd,
            "start_time": st.strftime("%H:%M"),
            "end_time": et.strftime("%H:%M"),
        }
        for wd, st, et in normalized
    ]


async def list_schedule(
    db: AsyncSession, user_id: int
) -> list[dict]:
    """Devuelve las ventanas del operador como list de dicts."""
    schedules = await get_schedule_by_user(db, [user_id])
    windows = schedules.get(user_id, [])
    return [
        {
            "weekday": wd,
            "start_time": st.strftime("%H:%M"),
            "end_time": et.strftime("%H:%M"),
        }
        for wd, st, et in windows
    ]

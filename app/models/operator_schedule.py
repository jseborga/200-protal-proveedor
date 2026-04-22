"""Horarios de operador (Fase 5.8).

Cada fila representa una ventana horaria on-duty para un operador en un
dia especifico de la semana. Un operador puede tener multiples ventanas
por dia (ej: 09:00-13:00 y 15:00-18:00). Las ventanas se interpretan en
la TZ America/La_Paz (misma que el scheduler del proyecto).

Backward compat: un operador sin ninguna fila se considera "siempre
on-duty" para preservar el comportamiento previo a 5.8.

Cross-midnight (ej: 22:00-02:00) se modela como dos filas:
- weekday=N, 22:00-23:59
- weekday=(N+1)%7, 00:00-02:00
"""
from datetime import datetime, time

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OperatorSchedule(Base):
    __tablename__ = "mkt_operator_schedule"
    __table_args__ = (
        CheckConstraint(
            "weekday BETWEEN 0 AND 6",
            name="ck_mkt_operator_schedule_weekday",
        ),
        Index(
            "ix_mkt_operator_schedule_user_weekday",
            "user_id", "weekday",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon..6=Sun
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<OperatorSchedule {self.id} user={self.user_id} "
            f"wd={self.weekday} {self.start_time}-{self.end_time}>"
        )

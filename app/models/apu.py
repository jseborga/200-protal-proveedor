"""Analisis de Precios Unitarios (APU) y presupuestos de obra.

El modelo replica deliberadamente la semantica del modulo Odoo
`ssa_construction_apu` para que un presupuesto hecho aqui migre al ERP sin
traduccion. Equivalencias:

    portal                     Odoo
    ----------------------     -------------------------
    ApuTemplate                apu.template
    ApuTemplateLine            apu.template.line
    ApuProject                 project.project (campos APU)
    ApuRubro                   apu.rubro
    ApuItem                    apu.item
    ApuLine                    apu.line
    ApuComputo                 apu.computo
    ApuItemSummary             apu.item.summary

Decisiones que hay que respetar para no romper la compatibilidad:

* El rendimiento vive en `ApuLine.quantity` con 3 decimales.
* Los componentes se tipifican mat / mo / eq / sub.
* Los indirectos, utilidad e impuestos NO son columnas: son filas de
  `ApuTemplateLine` evaluadas en orden acumulando variables (ver
  `app/services/apu_engine.py`).
* `ApuLine` guarda copia de nombre, unidad y precio del insumo. Un
  presupuesto es un documento con valor legal/comercial: no puede cambiar
  solo porque el precio de mercado se movio. La actualizacion es explicita.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

# Precision decimal, alineada con APU_*_DIGITS de Odoo (apu_item.py:22-26).
PRICE_DIGITS = 2        # precio unitario de un recurso
PERFORMANCE_DIGITS = 3  # rendimiento (ApuLine.quantity)
SUBTOTAL_DIGITS = 2
TOTAL_DIGITS = 2
QTY_DIGITS = 4          # cantidades / computos metricos

# Tipos de recurso. 'sub' = sub-APU, se desagrega en mat/mo/eq al calcular.
RESOURCE_TYPES = ("mat", "mo", "eq", "sub")

# Tipos de linea de plantilla (identicos a Odoo).
TEMPLATE_LINE_TYPES = ("sum_mat", "sum_mo", "sum_eq", "percent", "formula")


class ApuTemplate(TimestampMixin, Base):
    """Plantilla de calculo: define como se llega del costo directo al P.U.

    `company_id` nulo = plantilla global provista por la plataforma
    (p.ej. GAMLP). Las empresas pueden clonarla y ajustar porcentajes.
    """

    __tablename__ = "mkt_apu_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_company.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_apu_template.id", ondelete="SET NULL"), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    lines: Mapped[list["ApuTemplateLine"]] = relationship(
        "ApuTemplateLine",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="ApuTemplateLine.sequence, ApuTemplateLine.id",
    )

    @property
    def is_global(self) -> bool:
        return self.company_id is None

    def __repr__(self) -> str:
        return f"<ApuTemplate {self.id} {self.name}>"


class ApuTemplateLine(TimestampMixin, Base):
    """Fila de la plantilla. `code` es el nombre de variable en las formulas."""

    __tablename__ = "mkt_apu_template_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_apu_template.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    formula: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_total: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    template: Mapped["ApuTemplate"] = relationship("ApuTemplate", back_populates="lines")

    __table_args__ = (
        UniqueConstraint("template_id", "code", name="uq_apu_template_line_code"),
    )

    def __repr__(self) -> str:
        return f"<ApuTemplateLine {self.code} {self.type}>"


class ApuProject(TimestampMixin, Base):
    """Obra / presupuesto. Equivale a project.project con campos APU."""

    __tablename__ = "mkt_apu_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_company.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Region determina que precio de mercado se usa al refrescar (mkt_insumo_regional_price)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(10), default="BOB", nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_apu_template.id", ondelete="SET NULL"), nullable=True,
    )
    state: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False,
    )  # draft, active, closed
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Total del presupuesto, materializado al recalcular.
    total_budget: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Precision configurable por obra (Odoo la guarda en project.project).
    decimals_price: Mapped[int] = mapped_column(Integer, default=PRICE_DIGITS, nullable=False)
    decimals_performance: Mapped[int] = mapped_column(
        Integer, default=PERFORMANCE_DIGITS, nullable=False,
    )
    decimals_subtotal: Mapped[int] = mapped_column(
        Integer, default=SUBTOTAL_DIGITS, nullable=False,
    )
    decimals_total: Mapped[int] = mapped_column(Integer, default=TOTAL_DIGITS, nullable=False)
    decimals_qty: Mapped[int] = mapped_column(Integer, default=QTY_DIGITS, nullable=False)

    template: Mapped["ApuTemplate | None"] = relationship("ApuTemplate")
    rubros: Mapped[list["ApuRubro"]] = relationship(
        "ApuRubro",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ApuRubro.sequence, ApuRubro.id",
    )
    items: Mapped[list["ApuItem"]] = relationship(
        "ApuItem",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ApuItem.sequence, ApuItem.id",
    )

    def __repr__(self) -> str:
        return f"<ApuProject {self.id} {self.name}>"


class ApuRubro(TimestampMixin, Base):
    """Capitulo / modulo del presupuesto (apu.rubro)."""

    __tablename__ = "mkt_apu_rubro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_apu_project.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    project: Mapped["ApuProject"] = relationship("ApuProject", back_populates="rubros")
    items: Mapped[list["ApuItem"]] = relationship(
        "ApuItem", back_populates="rubro", order_by="ApuItem.sequence, ApuItem.id",
    )

    def __repr__(self) -> str:
        return f"<ApuRubro {self.id} {self.name}>"


class ApuItem(TimestampMixin, Base):
    """Partida / APU: cabecera cuyo precio unitario se compone de recursos."""

    __tablename__ = "mkt_apu_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_apu_project.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    rubro_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_apu_rubro.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    uom: Mapped[str] = mapped_column(String(30), default="m2", nullable=False)

    # Cantidad del item en el presupuesto. Se calcula desde los computos
    # metricos pero es editable a mano (igual que cantidad_contrato en Odoo).
    quantity: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    # True = la cantidad la fijan los computos; False = fijada a mano.
    quantity_from_computo: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )

    # Sub-APU: se expone como recurso 'sub' dentro de otras partidas.
    is_complementary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    reference_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    technical_specs: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Resultados materializados por el motor de calculo.
    mat_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    mo_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    eq_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    direct_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    project: Mapped["ApuProject"] = relationship("ApuProject", back_populates="items")
    rubro: Mapped["ApuRubro | None"] = relationship("ApuRubro", back_populates="items")
    lines: Mapped[list["ApuLine"]] = relationship(
        "ApuLine",
        back_populates="item",
        cascade="all, delete-orphan",
        foreign_keys="ApuLine.item_id",
        order_by="ApuLine.sequence, ApuLine.id",
    )
    computos: Mapped[list["ApuComputo"]] = relationship(
        "ApuComputo",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ApuComputo.sequence, ApuComputo.id",
    )
    summary_lines: Mapped[list["ApuItemSummary"]] = relationship(
        "ApuItemSummary",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ApuItemSummary.sequence, ApuItemSummary.id",
    )

    __table_args__ = (
        Index("ix_mkt_apu_item_project_seq", "project_id", "sequence"),
    )

    def __repr__(self) -> str:
        return f"<ApuItem {self.id} {self.name[:40]}>"


class ApuLine(TimestampMixin, Base):
    """Componente de un APU: un recurso con su rendimiento y precio.

    `insumo_id` enlaza al catalogo de mercado (opcional: se admiten recursos
    escritos a mano). `name`, `uom` y `price_unit` son COPIA en el momento de
    agregar: el presupuesto no debe moverse solo porque cambio el mercado.
    """

    __tablename__ = "mkt_apu_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_apu_item.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # mat|mo|eq|sub

    insumo_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_insumo.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    # Para type='sub': partida complementaria que aporta el costo.
    linked_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_apu_item.id", ondelete="CASCADE"), nullable=True, index=True,
    )

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    uom: Mapped[str] = mapped_column(String(30), default="u", nullable=False)
    # Rendimiento: cuanto recurso hace falta por unidad de la partida.
    quantity: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    price_unit: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    price_subtotal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Trazabilidad del precio: de donde salio y cuando.
    price_source: Mapped[str] = mapped_column(
        String(20), default="manual", nullable=False,
    )  # manual, market, regional, imported
    price_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    item: Mapped["ApuItem"] = relationship(
        "ApuItem", back_populates="lines", foreign_keys=[item_id],
    )

    def __repr__(self) -> str:
        return f"<ApuLine {self.id} {self.type} {self.name[:30]}>"


class ApuComputo(TimestampMixin, Base):
    """Computo metrico: piezas x largo x ancho x alto."""

    __tablename__ = "mkt_apu_computo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_apu_item.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # sector / ubicacion
    pieces: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    length: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    width: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    height: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    item: Mapped["ApuItem"] = relationship("ApuItem", back_populates="computos")

    def __repr__(self) -> str:
        return f"<ApuComputo {self.id} {self.name}>"


class ApuItemSummary(TimestampMixin, Base):
    """Resultado materializado de aplicar la plantilla a una partida.

    Es lo que se imprime en la planilla del APU: una fila por variable
    (MAT, MO, EQ, cargas sociales, gastos generales, utilidad, impuestos...).
    """

    __tablename__ = "mkt_apu_item_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_apu_item.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    line_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value_formula: Mapped[str | None] = mapped_column(String(300), nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_total: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    item: Mapped["ApuItem"] = relationship("ApuItem", back_populates="summary_lines")

    def __repr__(self) -> str:
        return f"<ApuItemSummary {self.code} {self.amount}>"

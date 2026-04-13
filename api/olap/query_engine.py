"""
Motor de queries OLAP para la API babbage.

Traduce los parámetros de la API babbage (drilldown, cut, order, page)
a queries SQLAlchemy / SQL crudo que se ejecutan contra PostgreSQL.

La API babbage define:
  drilldown  → dimensiones por las que agrupar (GROUP BY)
  cut        → filtros (WHERE): "dim.attr:value|dim.attr:value"
  order      → ordenación: "measure:asc|dim.attr:desc"
  page       → paginación offset-based
  pagesize   → tamaño de página
  aggregates → qué medidas calcular (por defecto todas)

Referencia: https://github.com/openspending/babbage
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.olap.cube_model import CubeModel

# Máximo de filas por página
MAX_PAGE_SIZE = 1000
DEFAULT_PAGE_SIZE = 100


@dataclass
class AggregateResult:
    cells: list[dict]
    total_cell_count: int
    page: int
    page_size: int
    has_next: bool
    summary: dict = field(default_factory=dict)   # totales globales


@dataclass
class FactsResult:
    data: list[dict]
    total_fact_count: int
    page: int
    page_size: int
    has_next: bool
    fields: list[str] = field(default_factory=list)


@dataclass
class MembersResult:
    data: list[dict]
    total_member_count: int
    dimension: str


# ── Parser de parámetros babbage ─────────────────────────────────────────────

def parse_cut(cut_str: Optional[str]) -> list[tuple[str, str, str]]:
    """
    Parsea el parámetro cut de babbage.
    Formato: "dim.attr:value|dim.attr:value2"
    Retorna: [(dim, attr, value), ...]

    Soporta:
      year.fiscal_year:2023
      municipality.ine_code:11020
      chapter.direction:expense
      data_type.data_type:liquidation
    """
    if not cut_str:
        return []
    filters = []
    for part in cut_str.split("|"):
        part = part.strip()
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        if "." in key:
            dim, attr = key.split(".", 1)
        else:
            dim, attr = key, key
        filters.append((dim.strip(), attr.strip(), value.strip()))
    return filters


def parse_drilldown(drilldown_str: Optional[str]) -> list[tuple[str, str]]:
    """
    Parsea el parámetro drilldown.
    Formato: "dim.attr|dim2.attr2" o "dim.attr" o "dim"
    Retorna: [(dim, attr), ...]
    """
    if not drilldown_str:
        return []
    dims = []
    for part in drilldown_str.split("|"):
        part = part.strip()
        if "." in part:
            dim, attr = part.split(".", 1)
            dims.append((dim.strip(), attr.strip()))
        else:
            dims.append((part, part))
    return dims


def parse_order(order_str: Optional[str]) -> list[tuple[str, str]]:
    """
    Parsea el parámetro order.
    Formato: "measure:asc|dim.attr:desc"
    Retorna: [(column_expr, direction), ...]
    """
    if not order_str:
        return []
    orders = []
    for part in order_str.split("|"):
        part = part.strip()
        if ":" in part:
            col, direction = part.rsplit(":", 1)
            direction = direction.strip().upper()
            if direction not in ("ASC", "DESC"):
                direction = "DESC"
        else:
            col, direction = part, "DESC"
        orders.append((col.strip(), direction))
    return orders


# ── Resolución de columnas desde el modelo ───────────────────────────────────

def _resolve_column(model: CubeModel, dim: str, attr: str) -> Optional[str]:
    """
    Resuelve una referencia dim.attr al nombre de columna SQL del modelo.
    También soporta referencias directas a medidas (sin dim).
    """
    # Buscar en dimensiones
    if dim in model["dimensions"]:
        dim_def = model["dimensions"][dim]
        if attr in dim_def["attributes"]:
            return dim_def["attributes"][attr]["column"]
        # Si attr == dim (referencia corta), usar key_attribute
        key = dim_def.get("key_attribute", dim)
        if attr == dim and key in dim_def["attributes"]:
            return dim_def["attributes"][key]["column"]

    # Buscar en medidas (agregaciones)
    if dim in model.get("measures", {}):
        return model["measures"][dim]["column"]
    if attr in model.get("measures", {}):
        return model["measures"][attr]["column"]

    return None


def _measure_expr(model: CubeModel, measure_name: str) -> Optional[str]:
    """Retorna la expresión SQL de agregación para una medida."""
    m = model.get("measures", {}).get(measure_name)
    if not m:
        return None
    agg = m.get("aggregation", "sum").upper()
    col = m["column"]
    if agg == "SUM":
        return f"SUM({col}) AS \"{measure_name}.sum\""
    elif agg == "AVG":
        return f"AVG({col}) AS \"{measure_name}.avg\""
    elif agg == "COUNT":
        return f"COUNT({col}) AS \"{measure_name}.count\""
    return f"SUM({col}) AS \"{measure_name}.sum\""


# ── Query builder ─────────────────────────────────────────────────────────────

def _safe_col(col: str) -> str:
    """
    Valida que una columna SQL no tenga inyección.
    Solo permite letras, números, puntos, guiones bajos y comillas.
    """
    if not re.match(r'^[\w\s".,_()\-:]+$', col):
        raise ValueError(f"Columna SQL potencialmente insegura: {col!r}")
    return col


class OLAPQueryEngine:
    """Motor de queries OLAP sobre PostgreSQL."""

    def __init__(self, db: AsyncSession, model: CubeModel):
        self.db = db
        self.model = model
        self.fact_table = model["fact_table"].strip()

    def _build_where(self, cuts: list[tuple[str, str, str]]) -> tuple[str, dict]:
        """Construye cláusula WHERE desde los cuts babbage."""
        conditions = []
        params: dict = {}

        for i, (dim, attr, value) in enumerate(cuts):
            col = _resolve_column(self.model, dim, attr)
            if not col:
                continue
            param_name = f"cut_{i}"

            # Soporte para rangos: "2020;2024" → BETWEEN
            if ";" in value:
                lo, hi = value.split(";", 1)
                conditions.append(
                    f"{_safe_col(col)} BETWEEN :{param_name}_lo AND :{param_name}_hi"
                )
                params[f"{param_name}_lo"] = lo.strip()
                params[f"{param_name}_hi"] = hi.strip()
            else:
                # Coerción de tipo simple: si es numérico, no usar comillas en CAST
                try:
                    numeric_val = int(value)
                    conditions.append(f"CAST({_safe_col(col)} AS TEXT) = :{param_name}")
                    params[param_name] = str(numeric_val)
                except ValueError:
                    conditions.append(f"CAST({_safe_col(col)} AS TEXT) = :{param_name}")
                    params[param_name] = value

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return where, params

    async def aggregate(
        self,
        drilldown: Optional[str] = None,
        cut: Optional[str] = None,
        order: Optional[str] = None,
        page: int = 1,
        pagesize: int = DEFAULT_PAGE_SIZE,
        aggregates: Optional[str] = None,
    ) -> AggregateResult:
        """
        Agregación principal — equivale a /cubes/{name}/aggregate de babbage.
        """
        pagesize = min(max(1, pagesize), MAX_PAGE_SIZE)
        offset   = (page - 1) * pagesize

        parsed_drilldown = parse_drilldown(drilldown)
        parsed_cuts      = parse_cut(cut)
        parsed_order     = parse_order(order)

        # ── SELECT columns ────────────────────────────────────────────────────
        select_cols = []
        group_cols  = []

        for dim, attr in parsed_drilldown:
            col = _resolve_column(self.model, dim, attr)
            if not col:
                continue
            alias = f"{dim}.{attr}"
            select_cols.append(f'{_safe_col(col)} AS "{alias}"')
            group_cols.append(_safe_col(col))

        # Medidas
        measure_names = list(self.model.get("measures", {}).keys())
        if aggregates:
            measure_names = [m for m in measure_names if m in aggregates.split("|")]

        measure_exprs = []
        for m_name in measure_names:
            expr = _measure_expr(self.model, m_name)
            if expr:
                measure_exprs.append(expr)

        if not select_cols and not measure_exprs:
            return AggregateResult(cells=[], total_cell_count=0, page=page,
                                   page_size=pagesize, has_next=False)

        # ── WHERE ─────────────────────────────────────────────────────────────
        where, params = self._build_where(parsed_cuts)

        # ── ORDER BY ──────────────────────────────────────────────────────────
        order_clauses = []
        for col_ref, direction in parsed_order:
            # Buscar en aliases de SELECT
            col = _resolve_column(self.model, *col_ref.split(".")) if "." in col_ref else None
            if col:
                order_clauses.append(f'{_safe_col(col)} {direction}')
            else:
                # Puede ser una medida como "executed_per_capita:desc"
                clean = re.sub(r'\.(sum|avg|count)$', '', col_ref)
                order_clauses.append(f'"{clean}.avg" {direction}')

        order_sql = ("ORDER BY " + ", ".join(order_clauses)) if order_clauses else ""

        # ── GROUP BY ──────────────────────────────────────────────────────────
        group_sql = ("GROUP BY " + ", ".join(group_cols)) if group_cols else ""

        # ── Query principal ───────────────────────────────────────────────────
        all_select = select_cols + measure_exprs
        sql = f"""
            SELECT {", ".join(all_select)}
            FROM {self.fact_table}
            {where}
            {group_sql}
            {order_sql}
        """

        # Contar total de celdas (sin paginación)
        count_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT {", ".join(select_cols or ["1"])}
                FROM {self.fact_table}
                {where}
                {group_sql}
            ) AS _count_query
        """
        count_result = await self.db.execute(text(count_sql), params)
        total = count_result.scalar() or 0

        # Query paginada
        paged_sql = f"{sql} LIMIT {pagesize} OFFSET {offset}"
        result = await self.db.execute(text(paged_sql), params)
        rows = result.mappings().all()

        cells = [dict(row) for row in rows]

        # Summary: totales globales de las medidas (sin drilldown)
        summary = {}
        if measure_exprs:
            summary_sql = f"""
                SELECT {", ".join(measure_exprs)}
                FROM {self.fact_table}
                {where}
            """
            s_result = await self.db.execute(text(summary_sql), params)
            s_row = s_result.mappings().first()
            if s_row:
                summary = dict(s_row)

        return AggregateResult(
            cells=cells,
            total_cell_count=total,
            page=page,
            page_size=pagesize,
            has_next=(offset + pagesize) < total,
            summary=summary,
        )

    async def facts(
        self,
        cut: Optional[str] = None,
        fields: Optional[str] = None,
        order: Optional[str] = None,
        page: int = 1,
        pagesize: int = DEFAULT_PAGE_SIZE,
    ) -> FactsResult:
        """Filas individuales sin agregación."""
        pagesize = min(max(1, pagesize), MAX_PAGE_SIZE)
        offset   = (page - 1) * pagesize
        parsed_cuts  = parse_cut(cut)
        parsed_order = parse_order(order)
        where, params = self._build_where(parsed_cuts)

        # Campos a seleccionar
        if fields:
            field_list = [f.strip() for f in fields.split("|")]
            select_exprs = []
            for f in field_list:
                if "." in f:
                    dim, attr = f.split(".", 1)
                    col = _resolve_column(self.model, dim, attr)
                    if col:
                        select_exprs.append(f'{_safe_col(col)} AS "{f}"')
            if not select_exprs:
                select_exprs = ["*"]
        else:
            # Seleccionar columnas clave de todas las dimensiones
            select_exprs = []
            for dim_name, dim_def in self.model["dimensions"].items():
                key_attr = dim_def.get("key_attribute", dim_name)
                col = _resolve_column(self.model, dim_name, key_attr)
                if col:
                    select_exprs.append(f'{_safe_col(col)} AS "{dim_name}.{key_attr}"')
            # Añadir todas las medidas sin agregar
            for m_name, m_def in self.model.get("measures", {}).items():
                select_exprs.append(f'{_safe_col(m_def["column"])} AS "{m_name}"')

        order_clauses = []
        for col_ref, direction in parsed_order:
            col = _resolve_column(self.model, *col_ref.split(".")) if "." in col_ref else None
            if col:
                order_clauses.append(f'{_safe_col(col)} {direction}')
        order_sql = ("ORDER BY " + ", ".join(order_clauses)) if order_clauses else ""

        count_sql = f"SELECT COUNT(*) FROM {self.fact_table} {where}"
        total = (await self.db.execute(text(count_sql), params)).scalar() or 0

        sql = f"""
            SELECT {", ".join(select_exprs)}
            FROM {self.fact_table}
            {where}
            {order_sql}
            LIMIT {pagesize} OFFSET {offset}
        """
        result = await self.db.execute(text(sql), params)
        rows   = result.mappings().all()

        return FactsResult(
            data=[dict(r) for r in rows],
            total_fact_count=total,
            page=page,
            page_size=pagesize,
            has_next=(offset + pagesize) < total,
            fields=list(select_exprs),
        )

    async def members(
        self,
        dimension: str,
        cut: Optional[str] = None,
        page: int = 1,
        pagesize: int = DEFAULT_PAGE_SIZE,
    ) -> MembersResult:
        """Valores únicos de una dimensión."""
        pagesize = min(max(1, pagesize), MAX_PAGE_SIZE)
        offset   = (page - 1) * pagesize

        dim_def = self.model["dimensions"].get(dimension)
        if not dim_def:
            return MembersResult(data=[], total_member_count=0, dimension=dimension)

        # Columnas de la dimensión
        attr_cols = [
            f'{_safe_col(v["column"])} AS "{k}"'
            for k, v in dim_def["attributes"].items()
        ]

        parsed_cuts  = parse_cut(cut)
        where, params = self._build_where(parsed_cuts)

        key_col = _resolve_column(
            self.model, dimension, dim_def.get("key_attribute", dimension)
        )
        group_cols = [_safe_col(v["column"]) for v in dim_def["attributes"].values()]

        count_sql = f"""
            SELECT COUNT(DISTINCT {_safe_col(key_col)})
            FROM {self.fact_table}
            {where}
        """
        total = (await self.db.execute(text(count_sql), params)).scalar() or 0

        sql = f"""
            SELECT {", ".join(attr_cols)}
            FROM {self.fact_table}
            {where}
            GROUP BY {", ".join(group_cols)}
            ORDER BY {_safe_col(key_col)}
            LIMIT {pagesize} OFFSET {offset}
        """
        result = await self.db.execute(text(sql), params)
        rows   = result.mappings().all()

        return MembersResult(
            data=[dict(r) for r in rows],
            total_member_count=total,
            dimension=dimension,
        )

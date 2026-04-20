"""
Utilidad de upsert validado para cuenta_general_kpis.

Todos los ETLs que inserten o actualicen KPIs de Cuenta General deben llamar a
``validate_and_upsert_cgkpis()`` en lugar de hacer un INSERT directo, para que
las discrepancias entre fuentes queden registradas en etl_validation_exceptions.

Lógica:
  1. Para cada KPI entrante se consulta el valor existente.
  2. Si no existe: INSERT simple, sin excepción.
  3. Si existe de la MISMA fuente: UPDATE silencioso (actualización normal).
  4. Si existe de DISTINTA fuente:
       a. Se calcula diff_pct = (nuevo - existente) / |existente| × 100
       b. Si |diff_pct| > threshold (por defecto 1 %): se registra excepción.
       c. La fuente de mayor prioridad (SOURCE_PRIORITY) gana.
          - Si la fuente entrante es más autoritativa: UPDATE + excepción (accion=updated).
          - Si la fuente existente es más autoritativa: se mantiene + excepción (accion=kept_existing).
          - Empate de prioridad: UPDATE (más reciente gana) + excepción si hay diff.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.socioeconomic import CuentaGeneralKpi, EtlValidationException, source_priority

log = logging.getLogger(__name__)

# Diferencia relativa a partir de la cual se genera excepción (1 %)
DEFAULT_DIFF_THRESHOLD_PCT = 1.0


@dataclass
class CgKpiRecord:
    nif_entidad: str
    ejercicio: int
    kpi: str
    valor: Optional[Decimal]
    unidad: str = "EUR"
    fuente_cuenta: Optional[str] = None
    periodo: str = ""
    """
    Granularidad del dato:
      '' (vacío) = anual
      '01'-'12'  = mensual (número de mes con cero)
      'T1'-'T4'  = trimestral
    """


async def validate_and_upsert_cgkpis(
    db: AsyncSession,
    records: list[CgKpiRecord],
    diff_threshold_pct: float = DEFAULT_DIFF_THRESHOLD_PCT,
) -> dict[str, int]:
    """
    Valida y hace upsert de una lista de CgKpiRecord.

    Devuelve un resumen: {'inserted': N, 'updated': N, 'kept': N, 'exceptions': N}
    """
    stats = {"inserted": 0, "updated": 0, "kept": 0, "exceptions": 0}

    for rec in records:
        periodo = rec.periodo or ""
        # Buscar valor existente (único por nif+ejercicio+kpi+periodo)
        row = await db.scalar(
            select(CuentaGeneralKpi).where(
                CuentaGeneralKpi.nif_entidad == rec.nif_entidad,
                CuentaGeneralKpi.ejercicio   == rec.ejercicio,
                CuentaGeneralKpi.kpi         == rec.kpi,
                CuentaGeneralKpi.periodo     == periodo,
            )
        )

        if row is None:
            # No existe → INSERT directo
            db.add(CuentaGeneralKpi(
                nif_entidad  = rec.nif_entidad,
                ejercicio    = rec.ejercicio,
                kpi          = rec.kpi,
                periodo      = periodo,
                valor        = rec.valor,
                unidad       = rec.unidad,
                fuente_cuenta= rec.fuente_cuenta,
            ))
            stats["inserted"] += 1
            continue

        # Misma fuente → UPDATE silencioso
        same_source = (
            (row.fuente_cuenta or "").lower() == (rec.fuente_cuenta or "").lower()
        )
        if same_source:
            row.valor         = rec.valor
            row.fuente_cuenta = rec.fuente_cuenta
            stats["updated"] += 1
            continue

        # Fuente distinta → calcular diff y decidir
        exc = _build_exception(row, rec)

        if abs(exc.diff_pct or 0) > diff_threshold_pct:
            # Decidir qué fuente gana
            prio_existente = source_priority(row.fuente_cuenta)
            prio_nueva     = source_priority(rec.fuente_cuenta)

            if prio_nueva <= prio_existente:
                # Fuente entrante es igual o más autoritativa → actualizar
                exc.accion    = "updated"
                row.valor         = rec.valor
                row.fuente_cuenta = rec.fuente_cuenta
                stats["updated"] += 1
                log.info(
                    "CG KPI actualizado [%s/%s/%s]: %s→%s (fuente %s→%s, diff %.1f%%)",
                    rec.nif_entidad, rec.ejercicio, rec.kpi,
                    exc.valor_existente, exc.valor_nuevo,
                    exc.fuente_existente, exc.fuente_nueva, exc.diff_pct,
                )
            else:
                # Fuente existente más autoritativa → mantener
                exc.accion = "kept_existing"
                stats["kept"] += 1
                log.warning(
                    "CG KPI mantenido [%s/%s/%s]: fuente existente '%s' tiene mayor "
                    "prioridad que '%s'. diff=%.1f%%",
                    rec.nif_entidad, rec.ejercicio, rec.kpi,
                    row.fuente_cuenta, rec.fuente_cuenta, exc.diff_pct,
                )

            db.add(exc)
            stats["exceptions"] += 1
        else:
            # Diff dentro del umbral → UPDATE silencioso (ruido de redondeo)
            if source_priority(rec.fuente_cuenta) <= source_priority(row.fuente_cuenta):
                row.valor         = rec.valor
                row.fuente_cuenta = rec.fuente_cuenta
                stats["updated"] += 1
            else:
                stats["kept"] += 1

    await db.flush()
    return stats


def _build_exception(
    existing: CuentaGeneralKpi,
    incoming: CgKpiRecord,
) -> EtlValidationException:
    val_e = existing.valor
    val_n = incoming.valor
    diff_abs = None
    diff_pct = None

    if val_e is not None and val_n is not None and val_e != 0:
        diff_abs = val_n - val_e
        diff_pct = float(diff_abs / abs(val_e) * 100)
    elif val_e is None and val_n is not None:
        diff_pct = None   # existente era null → no hay ratio
        diff_abs = val_n

    return EtlValidationException(
        nif_entidad      = existing.nif_entidad,
        ejercicio        = existing.ejercicio,
        kpi              = existing.kpi,
        fuente_existente = existing.fuente_cuenta,
        valor_existente  = val_e,
        fuente_nueva     = incoming.fuente_cuenta,
        valor_nuevo      = val_n,
        diff_pct         = diff_pct,
        diff_abs         = diff_abs,
        accion           = "pending",
    )

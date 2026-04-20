"""
Servicio de sincronización con OpenDataManager (ODM).

Responsabilidades:
  1. Verificar la firma HMAC-SHA256 del webhook entrante.
  2. Decidir qué hacer según el resource_name del dataset publicado:
       - "INE - Padrón Municipal"             → sync_population()
       - "Hacienda - Deuda Viva …"            → sync_deuda_viva()
       - Resto (paro, renta, EOH, PMP)        → log + ignorar (se consultan vía GraphQL)
  3. Descargar el JSONL desde ODM y hacer upsert en las tablas locales.

KPIs de sostenibilidad y su fuente:
  - deuda_viva                         → sync_deuda_viva()  (Hacienda InformacionEELLs)
  - resultado_presupuestario           → calculado desde CONPREL (municipal_budgets)
  - ahorro_bruto                       → calculado desde CONPREL (cap.1-5 ing − cap.1-4 gtos)
  - ingresos_corrientes_liquidados     → calculado desde CONPREL
  - gastos_corrientes_liquidados       → calculado desde CONPREL
  - remanente_tesoreria_gastos_gles    → no disponible (requiere balance Cuenta General)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.socioeconomic import CeselKpi, CuentaGeneralKpi, InePadronMunicipal
from tasks.cgkpi_upsert import CgKpiRecord, validate_and_upsert_cgkpis

logger = logging.getLogger(__name__)


def verify_hmac(payload_bytes: bytes, signature: str, secret: str) -> bool:
    """Verifica la firma HMAC-SHA256 del webhook de ODM."""
    expected = hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix("sha256="))


async def handle_odmgr_webhook(
    payload: dict,
    db: AsyncSession,
    odmgr_base_url: str,
) -> dict:
    """
    Punto de entrada principal del webhook ODM.
    Devuelve un dict con el resultado del procesamiento.
    """
    dataset = payload.get("dataset", {})
    resource_name: str = dataset.get("resource_name", "")
    dataset_id: str = dataset.get("id", "")
    version: str = dataset.get("version", "")
    download_urls: dict = payload.get("download_urls", {})

    logger.info(
        "odmgr_webhook_received",
        resource=resource_name,
        dataset_id=dataset_id,
        version=version,
    )

    resource_lower = resource_name.lower()

    # ── Padrón Municipal ─────────────────────────────────────────────────────
    if "padrón municipal" in resource_lower or "padron municipal" in resource_lower:
        data_url = _resolve_url(odmgr_base_url, download_urls.get("data", ""))
        count = await sync_population(db, data_url, dataset_id)
        return {"action": "sync_population", "records_upserted": count, "dataset_id": dataset_id}

    # ── Deuda Viva Ayuntamientos (Hacienda) ──────────────────────────────────
    if "deuda viva" in resource_lower:
        data_url = _resolve_url(odmgr_base_url, download_urls.get("data", ""))
        count = await sync_deuda_viva(db, data_url, dataset_id)
        return {"action": "sync_deuda_viva", "records_upserted": count, "dataset_id": dataset_id}

    # ── PMP mensual (jerez_pmp_mensual) ──────────────────────────────────────
    if resource_name == "jerez_pmp_mensual" or "pmp_mensual" in resource_lower:
        data_url = _resolve_url(odmgr_base_url, download_urls.get("data", ""))
        count = await sync_pmp_mensual(db, data_url, dataset_id)
        return {"action": "sync_pmp_mensual", "records_upserted": count, "dataset_id": dataset_id}

    # ── Morosidad trimestral (jerez_morosidad_trimestral) ─────────────────────
    if resource_name == "jerez_morosidad_trimestral" or "morosidad_trimestral" in resource_lower:
        data_url = _resolve_url(odmgr_base_url, download_urls.get("data", ""))
        count = await sync_morosidad_trimestral(db, data_url, dataset_id)
        return {"action": "sync_morosidad_trimestral", "records_upserted": count, "dataset_id": dataset_id}

    # ── Deuda financiera anual (jerez_deuda_financiera) ───────────────────────
    if resource_name == "jerez_deuda_financiera" or "deuda_financiera" in resource_lower:
        data_url = _resolve_url(odmgr_base_url, download_urls.get("data", ""))
        count = await sync_deuda_financiera(db, data_url, dataset_id)
        return {"action": "sync_deuda_financiera", "records_upserted": count, "dataset_id": dataset_id}

    # ── Coste efectivo de servicios CESEL (jerez_cesel) ──────────────────────
    if resource_name == "jerez_cesel" or "cesel" in resource_lower:
        data_url = _resolve_url(odmgr_base_url, download_urls.get("data", ""))
        count = await sync_cesel(db, data_url, dataset_id)
        return {"action": "sync_cesel", "records_upserted": count, "dataset_id": dataset_id}

    # ── Resto: consulta vía GraphQL — no sincronizar localmente ─────────────
    logger.info("odmgr_webhook_graphql_only", resource=resource_name)
    return {"action": "graphql_only", "resource": resource_name}


async def sync_population(
    db: AsyncSession,
    data_url: str,
    dataset_id: str,
) -> int:
    """
    Descarga el JSONL de padrón desde ODM y hace upsert en ine_padron_municipal.
    Solo persiste sexo_cod="T" (total) para mantener la tabla ligera.
    """
    logger.info("sync_population_start", url=data_url)
    records_upserted = 0

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", data_url) as resp:
            resp.raise_for_status()
            batch = []
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                row: dict[str, Any] = json.loads(line)

                # Filtrar: solo totales (sexo_cod = "T") para no triplicar filas
                sexo = str(row.get("sex_cod", row.get("sexo_cod", "T"))).upper()
                if sexo not in ("T", "TOTAL", ""):
                    continue

                mun_cod = str(row.get("municipios_cod", row.get("municipio_cod", ""))).strip()
                if not mun_cod:
                    continue

                year_val = row.get("periodo_principal", row.get("anyo", row.get("year")))
                hab_val = row.get("valor", row.get("habitantes"))

                if year_val is None or hab_val is None:
                    continue

                batch.append({
                    "municipio_cod":    mun_cod,
                    "municipio_nombre": row.get("municipios_nombre", row.get("municipio_nombre")),
                    "year":             int(year_val),
                    "sexo_cod":         "T",
                    "sexo_nombre":      "Total",
                    "habitantes":       int(float(hab_val)),
                    "odmgr_dataset_id": dataset_id,
                })

                if len(batch) >= 500:
                    records_upserted += await _upsert_population_batch(db, batch)
                    batch = []

            if batch:
                records_upserted += await _upsert_population_batch(db, batch)

    logger.info("sync_population_done", records=records_upserted)
    return records_upserted


async def sync_deuda_viva(
    db: AsyncSession,
    data_url: str,
    dataset_id: str,
) -> int:
    """
    Descarga el JSONL de "Deuda Viva de los Ayuntamientos" (Hacienda) desde ODM.

    El XLSX de Hacienda tiene columnas: Ejercicio, Código Provincia, Código Municipio,
    Municipio, Deuda viva …(miles de euros).
    ODM normaliza los nombres de columna a snake_case sin acentos al convertir a JSONL.
    Se hace upsert en cuenta_general_kpis con kpi="deuda_viva", valor en euros
    (el fichero Hacienda lo publica en miles de €).

    nif_entidad se almacena como código INE 5 dígitos (cod_prov 2 + cod_mun 3),
    ya que el fichero de Hacienda no incluye NIF.
    """
    logger.info("sync_deuda_viva_start", url=data_url)
    aggregated: dict[tuple, dict] = {}

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", data_url) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                row: dict[str, Any] = json.loads(line)

                # Construir código INE 5 dígitos: 2 prov + 3 mun
                cod_prov = str(row.get("codigo_provincia", row.get("Código Provincia", ""))).strip().zfill(2)
                cod_mun  = str(row.get("codigo_municipio", row.get("Código Municipio", ""))).strip().zfill(3)
                if not cod_prov or not cod_mun or cod_prov == "00":
                    continue
                cod_ine = cod_prov + cod_mun

                ejercicio_raw = row.get("ejercicio", row.get("Ejercicio"))
                # El nombre de la columna de deuda varía según el año — buscar dinámicamente
                valor_raw = None
                for k, v in row.items():
                    if "deuda" in str(k).lower() and v not in (None, ""):
                        valor_raw = v
                        break

                if ejercicio_raw is None or valor_raw is None:
                    continue

                try:
                    ejercicio = int(str(ejercicio_raw).strip())
                    valor = Decimal(str(valor_raw)) * 1000  # miles → euros
                except (InvalidOperation, ValueError):
                    continue

                key = (cod_ine, ejercicio, "deuda_viva")
                aggregated[key] = {
                    "nif_entidad":      cod_ine,
                    "ejercicio":        ejercicio,
                    "kpi":              "deuda_viva",
                    "periodo":          "",
                    "valor":            valor,
                    "fuente_cuenta":    "hacienda_deuda_viva",
                    "odmgr_dataset_id": dataset_id,
                }

    if not aggregated:
        logger.warning("sync_deuda_viva_no_records")
        return 0

    stmt = pg_insert(CuentaGeneralKpi).values(list(aggregated.values()))
    stmt = stmt.on_conflict_do_update(
        index_elements=["nif_entidad", "ejercicio", "kpi", "periodo"],
        set_={
            "valor":            stmt.excluded.valor,
            "fuente_cuenta":    stmt.excluded.fuente_cuenta,
            "odmgr_dataset_id": stmt.excluded.odmgr_dataset_id,
        },
    )
    await db.execute(stmt)

    count = len(aggregated)
    logger.info("sync_deuda_viva_done", records=count)
    return count


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _upsert_population_batch(db: AsyncSession, batch: list[dict]) -> int:
    stmt = pg_insert(InePadronMunicipal).values(batch)
    stmt = stmt.on_conflict_do_update(
        index_elements=["municipio_cod", "year", "sexo_cod"],
        set_={
            "habitantes":       stmt.excluded.habitantes,
            "municipio_nombre": stmt.excluded.municipio_nombre,
            "odmgr_dataset_id": stmt.excluded.odmgr_dataset_id,
        },
    )
    await db.execute(stmt)
    return len(batch)


async def sync_pmp_mensual(
    db: AsyncSession,
    data_url: str,
    dataset_id: str,
) -> int:
    """
    Sincroniza datos de PMP mensual desde el JSONL de ODM.

    Espera filas con columnas: _year, _month, entidad (nombre o NIF), pmp_dias.
    Los nombres de entidad se mapean a NIF vía municipal_entities.alias_fuentes.

    Si la entidad no se puede resolver, se omite la fila (sin error silencioso:
    se loguea como advertencia para revisión en la tabla entity_alias_pending futura).
    """
    from app.config import get_settings
    from models.budget import MunicipalEntity
    from sqlalchemy import select as sa_select

    settings = get_settings()
    ine_code = settings.city_ine_code

    logger.info("sync_pmp_mensual_start", url=data_url)

    # Cargar mapa alias → NIF de las entidades del municipio
    entities = (await db.execute(
        sa_select(MunicipalEntity).where(MunicipalEntity.ine_code == ine_code)
    )).scalars().all()

    alias_to_nif: dict[str, str] = {}
    for ent in entities:
        alias_to_nif[ent.nif.upper()] = ent.nif
        if ent.alias_fuentes:
            try:
                import json as _json
                aliases = _json.loads(ent.alias_fuentes)
                pmp_alias = aliases.get("pmp_pdf", "")
                if pmp_alias:
                    alias_to_nif[pmp_alias.strip().upper()] = ent.nif
            except (ValueError, TypeError):
                pass
        alias_to_nif[ent.nombre.upper()] = ent.nif
        alias_to_nif[ent.nombre_corto.upper()] = ent.nif

    records: list[CgKpiRecord] = []
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", data_url) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                row: dict[str, Any] = json.loads(line)

                year_raw  = row.get("_year")
                month_raw = row.get("_month")

                if not year_raw or not month_raw:
                    continue

                # Formato columnar con cabecera (columnas nombradas)
                pmp_raw     = row.get("pmp_global_dias") or row.get("pmp_dias") or row.get("pmp")
                entidad_raw = row.get("entidad") or row.get("nombre_entidad") or ""

                # Formato posicional del XLSX de Jerez (sin cabecera):
                # unnamed_1 = nombre entidad, unnamed_6 = valor PMP en días
                if pmp_raw is None:
                    pmp_raw     = row.get("unnamed_6", "").strip() or None
                    entidad_raw = entidad_raw or row.get("unnamed_1", "").strip()

                if pmp_raw is None or pmp_raw == "":
                    continue

                try:
                    ejercicio = int(year_raw)
                    mes       = str(month_raw).zfill(2)
                    pmp_valor = Decimal(str(pmp_raw).replace(",", "."))
                except (InvalidOperation, ValueError):
                    continue

                # Resolver entidad → NIF
                nif = alias_to_nif.get(str(entidad_raw).strip().upper())
                if not nif:
                    # Fallback: ayuntamiento principal si la fila es del ayto
                    nif = settings.city_nif
                    logger.warning(
                        "pmp_entity_unresolved",
                        entidad=entidad_raw,
                        year=ejercicio,
                        mes=mes,
                    )

                records.append(CgKpiRecord(
                    nif_entidad   = nif,
                    ejercicio     = ejercicio,
                    kpi           = "pmp_ayto",
                    periodo       = mes,
                    valor         = pmp_valor,
                    unidad        = "DIA",
                    fuente_cuenta = "transparencia_pmp_xlsx",
                ))

    stats = await validate_and_upsert_cgkpis(db, records)
    count = stats["inserted"] + stats["updated"]
    logger.info("sync_pmp_mensual_done", **stats)
    return count


async def sync_morosidad_trimestral(
    db: AsyncSession,
    data_url: str,
    dataset_id: str,
) -> int:
    """
    Sincroniza morosidad trimestral (Ley 15/2010) desde el JSONL de ODM.

    Espera filas con: _year, _quarter (T1-T4), pmp_trimestral,
    pagos_plazo_count, pagos_plazo_importe, pagos_fuera_plazo_count,
    pagos_fuera_plazo_importe, facturas_pendientes_fuera_plazo_count,
    facturas_pendientes_fuera_plazo_importe, intereses_demora.
    """
    from app.config import get_settings
    settings = get_settings()
    nif = settings.city_nif

    logger.info("sync_morosidad_trimestral_start", url=data_url)

    _KPI_COLS = {
        "pmp_trimestral":                           "DIA",
        "pagos_plazo_count":                        "UNI",
        "pagos_plazo_importe":                      "EUR",
        "pagos_fuera_plazo_count":                  "UNI",
        "pagos_fuera_plazo_importe":                "EUR",
        "facturas_pendientes_fuera_plazo_count":    "UNI",
        "facturas_pendientes_fuera_plazo_importe":  "EUR",
        "intereses_demora":                         "EUR",
    }

    records: list[CgKpiRecord] = []
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", data_url) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                row: dict[str, Any] = json.loads(line)

                year_raw    = row.get("_year")
                quarter_raw = row.get("_quarter", "")

                if not year_raw or not quarter_raw:
                    continue
                try:
                    ejercicio = int(year_raw)
                except ValueError:
                    continue

                trimestre = str(quarter_raw).upper()
                if not trimestre.startswith("T"):
                    trimestre = f"T{trimestre}"

                for kpi_col, unidad in _KPI_COLS.items():
                    raw_val = row.get(kpi_col)
                    if raw_val is None:
                        continue
                    try:
                        valor = Decimal(str(raw_val).replace(",", "."))
                    except InvalidOperation:
                        continue
                    records.append(CgKpiRecord(
                        nif_entidad   = nif,
                        ejercicio     = ejercicio,
                        kpi           = kpi_col,
                        periodo       = trimestre,
                        valor         = valor,
                        unidad        = unidad,
                        fuente_cuenta = "transparencia_morosidad_pdf",
                    ))

    stats = await validate_and_upsert_cgkpis(db, records)
    count = stats["inserted"] + stats["updated"]
    logger.info("sync_morosidad_trimestral_done", **stats)
    return count


async def sync_deuda_financiera(
    db: AsyncSession,
    data_url: str,
    dataset_id: str,
) -> int:
    """
    Sincroniza deuda financiera anual detallada desde el JSONL de ODM.

    Espera filas con: _year, deuda_privada, deuda_ico, deuda_total.
    Persiste en cuenta_general_kpis con periodo='' (anual).
    """
    from app.config import get_settings
    settings = get_settings()
    nif = settings.city_nif

    logger.info("sync_deuda_financiera_start", url=data_url)

    _KPI_COLS = {
        "deuda_privada":  "EUR",
        "deuda_ico":      "EUR",
        "deuda_publica":  "EUR",
        "deuda_total":    "EUR",
    }

    records: list[CgKpiRecord] = []
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", data_url) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                row: dict[str, Any] = json.loads(line)
                year_raw = row.get("_year")
                if not year_raw:
                    continue
                try:
                    ejercicio = int(year_raw)
                except ValueError:
                    continue

                for kpi_col, unidad in _KPI_COLS.items():
                    raw_val = row.get(kpi_col)
                    if raw_val is None:
                        continue
                    try:
                        valor = Decimal(str(raw_val).replace(",", "."))
                    except InvalidOperation:
                        continue
                    records.append(CgKpiRecord(
                        nif_entidad   = nif,
                        ejercicio     = ejercicio,
                        kpi           = kpi_col,
                        periodo       = "",
                        valor         = valor,
                        unidad        = unidad,
                        fuente_cuenta = "transparencia_deuda_financiera_pdf",
                    ))

    stats = await validate_and_upsert_cgkpis(db, records)
    count = stats["inserted"] + stats["updated"]
    logger.info("sync_deuda_financiera_done", **stats)
    return count


async def sync_cesel(
    db: AsyncSession,
    data_url: str,
    dataset_id: str,
) -> int:
    """
    Sincroniza datos CESEL (coste efectivo de servicios) desde el JSONL de ODM.

    Espera filas con: _year, servicio (código/descripción), coste_total,
    num_usuarios, coste_por_usuario.
    """
    from app.config import get_settings
    settings = get_settings()
    nif = settings.city_nif

    logger.info("sync_cesel_start", url=data_url)

    _KPI_COLS = {
        "coste_total":       "EUR",
        "num_usuarios":      "UNI",
        "coste_por_usuario": "EUR",
    }

    rows_to_insert: list[dict] = []
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", data_url) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                row: dict[str, Any] = json.loads(line)
                year_raw  = row.get("_year")
                servicio  = str(row.get("servicio", row.get("servicio_codigo", ""))).strip()
                if not year_raw or not servicio:
                    continue
                try:
                    ejercicio = int(year_raw)
                except ValueError:
                    continue

                for kpi_col, _ in _KPI_COLS.items():
                    raw_val = row.get(kpi_col)
                    if raw_val is None:
                        continue
                    try:
                        valor = Decimal(str(raw_val).replace(",", "."))
                    except InvalidOperation:
                        continue
                    rows_to_insert.append({
                        "nif_entidad":      nif,
                        "ejercicio":        ejercicio,
                        "servicio":         servicio,
                        "kpi":              kpi_col,
                        "valor":            valor,
                        "fuente":           "transparencia_cesel_xlsx",
                        "odmgr_dataset_id": dataset_id,
                    })

    if not rows_to_insert:
        return 0

    stmt = pg_insert(CeselKpi).values(rows_to_insert)
    stmt = stmt.on_conflict_do_update(
        index_elements=["nif_entidad", "ejercicio", "servicio", "kpi"],
        set_={
            "valor":            stmt.excluded.valor,
            "fuente":           stmt.excluded.fuente,
            "odmgr_dataset_id": stmt.excluded.odmgr_dataset_id,
        },
    )
    await db.execute(stmt)

    count = len(rows_to_insert)
    logger.info("sync_cesel_done", records=count)
    return count


def _resolve_url(base: str, path: str) -> str:
    """Construye la URL absoluta combinando la base de ODM con el path del dataset."""
    if path.startswith("http"):
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")

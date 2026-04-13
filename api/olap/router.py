"""
Router FastAPI que expone la API babbage / OpenSpending.

Endpoints compatibles con babbage 0.3:
  GET /api/3/cubes/                           → lista de cubos
  GET /api/3/cubes/{name}/model               → modelo del cubo
  GET /api/3/cubes/{name}/aggregate           → agregación OLAP
  GET /api/3/cubes/{name}/facts               → hechos sin agregar
  GET /api/3/cubes/{name}/members/{dimension} → valores de dimensión
  GET /api/3/info/{name}/package              → Fiscal Data Package

Los frontends de OpenBudgets/OpenSpending consumen esta API directamente.
El endpoint /aggregate es el más crítico para el dashboard Dash.
"""
from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.db import get_db
from api.olap.cube_model import CUBE_REGISTRY
from api.olap.query_engine import DEFAULT_PAGE_SIZE, OLAPQueryEngine
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/3", tags=["OLAP / babbage"])


def _get_cube(name: str):
    """Obtiene la definición de un cubo o lanza 404."""
    if name not in CUBE_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Cubo '{name}' no encontrado. "
                   f"Cubos disponibles: {list(CUBE_REGISTRY.keys())}"
        )
    return CUBE_REGISTRY[name]


# ── GET /api/3/cubes/ ─────────────────────────────────────────────────────────

@router.get("/cubes/")
async def list_cubes():
    """
    Lista todos los cubos disponibles.
    Compatible con babbage /cubes endpoint.
    """
    cubes = []
    for name, info in CUBE_REGISTRY.items():
        cubes.append({
            "name": name,
            "label": info["label"],
            "description": info["description"],
            "currency": info["currency"],
            "period": info["period"],
            "granularity": info["granularity"],
            "model": f"/api/3/cubes/{name}/model",
            "aggregate": f"/api/3/cubes/{name}/aggregate",
            "facts": f"/api/3/cubes/{name}/facts",
        })
    return {"cubes": cubes, "total": len(cubes)}


# ── GET /api/3/cubes/{name}/model ────────────────────────────────────────────

@router.get("/cubes/{name}/model")
async def get_cube_model(name: str):
    """
    Devuelve el modelo del cubo (dimensiones + medidas).
    El frontend babbage.ui lo usa para construir la UI de filtros.
    """
    info = _get_cube(name)
    model = info["model"]

    # Serializar para JSON (eliminar fact_table que es interna)
    response = {
        "name": name,
        "label": info["label"],
        "dimensions": model["dimensions"],
        "measures": model["measures"],
        "currency": model.get("currency", "EUR"),
        "date_attribute": model.get("date_attribute"),
    }
    return response


# ── GET /api/3/cubes/{name}/aggregate ────────────────────────────────────────

@router.get("/cubes/{name}/aggregate")
async def aggregate(
    name: str,
    drilldown: Optional[str] = Query(
        None,
        description="Dimensiones por las que agrupar: 'municipality.ine_code|year.fiscal_year'"
    ),
    cut: Optional[str] = Query(
        None,
        description="Filtros: 'year.fiscal_year:2023|data_type.data_type:liquidation'"
    ),
    order: Optional[str] = Query(
        None,
        description="Ordenación: 'executed_per_capita:desc'"
    ),
    page: int = Query(1, ge=1),
    pagesize: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=1000),
    aggregates: Optional[str] = Query(
        None,
        description="Medidas a calcular (todas si None): 'executed_amount|execution_rate'"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint de agregación OLAP — el corazón de la API babbage.

    Ejemplos:
      # Ranking de municipios andaluces por €/hab ejecutado en 2023
      ?drilldown=municipality.name|municipality.ine_code
      &cut=year.fiscal_year:2023|data_type.data_type:liquidation
        |municipality.ccaa_code:01
      &order=executed_per_capita:desc
      &pagesize=50

      # Evolución Jerez por capítulo 2020-2024
      ?drilldown=year.fiscal_year|chapter.chapter
      &cut=municipality.ine_code:11020|data_type.data_type:liquidation
      &order=year.fiscal_year:asc

      # Score de rigor histórico de Jerez
      ?drilldown=year.fiscal_year
      (sobre el cubo jerez-rigor)
    """
    info = _get_cube(name)
    engine = OLAPQueryEngine(db, info["model"])

    try:
        result = await engine.aggregate(
            drilldown=drilldown,
            cut=cut,
            order=order,
            page=page,
            pagesize=pagesize,
            aggregates=aggregates,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "cells": result.cells,
        "total_cell_count": result.total_cell_count,
        "page": result.page,
        "page_size": result.page_size,
        "has_next": result.has_next,
        "summary": result.summary,
        # Metadatos para compatibilidad babbage.ui
        "status": "ok",
        "cell_count": len(result.cells),
    }


# ── GET /api/3/cubes/{name}/facts ────────────────────────────────────────────

@router.get("/cubes/{name}/facts")
async def facts(
    name: str,
    cut: Optional[str] = Query(None),
    fields: Optional[str] = Query(
        None,
        description="Campos a devolver: 'municipality.ine_code|executed_amount'"
    ),
    order: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pagesize: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve filas individuales sin agregación.
    Útil para exportar datos crudos o mostrar tablas detalladas.
    """
    info = _get_cube(name)
    engine = OLAPQueryEngine(db, info["model"])

    try:
        result = await engine.facts(
            cut=cut,
            fields=fields,
            order=order,
            page=page,
            pagesize=pagesize,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "data": result.data,
        "total_fact_count": result.total_fact_count,
        "page": result.page,
        "page_size": result.page_size,
        "has_next": result.has_next,
        "fields": result.fields,
        "status": "ok",
    }


# ── GET /api/3/cubes/{name}/members/{dimension} ───────────────────────────────

@router.get("/cubes/{name}/members/{dimension}")
async def members(
    name: str,
    dimension: str,
    cut: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pagesize: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve los valores únicos de una dimensión.
    El frontend lo usa para poblar los filtros/dropdowns.

    Ejemplo:
      # Todos los municipios disponibles en 2023
      /cubes/municipal-spain/members/municipality
      ?cut=year.fiscal_year:2023
    """
    info = _get_cube(name)
    engine = OLAPQueryEngine(db, info["model"])

    if dimension not in info["model"]["dimensions"]:
        raise HTTPException(
            status_code=404,
            detail=f"Dimensión '{dimension}' no encontrada en cubo '{name}'. "
                   f"Dimensiones: {list(info['model']['dimensions'].keys())}"
        )

    try:
        result = await engine.members(
            dimension=dimension,
            cut=cut,
            page=page,
            pagesize=pagesize,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "data": result.data,
        "total_member_count": result.total_member_count,
        "dimension": result.dimension,
        "status": "ok",
    }


# ── GET /api/3/info/{name}/package (Fiscal Data Package) ─────────────────────

@router.get("/info/{name}/package")
async def fiscal_data_package(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Genera un Fiscal Data Package (FDP) compatible con OpenBudgets.
    Para el cubo municipal-spain devuelve los datos de Jerez (11020).
    Para los cubos jerez-* devuelve todos los datos disponibles.

    El ZIP contiene datapackage.json + CSVs.
    """
    from api.olap.fdp_generator import generate_fdp
    info = _get_cube(name)

    try:
        zip_buffer = await generate_fdp(db, name, info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando FDP: {e}")

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}.zip"'
        },
    )

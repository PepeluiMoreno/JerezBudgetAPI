"""
Panel de administración — Modificaciones presupuestarias.
FastAPI + Jinja2 + HTMX. Sin autenticación (acceso restringido por red).

Rutas:
  GET  /admin/                        → redirect a /admin/modificaciones
  GET  /admin/modificaciones          → página principal (año actual)
  GET  /admin/modificaciones/{year}   → modificaciones de un año
  GET  /admin/modificaciones/{year}/new       → formulario nueva modificación (HTMX)
  GET  /admin/modificaciones/{year}/{id}/edit → formulario edición (HTMX)
  POST /admin/modificaciones/{year}           → crear modificación
  PUT  /admin/modificaciones/{year}/{id}      → actualizar modificación
  DELETE /admin/modificaciones/{year}/{id}    → eliminar modificación
  GET  /admin/modificaciones/{year}/reconciliacion → panel reconciliación (HTMX)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from models.budget import BudgetModification, FiscalYear
from services.reconciliation import MOD_TYPE_LABELS, compute_reconciliation

logger = structlog.get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

CURRENT_YEAR = 2026
ALL_YEARS = list(range(2020, 2027))

MOD_TYPE_OPTIONS = [
    ("transfer",          "Transferencia de crédito"),
    ("generate",          "Generación de crédito"),
    ("carry_forward",     "Incorporación de remanentes"),
    ("supplementary",     "Suplemento de crédito"),
    ("credit_reduction",  "Minoración de crédito"),
]
STATUS_OPTIONS = [
    ("approved",     "Aprobada"),
    ("in_progress",  "En trámite"),
    ("rejected",     "Rechazada"),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_or_create_fiscal_year(db: AsyncSession, year: int) -> FiscalYear:
    result = await db.execute(select(FiscalYear).where(FiscalYear.year == year))
    fy = result.scalar_one_or_none()
    if not fy:
        fy = FiscalYear(year=year, status="draft", is_extension=(year == 2026))
        if year == 2026:
            fy.extended_from_year = 2025
        db.add(fy)
        await db.flush()
    return fy


async def _get_modifications(db: AsyncSession, fiscal_year_id: int) -> list[BudgetModification]:
    result = await db.execute(
        select(BudgetModification)
        .where(BudgetModification.fiscal_year_id == fiscal_year_id)
        .order_by(BudgetModification.ref)
    )
    return list(result.scalars().all())


def _parse_amount(raw: str) -> Optional[Decimal]:
    if not raw or not raw.strip():
        return None
    try:
        cleaned = raw.strip().replace(".", "").replace(",", ".")
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_date(raw: str) -> Optional[date]:
    if not raw or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


# ── Rutas ─────────────────────────────────────────────────────────────────────

@router.get("/", response_class=RedirectResponse)
async def admin_root():
    return RedirectResponse(url=f"/admin/modificaciones/{CURRENT_YEAR}")


@router.get("/modificaciones", response_class=RedirectResponse)
async def modifications_root():
    return RedirectResponse(url=f"/admin/modificaciones/{CURRENT_YEAR}")


@router.get("/modificaciones/{year}", response_class=HTMLResponse)
async def modifications_list(
    request: Request,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    fy = await _get_or_create_fiscal_year(db, year)
    modifications = await _get_modifications(db, fy.id)
    reconciliation = await compute_reconciliation(db, year)

    return templates.TemplateResponse(
        "admin/modifications.html",
        {
            "request": request,
            "year": year,
            "all_years": ALL_YEARS,
            "fiscal_year": fy,
            "modifications": modifications,
            "reconciliation": reconciliation,
            "mod_type_labels": MOD_TYPE_LABELS,
            "mod_type_options": MOD_TYPE_OPTIONS,
            "status_options": STATUS_OPTIONS,
        },
    )


@router.get("/modificaciones/{year}/form/new", response_class=HTMLResponse)
async def modification_form_new(request: Request, year: int):
    """HTMX: devuelve el formulario vacío para nueva modificación."""
    return templates.TemplateResponse(
        "admin/partials/modification_form.html",
        {
            "request": request,
            "year": year,
            "mod": None,
            "mod_type_options": MOD_TYPE_OPTIONS,
            "status_options": STATUS_OPTIONS,
            "action": f"/admin/modificaciones/{year}",
            "method": "post",
        },
    )


@router.get("/modificaciones/{year}/{mod_id}/edit", response_class=HTMLResponse)
async def modification_form_edit(
    request: Request,
    year: int,
    mod_id: int,
    db: AsyncSession = Depends(get_db),
):
    """HTMX: devuelve el formulario precargado para editar una modificación."""
    result = await db.execute(
        select(BudgetModification).where(BudgetModification.id == mod_id)
    )
    mod = result.scalar_one_or_none()
    if not mod:
        return HTMLResponse("<p class='error'>Modificación no encontrada</p>", status_code=404)

    return templates.TemplateResponse(
        "admin/partials/modification_form.html",
        {
            "request": request,
            "year": year,
            "mod": mod,
            "mod_type_options": MOD_TYPE_OPTIONS,
            "status_options": STATUS_OPTIONS,
            "action": f"/admin/modificaciones/{year}/{mod_id}",
            "method": "put",
        },
    )


@router.post("/modificaciones/{year}", response_class=HTMLResponse)
async def modification_create(
    request: Request,
    year: int,
    ref: str = Form(...),
    mod_type: str = Form(...),
    status: str = Form(...),
    total_amount: str = Form(""),
    resolution_date: str = Form(""),
    publication_date: str = Form(""),
    description: str = Form(""),
    source_url: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    fy = await _get_or_create_fiscal_year(db, year)

    mod = BudgetModification(
        fiscal_year_id=fy.id,
        ref=ref.strip().upper(),
        mod_type=mod_type,
        status=status,
        total_amount=_parse_amount(total_amount),
        resolution_date=_parse_date(resolution_date),
        publication_date=_parse_date(publication_date),
        description=description.strip() or None,
        source_url=source_url.strip() or None,
    )
    db.add(mod)
    await db.commit()
    await db.refresh(mod)

    logger.info("modification_created", ref=mod.ref, year=year)

    # HTMX: devolvemos la fila nueva + panel de reconciliación actualizado
    modifications = await _get_modifications(db, fy.id)
    reconciliation = await compute_reconciliation(db, year)

    return templates.TemplateResponse(
        "admin/partials/modifications_table.html",
        {
            "request": request,
            "year": year,
            "modifications": modifications,
            "reconciliation": reconciliation,
            "mod_type_labels": MOD_TYPE_LABELS,
            "fiscal_year": fy,
        },
        headers={"HX-Trigger": "reconciliation-updated"},
    )


@router.put("/modificaciones/{year}/{mod_id}", response_class=HTMLResponse)
async def modification_update(
    request: Request,
    year: int,
    mod_id: int,
    ref: str = Form(...),
    mod_type: str = Form(...),
    status: str = Form(...),
    total_amount: str = Form(""),
    resolution_date: str = Form(""),
    publication_date: str = Form(""),
    description: str = Form(""),
    source_url: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BudgetModification).where(BudgetModification.id == mod_id)
    )
    mod = result.scalar_one_or_none()
    if not mod:
        return HTMLResponse("<p class='error'>No encontrado</p>", status_code=404)

    mod.ref = ref.strip().upper()
    mod.mod_type = mod_type
    mod.status = status
    mod.total_amount = _parse_amount(total_amount)
    mod.resolution_date = _parse_date(resolution_date)
    mod.publication_date = _parse_date(publication_date)
    mod.description = description.strip() or None
    mod.source_url = source_url.strip() or None

    await db.commit()
    logger.info("modification_updated", ref=mod.ref, year=year)

    fy = await _get_or_create_fiscal_year(db, year)
    modifications = await _get_modifications(db, fy.id)
    reconciliation = await compute_reconciliation(db, year)

    return templates.TemplateResponse(
        "admin/partials/modifications_table.html",
        {
            "request": request,
            "year": year,
            "modifications": modifications,
            "reconciliation": reconciliation,
            "mod_type_labels": MOD_TYPE_LABELS,
            "fiscal_year": fy,
        },
        headers={"HX-Trigger": "reconciliation-updated"},
    )


@router.delete("/modificaciones/{year}/{mod_id}", response_class=HTMLResponse)
async def modification_delete(
    request: Request,
    year: int,
    mod_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BudgetModification).where(BudgetModification.id == mod_id)
    )
    mod = result.scalar_one_or_none()
    if mod:
        await db.delete(mod)
        await db.commit()
        logger.info("modification_deleted", mod_id=mod_id, year=year)

    fy = await _get_or_create_fiscal_year(db, year)
    modifications = await _get_modifications(db, fy.id)
    reconciliation = await compute_reconciliation(db, year)

    return templates.TemplateResponse(
        "admin/partials/modifications_table.html",
        {
            "request": request,
            "year": year,
            "modifications": modifications,
            "reconciliation": reconciliation,
            "mod_type_labels": MOD_TYPE_LABELS,
            "fiscal_year": fy,
        },
        headers={"HX-Trigger": "reconciliation-updated"},
    )


@router.get("/modificaciones/{year}/reconciliacion/panel", response_class=HTMLResponse)
async def reconciliation_panel(
    request: Request,
    year: int,
    db: AsyncSession = Depends(get_db),
):
    """HTMX: devuelve solo el panel de reconciliación actualizado."""
    reconciliation = await compute_reconciliation(db, year)
    return templates.TemplateResponse(
        "admin/partials/reconciliation_panel.html",
        {"request": request, "year": year, "reconciliation": reconciliation},
    )

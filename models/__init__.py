"""
Exportación centralizada de todos los modelos ORM.
Alembic importa este módulo para detectar automáticamente las tablas.
"""
from models.budget import (
    Base,
    BudgetLine,
    BudgetModification,
    BudgetSnapshot,
    EconomicClassification,
    FiscalYear,
    FunctionalClassification,
    MunicipalEntity,
    OrganicClassification,
    RigorMetrics,
)
from models.national import (
    Municipality,
    MunicipalPopulation,
    MunicipalBudget,
    MunicipalBudgetChapter,
    MunicipalBudgetProgram,
    PeerGroup,
    PeerGroupMember,
)
from models.socioeconomic import (
    CeselKpi,
    CuentaGeneralKpi,
    EtlValidationException,
    InePadronMunicipal,
    KpiThreshold,
)

__all__ = [
    # Capa 1 — CityDashboard (presupuesto propio)
    "Base",
    "FiscalYear",
    "EconomicClassification",
    "FunctionalClassification",
    "OrganicClassification",
    "BudgetSnapshot",
    "BudgetLine",
    "BudgetModification",
    "RigorMetrics",
    # Capa 2 — Nacional
    "Municipality",
    "MunicipalPopulation",
    "MunicipalBudget",
    "MunicipalBudgetChapter",
    "MunicipalBudgetProgram",
    "PeerGroup",
    "PeerGroupMember",
    # Capa 3 — Socioeconómico ODM
    "InePadronMunicipal",
    "CuentaGeneralKpi",
    # Capa 4 — Sostenibilidad y KPIs financieros
    "EtlValidationException",
    "CeselKpi",
    "KpiThreshold",
    # Capa 5 — Infraestructura análisis
    "MunicipalEntity",
]

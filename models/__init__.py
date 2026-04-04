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

__all__ = [
    # Capa 1 — JerezBudget
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
]

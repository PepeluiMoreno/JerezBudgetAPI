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

__all__ = [
    "Base",
    "FiscalYear",
    "EconomicClassification",
    "FunctionalClassification",
    "OrganicClassification",
    "BudgetSnapshot",
    "BudgetLine",
    "BudgetModification",
    "RigorMetrics",
]

"""
Seed económico: actualiza las descripciones de economic_classifications
a partir de data/revenue_concepts.csv.

Uso:
    docker compose run --rm api python -m tasks.seed_economic_names
    make seed-economic-names   (si se añade al Makefile)
"""
import asyncio
import csv
import logging
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

CSV_PATH = Path(__file__).parent.parent / "data" / "revenue_concepts.csv"


async def seed(session: AsyncSession) -> None:
    from models.budget import EconomicClassification

    rows = []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    updated = 0
    skipped = 0
    for row in rows:
        code = row["code"].strip()
        description = row["description"].strip()
        direction = row["direction"].strip()

        result = await session.execute(
            select(EconomicClassification).where(
                EconomicClassification.code == code,
                EconomicClassification.direction == direction,
            )
        )
        ec = result.scalar_one_or_none()
        if ec is None:
            skipped += 1
            continue
        if ec.description != description:
            ec.description = description
            updated += 1

    await session.commit()
    log.info("seed_economic_names: updated=%d skipped=%d total=%d", updated, skipped, len(rows))


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())

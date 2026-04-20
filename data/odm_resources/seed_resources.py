#!/usr/bin/env python3
"""
seed_resources.py — Aprovisiona recursos ODM desde ficheros JSON.

Uso:
    # Aplica todos los JSON de este directorio:
    ODM_DATABASE_URL="postgresql+psycopg2://user:pass@host:port/db" python seed_resources.py

    # Aplica un fichero concreto:
    python seed_resources.py --file gestion_financiera.json

    # Solo muestra lo que haría (sin escribir):
    python seed_resources.py --dry-run

    # Opera solo sobre un recurso por nombre:
    python seed_resources.py --resource "Jerez - PMP Mensual"

Variables de entorno:
    ODM_DATABASE_URL   Cadena de conexión SQLAlchemy a la BD de ODM
                       Ejemplo: postgresql+psycopg2://odmgr_admin:pass@localhost:55432/odmgr_db

Prerequisitos (deben existir previamente en ODM):
    - Los Fetchers referenciados (fetcher_name)
    - Los Publishers referenciados (publisher_acronimo)
    Los recursos con "status": "pending_fetcher" son ignorados.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 no instalado. Instala con: pip install psycopg2-binary")
    sys.exit(1)


# ── Conexión ──────────────────────────────────────────────────────────────────

def get_connection(db_url: str):
    """Convierte una URL SQLAlchemy a parámetros psycopg2 y conecta."""
    # postgresql+psycopg2://user:pass@host:port/dbname
    url = db_url.replace("postgresql+psycopg2://", "").replace("postgresql://", "")
    if "@" in url:
        credentials, hostpart = url.rsplit("@", 1)
        user, password = credentials.split(":", 1)
    else:
        user, password, hostpart = "", "", url

    if "/" in hostpart:
        hostport, dbname = hostpart.rsplit("/", 1)
    else:
        hostport, dbname = hostpart, "odmgr_db"

    host, port = (hostport.split(":") + ["5432"])[:2]

    return psycopg2.connect(
        host=host, port=int(port), dbname=dbname, user=user, password=password
    )


# ── Upsert logic ──────────────────────────────────────────────────────────────

def upsert_resource(cur, resource_def: dict[str, Any], dry_run: bool) -> str:
    """
    Crea o actualiza un recurso en ODM.

    Returns:
        "created" | "updated" | "unchanged" | "skipped"
    """
    name = resource_def["name"]

    # -- Buscar fetcher
    cur.execute(
        "SELECT id FROM opendata.fetcher WHERE name = %s AND deleted_at IS NULL",
        (resource_def["fetcher_name"],),
    )
    row = cur.fetchone()
    if not row:
        print(f"  [!] Fetcher no encontrado: {resource_def['fetcher_name']} — saltando '{name}'")
        return "skipped"
    fetcher_id = row["id"]

    # -- Buscar publisher
    cur.execute(
        "SELECT id FROM opendata.publisher WHERE acronimo = %s",
        (resource_def["publisher_acronimo"],),
    )
    row = cur.fetchone()
    if not row:
        print(f"  [!] Publisher no encontrado: {resource_def['publisher_acronimo']} — saltando '{name}'")
        return "skipped"
    publisher_id = row["id"]

    # -- Buscar resource existente
    cur.execute(
        "SELECT id FROM opendata.resource WHERE name = %s",
        (name,),
    )
    existing = cur.fetchone()
    params = resource_def.get("params", {})

    if existing:
        resource_id = existing["id"]

        # Comparar params actuales
        cur.execute(
            "SELECT key, value FROM opendata.resource_param WHERE resource_id = %s",
            (resource_id,),
        )
        current_params = {r["key"]: r["value"] for r in cur.fetchall()}
        desired_params = {k: str(v) for k, v in params.items()}

        if current_params == desired_params:
            print(f"  [=] {name}")
            return "unchanged"

        # Params difieren — actualizar
        added = set(desired_params) - set(current_params)
        removed = set(current_params) - set(desired_params)
        changed = {k for k in desired_params if k in current_params and desired_params[k] != current_params[k]}
        print(f"  [~] {name}  (params: +{len(added)} ~{len(changed)} -{len(removed)})")
        if not dry_run:
            cur.execute("DELETE FROM opendata.resource_param WHERE resource_id = %s", (resource_id,))
            for key, value in desired_params.items():
                cur.execute(
                    "INSERT INTO opendata.resource_param (id, resource_id, key, value, is_external) "
                    "VALUES (gen_random_uuid(), %s, %s, %s, false)",
                    (resource_id, key, value),
                )
        return "updated"

    # -- Crear nuevo resource
    print(f"  [+] {name}")
    if not dry_run:
        cur.execute(
            """
            INSERT INTO opendata.resource
              (id, name, publisher, fetcher_id, publisher_id, active,
               description, target_table, enable_load, load_mode, created_at)
            VALUES
              (gen_random_uuid(), %s, %s, %s, %s, true, %s, %s, true, %s, now())
            RETURNING id
            """,
            (
                name,
                resource_def.get("publisher_acronimo", ""),
                fetcher_id,
                publisher_id,
                resource_def.get("description", ""),
                resource_def.get("target_table", ""),
                resource_def.get("load_mode", "replace"),
            ),
        )
        resource_id = cur.fetchone()["id"]
        for key, value in {k: str(v) for k, v in params.items()}.items():
            cur.execute(
                "INSERT INTO opendata.resource_param (id, resource_id, key, value, is_external) "
                "VALUES (gen_random_uuid(), %s, %s, %s, false)",
                (resource_id, key, value),
            )
    return "created"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Aprovisiona recursos ODM desde JSON")
    parser.add_argument("--file", help="Fichero JSON concreto (por defecto: todos los *.json del directorio)")
    parser.add_argument("--resource", help="Opera solo sobre el recurso con este nombre")
    parser.add_argument("--db-url", help="URL de conexión ODM (sobreescribe ODM_DATABASE_URL)")
    parser.add_argument("--dry-run", action="store_true", help="Muestra lo que haría sin escribir")
    args = parser.parse_args()

    db_url = args.db_url or os.environ.get("ODM_DATABASE_URL", "")
    if not db_url:
        print("ERROR: Falta ODM_DATABASE_URL (env var) o --db-url")
        sys.exit(1)

    # -- Cargar JSONs
    here = Path(__file__).parent
    if args.file:
        json_files = [Path(args.file)]
    else:
        json_files = sorted(here.glob("*.json"))

    resources: list[dict] = []
    for jf in json_files:
        with open(jf, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            resources.extend(data)
        else:
            resources.append(data)

    if args.resource:
        resources = [r for r in resources if r.get("name") == args.resource]
        if not resources:
            print(f"ERROR: No se encontró el recurso '{args.resource}' en los JSON")
            sys.exit(1)

    # -- Filtrar pending_fetcher
    active = [r for r in resources if r.get("status") != "pending_fetcher"]
    pending = [r for r in resources if r.get("status") == "pending_fetcher"]

    if pending:
        print(f"Ignorando {len(pending)} recursos con status=pending_fetcher:")
        for r in pending:
            print(f"  - {r['name']}")
        print()

    if not active:
        print("No hay recursos activos que procesar.")
        return

    print(f"Procesando {len(active)} recursos {'(DRY-RUN)' if args.dry_run else ''}...\n")

    try:
        conn = get_connection(db_url)
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        stats = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}
        for res in active:
            result = upsert_resource(cur, res, args.dry_run)
            stats[result] += 1

        if not args.dry_run:
            conn.commit()
            print(f"\n✅ Completado: {stats['created']} creados, {stats['updated']} actualizados, "
                  f"{stats['unchanged']} sin cambios, {stats['skipped']} saltados.")
        else:
            conn.rollback()
            print(f"\n[DRY-RUN] Nada escrito: {stats['created']} se crearían, "
                  f"{stats['updated']} se actualizarían, {stats['unchanged']} sin cambios.")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        if "conn" in dir() and conn:
            conn.close()


if __name__ == "__main__":
    main()

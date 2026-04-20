# Integración CityDashboard ↔ OpenDataManager

## Qué es ODM para CityDashboard

OpenDataManager (ODM) es un **proveedor de datos públicos externo**. CityDashboard no sabe de dónde vienen los datos originalmente — solo los recibe ya procesados, vía webhook o GraphQL. ODM se encarga de:

- Descubrir y descargar ficheros desde portales públicos (transparencia municipal, Hacienda, INE, etc.)
- Parsear, normalizar y cargar los datos en su propia BD
- Notificar a los suscriptores cuando hay datos nuevos (webhook)

CityDashboard declara qué datasets necesita. ODM los obtiene.

---

## Cómo CityDashboard declara lo que necesita

Los recursos ODM del proyecto están declarados en `data/odm_resources/`:

```
data/odm_resources/
  gestion_financiera.json   ← módulo Gestión Financiera
  seed_resources.py         ← script de aprovisionamiento
```

Cada JSON es un array de objetos con este esquema:

```json
{
  "name": "Nombre del recurso en ODM",
  "fetcher_name": "NOMBRE_FETCHER",
  "publisher_acronimo": "SIGLAS",
  "target_table": "nombre_tabla_odm",
  "load_mode": "replace | append",
  "description": "Descripción libre",
  "status": "active | pending_fetcher",
  "params": {
    "param_clave": "param_valor"
  }
}
```

Los recursos con `"status": "pending_fetcher"` se ignoran hasta que el fetcher requerido exista en ODM.

### Aplicar los recursos a ODM

```bash
# Todos los JSON del directorio:
ODM_DATABASE_URL="postgresql+psycopg2://odmgr_admin:pass@localhost:55432/odmgr_db" \
  python data/odm_resources/seed_resources.py

# Un fichero concreto:
python data/odm_resources/seed_resources.py --file data/odm_resources/gestion_financiera.json

# Previsualizar sin escribir:
python data/odm_resources/seed_resources.py --dry-run

# Un recurso concreto:
python data/odm_resources/seed_resources.py --resource "Jerez - Coste Efectivo de Servicios (CESEL)"
```

El script es idempotente: si el recurso ya existe y los params coinciden, no escribe nada (`[=]`). Si los params difieren, actualiza (`[~]`). Si no existe, crea (`[+]`).

---

## Cómo llegan los datos a CityDashboard

### Vía webhook (push)

Cuando ODM completa una carga, hace un `POST /webhooks/odmgr` con HMAC-SHA256 en la cabecera `X-ODM-Signature`. CityDashboard verifica la firma y procesa el payload.

Handler: `services/odmgr_sync.py`  
Endpoint: `app/main.py` → `POST /webhooks/odmgr`

### Vía GraphQL (pull)

CityDashboard también puede consultar datos directamente a la API GraphQL de ODM.

---

## Flujo completo

```
docs/odm_resources/*.json
        │
        ▼
seed_resources.py  ──→  ODM BD (opendata.resource + resource_param)
                                │
                                ▼ (ODM ejecuta según schedule o manual)
                     ODM fetcher (FILE_SERIES, HTML_TABLE, …)
                                │
                                ▼
                     transparencia.jerez.es / Hacienda / INE / …
                                │
                                ▼
                     ODM staging → dataset
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
          POST /webhooks/odmgr      ODM GraphQL API
                    │
                    ▼
         services/odmgr_sync.py
                    │
                    ▼
         BD CityDashboard (PostgreSQL)
                    │
                    ▼
         GraphQL CityDashboard → Vue SPA
```

---

## Checklist para añadir un nuevo dataset

1. **Declarar el recurso** en el JSON del módulo correspondiente (`docs/odm_resources/<modulo>.json`)
2. **Aplicar a ODM** con `seed_resources.py`
3. **Añadir handler** en `services/odmgr_sync.py` para procesar el webhook
4. **Migración de BD** si el dataset requiere nueva tabla (Alembic)
5. **Añadir resolver GraphQL** en `gql/resolvers/`
6. **Añadir vista o KPI** en el frontend (`frontend/src/views/`)

---

## Convenciones de nombres

| Prefijo | Uso |
|---|---|
| `jerez_*` | Datos específicos del municipio de Jerez (portal transparencia, liquidaciones locales) |
| `nacional_*` | Datos nacionales (CONPREL Hacienda, INE Nomenclator, padrones nacionales) |

Los `target_table` de ODM siguen estas mismas convenciones.

---

## Prerequisitos en ODM

Antes de ejecutar `seed_resources.py`, deben existir en ODM:

- **Fetchers** referenciados en los JSON (`FILE_SERIES`, `HTML_TABLE`, etc.)
- **Publisher** con el `acronimo` indicado (ej. `AJFRA` para Ayuntamiento de Jerez)

La creación de fetchers y publishers en ODM es un paso previo fuera del alcance de este repositorio.

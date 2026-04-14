"""
Descargador de ficheros MDB del CONPREL (Ministerio de Hacienda).

Los ficheros se publican anualmente en:
  https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL/

La URL exacta varía entre años y publicaciones. Este módulo
implementa una estrategia de múltiples URLs candidatas
y cachea en MinIO para evitar descargas repetidas.
"""
from __future__ import annotations

import asyncio
import hashlib
import tempfile
from pathlib import Path

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# URL actual del CONPREL (verificada 2026-04-14)
# La descarga devuelve un ZIP que contiene el MDB.
# TipoDato: "Liquidaciones" = ejecución/liquidación (lo que queremos)
#           "Presupuestos"  = presupuesto inicial
_CONPREL_BASE = "https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL"
_CONPREL_TIPO = "Liquidaciones"


def _candidate_urls(year: int) -> list[str]:
    return [
        # Formato actual (2020+): devuelve ZIP con MDB dentro
        f"{_CONPREL_BASE}/Consulta/DescargaFichero?CCAA=&TipoDato={_CONPREL_TIPO}&Ejercicio={year}&TipoPublicacion=Access",
        # Variante con Presupuestos como fallback
        f"{_CONPREL_BASE}/Consulta/DescargaFichero?CCAA=&TipoDato=Presupuestos&Ejercicio={year}&TipoPublicacion=Access",
    ]


async def download_conprel_mdb(year: int) -> Path:
    """
    Descarga el fichero MDB del CONPREL para un año dado.
    Prueba múltiples URLs hasta encontrar una que funcione.
    Cachea en MinIO para evitar re-descargas.

    Returns:
        Ruta al fichero temporal .mdb listo para parsear.
        El llamador es responsable de borrarlo tras procesar.

    Raises:
        RuntimeError si no se puede descargar de ninguna URL.
    """
    minio_key = f"conprel/mdb/conprel_{year}.mdb"

    # ── Intentar desde MinIO cache ────────────────────────────────────────────
    cached = await _from_minio_cache(minio_key)
    if cached:
        logger.info("conprel_from_cache", year=year, key=minio_key)
        return cached

    # ── Descargar desde el Ministerio ─────────────────────────────────────────
    candidates = _candidate_urls(year)
    last_error = None

    async with httpx.AsyncClient(
        headers={
            "User-Agent": settings.http_user_agent,
            "Accept": "application/octet-stream, */*",
        },
        timeout=300,  # los MDB pueden ser grandes
        follow_redirects=True,
    ) as client:
        for url in candidates:
            try:
                logger.info("trying_conprel_url", year=year, url=url)
                resp = await client.get(url)

                if resp.status_code == 404:
                    continue
                resp.raise_for_status()

                content = resp.content
                if len(content) < 4:
                    continue

                # Desempaquetar ZIP si hace falta (el Ministerio envía ZIP desde 2020)
                if _is_zip(content):
                    content = _extract_mdb_from_zip(content)
                    if content is None:
                        logger.warning("no_mdb_in_zip", url=url)
                        continue

                # Verificar que es un fichero MDB
                if not _is_mdb(content):
                    logger.warning("not_mdb_content", url=url, size=len(content))
                    continue

                # Guardar en temporal
                tmp = tempfile.NamedTemporaryFile(suffix=".mdb", delete=False)
                tmp.write(content)
                tmp.close()
                tmp_path = Path(tmp.name)

                # Subir a MinIO para cache
                await _upload_to_minio(content, minio_key)

                logger.info(
                    "conprel_downloaded",
                    year=year, url=url,
                    size_kb=len(content) // 1024
                )
                return tmp_path

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.debug("url_failed", url=url, status=e.response.status_code)
                continue
            except Exception as e:
                last_error = e
                logger.debug("url_error", url=url, error=str(e))
                continue

    raise RuntimeError(
        f"No se pudo descargar el CONPREL {year}. "
        f"Último error: {last_error}. "
        f"Descarga manual desde: "
        f"https://serviciostelematicosext.hacienda.gob.es/SGFAL/CONPREL"
    )


def _is_zip(content: bytes) -> bool:
    """Detecta fichero ZIP por magic bytes PK\\x03\\x04."""
    return content[:4] == b"PK\x03\x04"


def _extract_mdb_from_zip(content: bytes) -> bytes | None:
    """Extrae el primer fichero .mdb/.accdb de un ZIP en memoria."""
    import io
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                if name.lower().endswith((".mdb", ".accdb")):
                    return zf.read(name)
    except Exception:
        pass
    return None


def _is_mdb(content: bytes) -> bool:
    """Verifica magic bytes de fichero Access MDB/ACCDB."""
    # MDB97-2003: empieza por 0x00 0x01 0x00 0x00
    # ACCDB: empieza por 0x00 0x01 0x00 0x00 (mismos)
    return content[:4] in (
        b"\x00\x01\x00\x00",
        b"\x00\x01\x02\x00",  # variante
    )


async def _from_minio_cache(key: str) -> Path | None:
    """Intenta recuperar el MDB desde la cache de MinIO."""
    import asyncio

    def _download():
        import boto3
        from botocore.exceptions import ClientError
        s3 = boto3.client(
            "s3",
            endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_root_user,
            aws_secret_access_key=settings.minio_root_password,
        )
        tmp = tempfile.NamedTemporaryFile(suffix=".mdb", delete=False)
        try:
            s3.download_fileobj(settings.minio_bucket, key, tmp)
            tmp.close()
            return Path(tmp.name)
        except ClientError:
            tmp.close()
            Path(tmp.name).unlink(missing_ok=True)
            return None

    try:
        return await asyncio.get_running_loop().run_in_executor(None, _download)
    except Exception:
        return None


async def _upload_to_minio(content: bytes, key: str) -> None:
    """Sube el MDB a MinIO como cache."""
    import asyncio
    import io

    def _upload():
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_root_user,
            aws_secret_access_key=settings.minio_root_password,
        )
        try:
            s3.put_object(
                Bucket=settings.minio_bucket,
                Key=key,
                Body=io.BytesIO(content),
                ContentType="application/octet-stream",
            )
        except Exception as e:
            logger.warning("minio_upload_failed", key=key, error=str(e))

    await asyncio.get_running_loop().run_in_executor(None, _upload)

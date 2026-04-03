"""
Descargador de ficheros presupuestarios.

Flujo:
  1. Comprueba si el fichero ya existe en MinIO por URL+SHA256
  2. Si no existe: descarga en streaming, calcula hash, sube a MinIO
  3. Devuelve (ruta_local_temporal, sha256, minio_key)

La ruta local es un NamedTemporaryFile que el llamador debe cerrar/borrar.
El hash SHA256 actúa como clave de deduplicación — si el Ayuntamiento
republica el mismo fichero con otro nombre no se vuelve a procesar.
"""
from __future__ import annotations

import asyncio
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import structlog
from botocore.exceptions import ClientError

from app.config import get_settings
from etl.scraper import DiscoveredFile

logger = structlog.get_logger(__name__)
settings = get_settings()


@dataclass
class DownloadResult:
    local_path: Path          # fichero temporal — borrar tras procesar
    sha256: str
    minio_key: str
    already_existed: bool     # True = estaba en MinIO, no se ha re-descargado


# ── MinIO client (síncrono boto3, se llama desde executor) ───────────────────

def _get_s3():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_root_user,
        aws_secret_access_key=settings.minio_root_password,
    )


def _ensure_bucket() -> None:
    s3 = _get_s3()
    try:
        s3.head_bucket(Bucket=settings.minio_bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            s3.create_bucket(Bucket=settings.minio_bucket)
            logger.info("minio_bucket_created", bucket=settings.minio_bucket)
        else:
            raise


def _minio_key(file_info: DiscoveredFile) -> str:
    return f"presupuesto/{file_info.fiscal_year}/{file_info.file_type}/{file_info.filename}"


def _sha256_exists_in_minio(key: str) -> Optional[str]:
    """Devuelve el SHA256 almacenado en metadatos si el objeto existe, None si no."""
    s3 = _get_s3()
    try:
        head = s3.head_object(Bucket=settings.minio_bucket, Key=key)
        return head.get("Metadata", {}).get("sha256")
    except ClientError:
        return None


def _upload_to_minio(local_path: Path, key: str, sha256: str) -> None:
    s3 = _get_s3()
    with open(local_path, "rb") as f:
        s3.put_object(
            Bucket=settings.minio_bucket,
            Key=key,
            Body=f,
            Metadata={"sha256": sha256},
        )
    logger.info("minio_upload_ok", key=key, sha256=sha256[:12])


def _download_from_minio(key: str, local_path: Path) -> None:
    s3 = _get_s3()
    s3.download_file(settings.minio_bucket, key, str(local_path))


# ── Descarga HTTP ────────────────────────────────────────────────────────────

async def _http_download(url: str, dest: Path) -> str:
    """
    Descarga url a dest en streaming, devuelve SHA256.
    Reintentos: 3 × backoff exponencial.
    """
    h = hashlib.sha256()
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": settings.http_user_agent},
                timeout=settings.http_timeout,
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    with open(dest, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            h.update(chunk)
            return h.hexdigest()
        except httpx.HTTPError as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            logger.warning("download_retry", url=url, attempt=attempt + 1, wait=wait, error=str(e))
            await asyncio.sleep(wait)
    raise RuntimeError("unreachable")


# ── API pública ──────────────────────────────────────────────────────────────

async def download_file(file_info: DiscoveredFile) -> DownloadResult:
    """
    Descarga y almacena un fichero presupuestario.
    Si ya existe en MinIO con el mismo SHA256, no vuelve a descargar.
    Devuelve DownloadResult con ruta local temporal lista para parsear.
    """
    loop = asyncio.get_event_loop()

    # Asegurar bucket existe (operación síncrona rápida)
    await loop.run_in_executor(None, _ensure_bucket)

    key = _minio_key(file_info)
    suffix = Path(file_info.filename).suffix

    # Fichero temporal de trabajo
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    # ¿Ya está en MinIO?
    existing_sha = await loop.run_in_executor(None, _sha256_exists_in_minio, key)
    if existing_sha:
        logger.info("file_already_in_minio", key=key, sha256=existing_sha[:12])
        await loop.run_in_executor(None, _download_from_minio, key, tmp_path)
        return DownloadResult(
            local_path=tmp_path,
            sha256=existing_sha,
            minio_key=key,
            already_existed=True,
        )

    # Descargar desde el portal
    logger.info("downloading_file", url=file_info.url, filename=file_info.filename)
    sha256 = await _http_download(file_info.url, tmp_path)

    # Subir a MinIO
    await loop.run_in_executor(None, _upload_to_minio, tmp_path, key, sha256)

    logger.info(
        "download_complete",
        filename=file_info.filename,
        sha256=sha256[:12],
        size_kb=tmp_path.stat().st_size // 1024,
    )
    return DownloadResult(
        local_path=tmp_path,
        sha256=sha256,
        minio_key=key,
        already_existed=False,
    )

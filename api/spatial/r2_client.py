"""
Cloudflare R2 helper (boto3 S3-compatible).

All boto3 calls are blocking; wrap in run_in_executor before awaiting.
"""

import asyncio
import logging
from pathlib import Path

import boto3
from botocore.config import Config

from config import settings

log = logging.getLogger("geo-stack.r2")


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        aws_access_key_id=settings.r2_access_key,
        aws_secret_access_key=settings.r2_secret_key,
        config=Config(retries={"max_attempts": 3}, signature_version="s3v4"),
        region_name="auto",
    )


def r2_configured() -> bool:
    return bool(settings.r2_access_key and settings.r2_endpoint)


async def upload_file(local_path: Path, key: str, bucket: str) -> None:
    if not r2_configured():
        return
    loop = asyncio.get_running_loop()

    def _run():
        _client().upload_file(str(local_path), bucket, key)
        log.info("R2 upload: %s → %s/%s", local_path.name, bucket, key)

    await loop.run_in_executor(None, _run)


async def delete_object(key: str, bucket: str) -> None:
    if not r2_configured():
        return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: _client().delete_object(Bucket=bucket, Key=key))


async def download_file(key: str, bucket: str, local_path: Path) -> None:
    loop = asyncio.get_running_loop()
    local_path.parent.mkdir(parents=True, exist_ok=True)

    def _run():
        _client().download_file(bucket, key, str(local_path))
        log.info("R2 download: %s/%s → %s", bucket, key, local_path.name)

    await loop.run_in_executor(None, _run)


def gdal_env(bucket: str | None = None) -> dict[str, str]:
    """Env vars that let GDAL read from R2 via /vsis3/."""
    endpoint = settings.r2_endpoint.replace("https://", "").replace("http://", "")
    return {
        "AWS_ACCESS_KEY_ID": settings.r2_access_key,
        "AWS_SECRET_ACCESS_KEY": settings.r2_secret_key,
        "AWS_S3_ENDPOINT": endpoint,
        "AWS_REGION": "auto",
        "AWS_VIRTUAL_HOSTING": "FALSE",
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_USE_TEMP_FILE_FOR_RANDOM_WRITE": "NO",
    }


def vsis3(key: str, bucket: str) -> str:
    return f"/vsis3/{bucket}/{key}"

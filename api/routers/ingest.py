"""
Ingest router — two paths for loading geodata into staging.

Small-file path  (< 100k features, browser-parsed):
  POST /ingest/features   — GeoJSON features → staging.raw_features via SSE

Large-file path (any size, any GDAL format):
  POST /ingest/upload     — stream file → /tmp → detect layers → R2 backup
  POST /ingest/process    — run ogr2ogr as background task (direct → Supabase)
  GET  /ingest/job/{id}   — SSE progress stream
  GET  /ingest/jobs       — list recent jobs
  DELETE /ingest/job/{id} — cancel / clean up

Staging management:
  GET    /ingest/layers          — layers in staging.raw_features
  DELETE /ingest/layer/{name}    — clear a raw_features layer
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from config import settings
from spatial import r2_client
from spatial.postgis_engine import get_postgis_pool

router = APIRouter()
log = logging.getLogger("geo-stack.ingest")

TMP_ROOT = Path("/tmp/geo-uploads")
MAX_FEATURES = 100_000
BATCH_SIZE = 500

VALID_GEOM_TYPES = {
    "Point", "MultiPoint", "LineString", "MultiLineString",
    "Polygon", "MultiPolygon", "GeometryCollection",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _sanitise_table(v: str) -> str:
    parts = v.strip().split(".")
    if len(parts) != 2:
        raise ValueError("Must be schema.table")
    return ".".join(re.sub(r"[^a-z0-9_]", "_", p.lower())[:64] for p in parts)


def _direct_url() -> str:
    """Direct Supabase URL for ogr2ogr (port 5432, COPY mode works)."""
    url = settings.supabase_direct_url or settings.database_url
    if "sslmode" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def _ogr2ogr_bin() -> str:
    for p in ("/usr/bin/ogr2ogr", "/usr/local/bin/ogr2ogr", "ogr2ogr"):
        if shutil.which(p):
            return p
    raise RuntimeError("ogr2ogr not found — is gdal-bin installed?")


def _ogrinfo_bin() -> str:
    for p in ("/usr/bin/ogrinfo", "/usr/local/bin/ogrinfo", "ogrinfo"):
        if shutil.which(p):
            return p
    raise RuntimeError("ogrinfo not found — is gdal-bin installed?")


# ── Layer detection ──────────────────────────────────────────────────────────

def _parse_ogrinfo(output: str) -> list[dict]:
    layers: list[dict] = []
    cur: dict | None = None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Layer name:"):
            cur = {
                "name": line.split(":", 1)[1].strip(),
                "geometry_type": "Unknown",
                "feature_count": -1,
                "zip_member": None,
            }
            layers.append(cur)
        elif cur and line.startswith("Geometry:"):
            cur["geometry_type"] = line.split(":", 1)[1].strip()
        elif cur and line.startswith("Feature Count:"):
            try:
                cur["feature_count"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return layers


def _run_ogrinfo(gdal_path: str) -> list[dict]:
    try:
        r = subprocess.run(
            [_ogrinfo_bin(), "-al", "-so", gdal_path],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "SHAPE_ENCODING": "UTF-8"},
        )
        return _parse_ogrinfo(r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return [{"name": "layer", "geometry_type": "Unknown", "feature_count": -1, "zip_member": None}]


def detect_layers(file_path: Path) -> list[dict]:
    """Return layer list. For ZIP files, lists each SHP as a separate layer."""
    name = file_path.name.lower()

    if name.endswith(".zip"):
        layers = []
        try:
            with zipfile.ZipFile(file_path) as zf:
                shps = sorted(n for n in zf.namelist() if n.lower().endswith(".shp"))
        except zipfile.BadZipFile:
            return _run_ogrinfo(str(file_path))

        for member in shps:
            vsi_path = f"/vsizip/{file_path}/{member}"
            info = _run_ogrinfo(vsi_path)
            for layer in info:
                # Use the SHP basename (no extension) as the display name
                layer["name"] = Path(member).stem
                layer["zip_member"] = member
            layers.extend(info)
        return layers

    return _run_ogrinfo(str(file_path))


def build_ogr_input(file_path: Path, layer_info: dict) -> tuple[str, list[str]]:
    """
    Return (gdal_input_path, extra_args) for the ogr2ogr command.
    extra_args holds the source layer name when needed (GeoPackage, GeoJSON multi-layer).
    """
    name = file_path.name.lower()

    if name.endswith(".zip") and layer_info.get("zip_member"):
        gdal_path = f"/vsizip/{file_path}/{layer_info['zip_member']}"
        return gdal_path, []

    gdal_path = str(file_path)
    layer_name = layer_info["name"]
    # Non-ZIP multi-layer formats: GeoPackage, GDB, etc. — pass layer name as positional arg
    if name.endswith((".gpkg", ".gdb", ".gml")):
        return gdal_path, [layer_name]

    return gdal_path, []


# ── Job DB helpers ────────────────────────────────────────────────────────────

async def _update_job(job_id: str, **kwargs) -> None:
    pool = await get_postgis_pool()
    sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
    vals = list(kwargs.values())
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE staging.ingest_jobs SET {sets}, updated_at = now() WHERE id = $1",
            job_id, *vals,
        )


# ── Background task: ogr2ogr ──────────────────────────────────────────────────

async def _run_ogr2ogr(job_id: str) -> None:
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT * FROM staging.ingest_jobs WHERE id = $1", job_id
        )
    if not job:
        return

    file_path = TMP_ROOT / job_id / job["file_name"]

    # If /tmp was cleared (API restart) and we have an R2 backup, restore it
    if not file_path.exists() and job.get("r2_key") and r2_client.r2_configured():
        log.info("Job %s: /tmp gone, restoring from R2", job_id)
        await _update_job(job_id, status="restoring")
        try:
            await r2_client.download_file(
                job["r2_key"], settings.r2_uploads_bucket, file_path
            )
        except Exception as exc:
            await _update_job(job_id, status="error",
                              error_message=f"File lost and R2 restore failed: {exc}")
            return

    if not file_path.exists():
        await _update_job(job_id, status="error",
                          error_message="Uploaded file is no longer available. Please re-upload.")
        return

    # Find the layer the user selected
    detected = json.loads(job["detected_layers"] or "[]")
    source_layer_name = job["source_layer"]
    if source_layer_name:
        layer_info = next(
            (l for l in detected if l["name"] == source_layer_name), None
        ) or {"name": source_layer_name, "zip_member": None}
    else:
        layer_info = detected[0] if detected else {"name": "layer", "zip_member": None}

    schema = job["target_table"].split(".")[0]
    gdal_input, extra_args = build_ogr_input(file_path, layer_info)

    use_copy = "5432" in _direct_url() or "direct" in _direct_url()
    cmd = [
        _ogr2ogr_bin(),
        "-f", "PostgreSQL",
        f"PG:{_direct_url()}",
        gdal_input,
        *extra_args,
        "-nln", job["target_table"],
        "-t_srs", "EPSG:4326",
        "-nlt", "PROMOTE_TO_MULTI",
        "-lco", "GEOMETRY_NAME=geom",
        "-lco", "FID=id",
        "-lco", "SPATIAL_INDEX=GIST",
        "-lco", f"SCHEMA={schema}",
        "-overwrite" if job["overwrite"] else "-append",
        "-progress",
    ]
    if use_copy:
        cmd += ["--config", "PG_USE_COPY", "YES"]

    log.info("Job %s: running ogr2ogr for %s → %s", job_id, layer_info["name"], job["target_table"])
    await _update_job(job_id, status="processing", pct_complete=0)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "SHAPE_ENCODING": "UTF-8", "OGR_ENABLE_PARTIAL_REPROJECTION": "YES"},
        )

        buf = b""
        last_pct = 0
        while True:
            chunk = await proc.stdout.read(128)
            if not chunk:
                break
            buf += chunk
            pcts = re.findall(rb"(\d+)\.\.\.", buf)
            if pcts:
                pct = int(pcts[-1])
                if pct != last_pct:
                    last_pct = pct
                    await _update_job(job_id, pct_complete=pct)
                # Trim buffer to avoid unbounded growth
                buf = buf[buf.rfind(b"...") + 3:]

        await proc.wait()
        tail = buf.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    f"SELECT COUNT(*) AS c FROM {job['target_table']}"  # noqa: S608
                )
            rows = row["c"] if row else 0
            await _update_job(job_id, status="done", pct_complete=100, rows_inserted=rows)
            log.info("Job %s: done, %d rows in %s", job_id, rows, job["target_table"])
        else:
            await _update_job(job_id, status="error", error_message=tail[:500])
            log.error("Job %s: ogr2ogr failed (rc=%d): %s", job_id, proc.returncode, tail[:200])

    except Exception as exc:
        await _update_job(job_id, status="error", error_message=str(exc)[:500])
        log.exception("Job %s: unexpected error", job_id)

    finally:
        # Clean up /tmp directory for this job
        shutil.rmtree(TMP_ROOT / job_id, ignore_errors=True)


# ════════════════════════════════════════════════════════════════════════════
# Endpoints — large-file server-side path
# ════════════════════════════════════════════════════════════════════════════

@router.post("/upload")
async def upload_file_for_processing(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
):
    """
    Stream an uploaded file to /tmp, detect its layers with ogrinfo,
    and back it up to R2 geo-uploads. Returns job_id + layer list.

    Supported: any format ogr2ogr can read (GeoJSON, KML, GeoPackage, Shapefile ZIP, GeoParquet, …).
    """
    job_id = str(uuid.uuid4())
    job_dir = TMP_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^\w.\-]", "_", file.filename or "upload")
    tmp_path = job_dir / safe_name

    # Stream file to disk
    file_size = 0
    try:
        async with aiofiles.open(tmp_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                await f.write(chunk)
                file_size += len(chunk)
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, f"Failed to save upload: {exc}") from exc

    log.info("Job %s: saved %s (%.1f MB)", job_id, safe_name, file_size / 1_048_576)

    # Detect layers (blocking ogrinfo — run in executor)
    loop = asyncio.get_running_loop()
    try:
        layers = await loop.run_in_executor(None, detect_layers, tmp_path)
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(422, f"Could not inspect file: {exc}") from exc

    if not layers:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(422, "No readable layers found in this file. "
                            "Check that it is a valid vector format.")

    # Create job record
    r2_key = f"{job_id}/{safe_name}" if r2_client.r2_configured() else None
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO staging.ingest_jobs
                (id, file_name, file_size_bytes, r2_key, detected_layers, status)
            VALUES ($1, $2, $3, $4, $5::jsonb, 'pending')
            """,
            job_id, safe_name, file_size, r2_key, json.dumps(layers),
        )

    # Back up to R2 in background (non-blocking)
    if r2_key:
        background_tasks.add_task(
            r2_client.upload_file, tmp_path, r2_key, settings.r2_uploads_bucket
        )

    return {"job_id": job_id, "file_name": safe_name, "file_size_bytes": file_size, "layers": layers}


class ProcessRequest(BaseModel):
    job_id: str
    target_table: str
    source_layer: str | None = None
    overwrite: bool = False

    @field_validator("target_table")
    @classmethod
    def validate_table(cls, v: str) -> str:
        try:
            return _sanitise_table(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


@router.post("/process")
async def process_job(req: ProcessRequest, background_tasks: BackgroundTasks):
    """
    Start an ogr2ogr background job for a previously uploaded file.
    Stream progress via GET /ingest/job/{job_id}.
    """
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT id, status FROM staging.ingest_jobs WHERE id = $1", req.job_id
        )
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] not in ("pending", "error"):
        raise HTTPException(400, f"Job is already {job['status']} — cannot reprocess")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE staging.ingest_jobs
            SET target_table = $2, source_layer = $3, overwrite = $4, status = 'queued',
                pct_complete = 0, error_message = NULL, updated_at = now()
            WHERE id = $1
            """,
            req.job_id, req.target_table, req.source_layer, req.overwrite,
        )

    background_tasks.add_task(_run_ogr2ogr, req.job_id)
    return {"job_id": req.job_id, "status": "queued"}


@router.get("/job/{job_id}")
async def stream_job_progress(job_id: str):
    """SSE stream for a running or completed ingest job."""
    pool = await get_postgis_pool()

    async def _stream():
        terminal = {"done", "error"}
        for _ in range(3600):  # max ~1 hour at 1 s/tick
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT status, pct_complete, rows_inserted, rows_total, error_message
                    FROM staging.ingest_jobs WHERE id = $1
                    """,
                    job_id,
                )
            if not row:
                yield f"data: {json.dumps({'error': 'job not found'})}\n\n"
                return

            payload = {
                "status": row["status"],
                "pct": row["pct_complete"] or 0,
                "rows_inserted": row["rows_inserted"] or 0,
                "error": row["error_message"],
            }
            yield f"data: {json.dumps(payload)}\n\n"

            if row["status"] in terminal:
                return

            await asyncio.sleep(1)

        yield f"data: {json.dumps({'error': 'timeout'})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs")
async def list_jobs():
    """List recent ingest jobs (last 50)."""
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, file_name, file_size_bytes, target_table, source_layer,
                   status, pct_complete, rows_inserted, error_message,
                   created_at, updated_at
            FROM staging.ingest_jobs
            ORDER BY created_at DESC
            LIMIT 50
            """
        )
    return [
        {
            "job_id": str(r["id"]),
            "file_name": r["file_name"],
            "file_size_mb": round(r["file_size_bytes"] / 1_048_576, 1) if r["file_size_bytes"] else None,
            "target_table": r["target_table"],
            "source_layer": r["source_layer"],
            "status": r["status"],
            "pct": r["pct_complete"],
            "rows_inserted": r["rows_inserted"],
            "error": r["error_message"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]


@router.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """Delete a job record and its R2 backup file."""
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM staging.ingest_jobs WHERE id = $1 RETURNING r2_key", job_id
        )
    if not row:
        raise HTTPException(404, "Job not found")

    # Clean R2 backup
    if row["r2_key"]:
        await r2_client.delete_object(row["r2_key"], settings.r2_uploads_bucket)

    # Clean /tmp
    shutil.rmtree(TMP_ROOT / job_id, ignore_errors=True)
    return {"deleted": job_id}


# ════════════════════════════════════════════════════════════════════════════
# Endpoints — small-file browser-parsed path (GeoJSON, KML, CSV, small SHP)
# ════════════════════════════════════════════════════════════════════════════

class IngestRequest(BaseModel):
    source: str
    layer_name: str
    features: list[dict]

    @field_validator("layer_name")
    @classmethod
    def sanitise_layer_name(cls, v: str) -> str:
        cleaned = re.sub(r"[^a-z0-9_]", "_", v.lower().strip())[:64]
        if not cleaned:
            raise ValueError("layer_name cannot be empty")
        return cleaned

    @field_validator("source")
    @classmethod
    def sanitise_source(cls, v: str) -> str:
        return v.strip()[:255]


@router.post("/features")
async def ingest_features(req: IngestRequest):
    """
    Insert GeoJSON features into staging.raw_features, streaming progress via SSE.
    Max 100,000 features. For larger datasets use POST /ingest/upload instead.
    """
    if not req.features:
        raise HTTPException(400, "No features provided")
    if len(req.features) > MAX_FEATURES:
        raise HTTPException(
            400,
            f"Max {MAX_FEATURES:,} features — got {len(req.features):,}. "
            "Use POST /ingest/upload for larger files.",
        )

    pool = await get_postgis_pool()
    total = len(req.features)

    async def _stream():
        inserted = 0
        skipped = 0
        errors: list[str] = []
        start = time.perf_counter()

        async with pool.acquire() as conn:
            for batch_start in range(0, total, BATCH_SIZE):
                batch = req.features[batch_start: batch_start + BATCH_SIZE]
                rows = []
                for feat in batch:
                    geom = feat.get("geometry")
                    if not geom or geom.get("type") not in VALID_GEOM_TYPES:
                        skipped += 1
                        continue
                    rows.append((
                        req.source, req.layer_name,
                        json.dumps(feat.get("properties") or {}),
                        json.dumps(geom),
                    ))

                if rows:
                    try:
                        await conn.executemany(
                            """
                            INSERT INTO staging.raw_features
                                (source, layer_name, properties, geom)
                            VALUES (
                                $1, $2, $3::jsonb,
                                ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON($4), 4326))
                            )
                            """,
                            rows,
                        )
                        inserted += len(rows)
                    except Exception as exc:
                        err_msg = str(exc)[:300]
                        errors.append(err_msg)
                        skipped += len(rows)
                        log.error("Ingest batch offset=%d failed: %s", batch_start, exc)

                elapsed = time.perf_counter() - start
                pct = round(inserted / total * 100, 1) if total else 0
                yield f"data: {json.dumps({'inserted': inserted, 'total': total, 'pct': pct, 'skipped': skipped, 'elapsed_s': round(elapsed, 1)})}\n\n"

        elapsed = time.perf_counter() - start
        final = {"done": True, "inserted": inserted, "total": total,
                 "skipped": skipped, "errors": errors[:5], "elapsed_s": round(elapsed, 1)}
        log.info("Ingest: layer=%s inserted=%d/%d skipped=%d", req.layer_name, inserted, total, skipped)
        yield f"data: {json.dumps(final)}\n\n"

    return StreamingResponse(
        _stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/layers")
async def list_staging_layers():
    """List all layers in staging.raw_features with counts."""
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT layer_name, source, COUNT(*) AS feature_count,
                   MAX(imported_at) AS last_imported,
                   ST_AsGeoJSON(ST_Extent(geom))::jsonb AS bbox_geojson
            FROM staging.raw_features
            GROUP BY layer_name, source
            ORDER BY last_imported DESC
            LIMIT 50
        """)
    return [
        {
            "layer_name": r["layer_name"],
            "source": r["source"],
            "feature_count": r["feature_count"],
            "last_imported": r["last_imported"].isoformat() if r["last_imported"] else None,
            "bbox": r["bbox_geojson"],
        }
        for r in rows
    ]


@router.delete("/layer/{layer_name}")
async def delete_staging_layer(layer_name: str):
    """Remove all features for a layer from staging.raw_features."""
    clean = re.sub(r"[^a-z0-9_]", "_", layer_name.lower())
    pool = await get_postgis_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM staging.raw_features WHERE layer_name = $1", clean
        )
    deleted = int(result.split()[-1])
    log.info("Deleted staging layer: %s (%d rows)", clean, deleted)
    return {"deleted": deleted, "layer": clean}

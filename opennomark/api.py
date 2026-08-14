"""FastAPI backend for OpenNoMark."""

import asyncio
import json
import math
import os
import re
import uuid
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.background import BackgroundTask

from . import __version__

app = FastAPI(title="OpenNoMark", version=__version__)

DESKTOP_MODE = os.environ.get("OPENNOMARK_DESKTOP") == "1"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[] if DESKTOP_MODE else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-loaded, shared pipeline. Model construction is guarded because request
# inference runs in worker threads instead of blocking the ASGI event loop.
_pipeline = None
_pipeline_init_lock = threading.Lock()
_pipeline_preload_thread = None
_model_state_lock = threading.Lock()
_model_state = {
    "status": "idle",
    "error": None,
}


def _set_model_state(status: str, error: str | None = None) -> None:
    with _model_state_lock:
        _model_state["status"] = status
        _model_state["error"] = error


def model_state() -> dict[str, str | None]:
    with _model_state_lock:
        return dict(_model_state)


def _configured_concurrency() -> int:
    """Choose a conservative device-aware inference limit."""
    try:
        import torch

        default = 2 if torch.backends.mps.is_available() else 1
    except ModuleNotFoundError:
        # API-only tests can exercise routing with a stub pipeline. Real image
        # processing still requires the project's core Torch dependency.
        default = 1
    configured = os.environ.get("OPENNOMARK_MAX_CONCURRENCY")
    if configured is None:
        return default
    try:
        return max(1, min(4, int(configured)))
    except ValueError:
        return default


PROCESSING_CONCURRENCY = _configured_concurrency()
_processing_slots = asyncio.Semaphore(PROCESSING_CONCURRENCY)
configured_data_dir = os.environ.get("OPENNOMARK_DATA_DIR")
if configured_data_dir:
    runtime_dir = Path(configured_data_dir).expanduser() / "runtime"
    UPLOAD_DIR = runtime_dir / "uploads"
    OUTPUT_DIR = runtime_dir / "outputs"
else:
    UPLOAD_DIR = Path(tempfile.gettempdir()) / "opennomark_uploads"
    OUTPUT_DIR = Path(tempfile.gettempdir()) / "opennomark_outputs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class BatchDownloadItem(BaseModel):
    job_id: str
    filename: str


class BatchDownloadRequest(BaseModel):
    items: list[BatchDownloadItem]


def _parse_manual_regions(raw: str) -> list[dict[str, float]]:
    """Validate normalized user-confirmed repair rectangles."""
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(422, "Manual regions must be valid JSON") from exc

    if not isinstance(payload, list) or not 1 <= len(payload) <= 8:
        raise HTTPException(422, "Supply between 1 and 8 manual regions")

    normalized = []
    total_area = 0.0
    for item in payload:
        if not isinstance(item, dict):
            raise HTTPException(422, "Each manual region must be an object")
        try:
            x = float(item["x"])
            y = float(item["y"])
            width = float(item["width"])
            height = float(item["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, "Manual region coordinates are invalid") from exc

        values = (x, y, width, height)
        if not all(math.isfinite(value) for value in values):
            raise HTTPException(422, "Manual region coordinates must be finite")
        if (
            x < 0
            or y < 0
            or width < 0.005
            or height < 0.005
            or x + width > 1.000001
            or y + height > 1.000001
        ):
            raise HTTPException(422, "Manual regions must stay inside the image")

        total_area += width * height
        normalized.append({"x": x, "y": y, "width": width, "height": height})

    if total_area > 0.35:
        raise HTTPException(422, "Manual regions cover too much of the image")
    return normalized


def _output_for_job(job_id: str) -> Path | None:
    """Resolve a generated output without accepting arbitrary paths."""
    if not re.fullmatch(r"[0-9a-f]{8}", job_id):
        return None
    return next(OUTPUT_DIR.glob(f"{job_id}_clean.*"), None)


def _unique_archive_name(filename: str, suffix: str, used: set[str]) -> str:
    """Build a readable, collision-free filename for a batch archive."""
    safe_name = Path(filename.replace("\\", "/")).name or f"result{suffix}"
    source = Path(safe_name)
    ext = suffix
    stem = source.stem or "result"
    candidate = f"clean_{stem}{ext}"
    index = 2
    while candidate in used:
        candidate = f"clean_{stem}_{index}{ext}"
        index += 1
    used.add(candidate)
    return candidate


def _create_pipeline():
    from .pipeline import WatermarkRemovalPipeline

    pipeline = WatermarkRemovalPipeline()
    # OWLv2 is otherwise lazy-loaded by WatermarkLocalizer. Warm it here while
    # model initialization is still serialized so concurrent first requests do
    # not race and allocate duplicate detector instances.
    pipeline.localizer.detector
    return pipeline


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        with _pipeline_init_lock:
            if _pipeline is None:
                _set_model_state("loading")
                try:
                    _pipeline = _create_pipeline()
                except Exception as exc:
                    _set_model_state("error", str(exc))
                    raise
                else:
                    _set_model_state("ready")
    return _pipeline


def start_pipeline_preload() -> threading.Thread:
    """Warm the desktop models without blocking the local HTTP server."""
    global _pipeline_preload_thread
    if _pipeline_preload_thread is not None and _pipeline_preload_thread.is_alive():
        return _pipeline_preload_thread

    def preload() -> None:
        try:
            get_pipeline()
        except Exception:
            # The error is exposed through /api/health and a later request can
            # retry initialization after the user fixes connectivity or disk
            # space.
            pass

    _pipeline_preload_thread = threading.Thread(
        target=preload,
        name="opennomark-model-preload",
        daemon=True,
    )
    _pipeline_preload_thread.start()
    return _pipeline_preload_thread


def _save_upload(upload: UploadFile, input_path: Path) -> None:
    with open(input_path, "wb") as file:
        shutil.copyfileobj(upload.file, file)


async def _process_upload(upload: UploadFile, pipeline) -> dict:
    if not upload.content_type or not upload.content_type.startswith("image/"):
        return {"filename": upload.filename, "error": "Not an image file"}

    job_id = uuid.uuid4().hex[:8]
    ext = os.path.splitext(upload.filename or "image.png")[1] or ".png"
    input_path = UPLOAD_DIR / f"{job_id}_input{ext}"
    output_path = OUTPUT_DIR / f"{job_id}_clean{ext}"

    try:
        await asyncio.to_thread(_save_upload, upload, input_path)
        async with _processing_slots:
            _, meta = await asyncio.to_thread(
                pipeline.process,
                str(input_path),
                str(output_path),
            )
        if meta["status"] == "partial":
            return {
                "filename": upload.filename,
                "status": "error",
                "watermarks_found": meta["watermarks_found"],
                "download_url": None,
                "error": "Residual watermark evidence remained after validation",
            }
        if meta["status"] == "no_watermark":
            # An unchanged image is still a valid batch result. Keeping a copy
            # in the output directory makes single and ZIP downloads consistent.
            await asyncio.to_thread(shutil.copyfile, input_path, output_path)

        return {
            "filename": upload.filename,
            "job_id": job_id,
            "status": meta["status"],
            "watermarks_found": meta["watermarks_found"],
            "download_url": f"/api/download/{job_id}{ext}",
        }
    except Exception as exc:
        return {
            "filename": upload.filename,
            "status": "error",
            "watermarks_found": 0,
            "download_url": None,
            "error": str(exc),
        }
    finally:
        input_path.unlink(missing_ok=True)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "max_concurrency": PROCESSING_CONCURRENCY,
        "desktop": DESKTOP_MODE,
        "models": model_state(),
    }


@app.post("/api/remove")
async def remove_watermark(files: list[UploadFile] = File(...)):
    """Remove watermarks with bounded, shared-model concurrency."""
    pipeline = await asyncio.to_thread(get_pipeline)
    results = await asyncio.gather(
        *(_process_upload(upload, pipeline) for upload in files)
    )
    return {"results": results}


@app.post("/api/remove-manual")
async def remove_manual_watermark(
    file: UploadFile = File(...),
    regions: str = Form(...),
):
    """Repair only the rectangles explicitly selected by the user."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(422, "Not an image file")

    normalized_regions = _parse_manual_regions(regions)
    pipeline = await asyncio.to_thread(get_pipeline)
    job_id = uuid.uuid4().hex[:8]
    ext = os.path.splitext(file.filename or "image.png")[1] or ".png"
    input_path = UPLOAD_DIR / f"{job_id}_manual_input{ext}"
    output_path = OUTPUT_DIR / f"{job_id}_clean{ext}"

    try:
        await asyncio.to_thread(_save_upload, file, input_path)
        async with _processing_slots:
            _, meta = await asyncio.to_thread(
                pipeline.process_manual,
                str(input_path),
                normalized_regions,
                str(output_path),
            )
        return {
            "results": [
                {
                    "filename": file.filename,
                    "job_id": job_id,
                    "status": meta["status"],
                    "watermarks_found": meta["watermarks_found"],
                    "download_url": f"/api/download/{job_id}{ext}",
                }
            ]
        }
    except Exception as exc:
        return {
            "results": [
                {
                    "filename": file.filename,
                    "status": "error",
                    "watermarks_found": 0,
                    "download_url": None,
                    "error": str(exc),
                }
            ]
        }
    finally:
        input_path.unlink(missing_ok=True)


@app.get("/api/download/{filename}")
def download(filename: str):
    """Download a processed image."""
    job_id = Path(filename).stem.replace("_clean", "")
    file_path = _output_for_job(job_id)
    if file_path:
        return FileResponse(file_path, filename=f"clean_{file_path.name}")
    raise HTTPException(404, "File not found")


@app.post("/api/download-batch")
def download_batch(request: BatchDownloadRequest):
    """Bundle all available processed outputs into one ZIP download."""
    if not request.items:
        raise HTTPException(400, "No files requested")

    archive_file = tempfile.NamedTemporaryFile(
        prefix="opennomark_batch_", suffix=".zip", delete=False
    )
    archive_path = Path(archive_file.name)
    archive_file.close()
    used_names: set[str] = set()
    included = 0
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for item in request.items:
                file_path = _output_for_job(item.job_id)
                if not file_path:
                    continue
                archive_name = _unique_archive_name(item.filename, file_path.suffix, used_names)
                bundle.write(file_path, arcname=archive_name)
                included += 1
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise

    if not included:
        archive_path.unlink(missing_ok=True)
        raise HTTPException(404, "No processed files found")

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="opennomark-results.zip",
        background=BackgroundTask(archive_path.unlink, missing_ok=True),
    )


# Serve frontend static files if they exist. PyInstaller extracts bundled data
# under ``sys._MEIPASS``; source checkouts continue to use frontend/dist.
configured_frontend_dir = os.environ.get("OPENNOMARK_FRONTEND_DIR")
if configured_frontend_dir:
    FRONTEND_DIR = Path(configured_frontend_dir).expanduser()
elif getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    FRONTEND_DIR = Path(sys._MEIPASS) / "frontend" / "dist"
else:
    FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

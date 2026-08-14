"""Download and verify every model required by the offline desktop build."""

from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
from pathlib import Path


MANIFEST_NAME = "offline-models.json"


def configure_model_environment(root: Path, *, offline: bool) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        {
            "OPENNOMARK_MODEL_DIR": str(root),
            "HF_HOME": str(root / "huggingface"),
            "HF_HUB_CACHE": str(root / "huggingface" / "hub"),
            "TORCH_HOME": str(root / "torch"),
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }
    )
    if offline:
        os.environ.update(
            {
                "OPENNOMARK_OFFLINE_MODE": "1",
                "HF_HUB_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_XET": "1",
            }
        )
    else:
        for key in (
            "OPENNOMARK_OFFLINE_MODE",
            "HF_HUB_OFFLINE",
            "HF_DATASETS_OFFLINE",
            "TRANSFORMERS_OFFLINE",
            "HF_HUB_DISABLE_XET",
        ):
            os.environ.pop(key, None)
    return root


def model_manifest() -> dict:
    from opennomark.detector import DEFAULT_MODEL_ID
    from opennomark.inpainter import LAMA_MODEL_URL
    from opennomark.text_detector import (
        DEFAULT_DETECTION_MODEL_ID,
        DEFAULT_RECOGNITION_MODEL_ID,
    )

    return {
        "schema": 1,
        "models": {
            "owlv2": DEFAULT_MODEL_ID,
            "ocr_detection": DEFAULT_DETECTION_MODEL_ID,
            "ocr_recognition": DEFAULT_RECOGNITION_MODEL_ID,
            "lama": LAMA_MODEL_URL,
        },
    }


def load_models(*, local_files_only: bool) -> None:
    from transformers import (
        AutoImageProcessor,
        AutoModelForObjectDetection,
        AutoModelForTextRecognition,
        Owlv2ForObjectDetection,
        Owlv2Processor,
    )

    expected = model_manifest()["models"]
    kwargs = {"local_files_only": local_files_only}
    loaders = (
        ("OWLv2 processor", Owlv2Processor, expected["owlv2"]),
        ("OWLv2 detector", Owlv2ForObjectDetection, expected["owlv2"]),
        ("OCR detection processor", AutoImageProcessor, expected["ocr_detection"]),
        ("OCR detection model", AutoModelForObjectDetection, expected["ocr_detection"]),
        ("OCR recognition processor", AutoImageProcessor, expected["ocr_recognition"]),
        ("OCR recognition model", AutoModelForTextRecognition, expected["ocr_recognition"]),
    )
    for label, loader, model_id in loaders:
        print(f"Loading {label}: {model_id}", flush=True)
        loaded = loader.from_pretrained(model_id, **kwargs)
        del loaded
        gc.collect()

    from opennomark.inpainter import LamaInpainter, _lama_model_path

    lama_path = _lama_model_path()
    if local_files_only and not lama_path.is_file():
        raise FileNotFoundError(f"Bundled LaMa checkpoint is missing: {lama_path}")
    print(f"Loading Big-LaMa checkpoint: {lama_path}", flush=True)
    inpainter = LamaInpainter(device="cpu")
    del inpainter
    gc.collect()


def write_manifest(root: Path) -> None:
    manifest_path = root / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(model_manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote offline model manifest: {manifest_path}", flush=True)


def materialize_cache_symlinks(root: Path) -> None:
    """Replace Hugging Face cache symlinks with files for Windows packaging.

    GitHub's Windows runners can create cache symlinks, but the 7-Zip binary
    used by electron-builder cannot add those links to an NSIS archive.
    Materializing only the generated bundle keeps normal user caches intact.
    """
    links = [path for path in root.rglob("*") if path.is_symlink()]
    for link in links:
        target = link.resolve(strict=True)
        if not target.is_file():
            raise RuntimeError(f"Unsupported model-cache symlink: {link} -> {target}")
        link.unlink()
        shutil.copy2(target, link)
    print(f"Materialized {len(links)} model-cache symlinks", flush=True)


def validate_manifest(root: Path) -> None:
    manifest_path = root / MANIFEST_NAME
    try:
        actual = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Offline model manifest is invalid: {manifest_path}") from exc
    if actual != model_manifest():
        raise SystemExit("Offline model manifest does not match this OpenNoMark build")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("download", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    root = configure_model_environment(
        args.output,
        offline=args.action == "verify",
    )
    if args.action == "verify":
        validate_manifest(root)
        load_models(local_files_only=True)
        print("Offline model verification passed", flush=True)
    else:
        load_models(local_files_only=False)
        materialize_cache_symlinks(root)
        write_manifest(root)


if __name__ == "__main__":
    main()

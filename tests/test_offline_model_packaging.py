"""Tests for the complete offline desktop model bundle."""

import importlib.util
import os
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "packaging" / "prepare_offline_models.py"
SPEC = importlib.util.spec_from_file_location("prepare_offline_models", SCRIPT_PATH)
assert SPEC and SPEC.loader
OFFLINE_MODELS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OFFLINE_MODELS)


def test_materialize_cache_symlinks(tmp_path):
    blob = tmp_path / "hub" / "blobs" / "model"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"model weights")

    snapshot = tmp_path / "hub" / "snapshots" / "revision" / "model.bin"
    snapshot.parent.mkdir(parents=True)
    try:
        snapshot.symlink_to(os.path.relpath(blob, snapshot.parent))
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    OFFLINE_MODELS.materialize_cache_symlinks(tmp_path)

    assert not snapshot.is_symlink()
    assert snapshot.read_bytes() == b"model weights"
    assert blob.read_bytes() == b"model weights"

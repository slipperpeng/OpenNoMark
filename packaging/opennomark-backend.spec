# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


repo_root = Path(SPECPATH).resolve().parent
frontend_dist = repo_root / "frontend" / "dist"
if not frontend_dist.exists():
    raise SystemExit("frontend/dist is missing; run the frontend build before PyInstaller")

datas = [
    (str(frontend_dist), "frontend/dist"),
    (str(repo_root / "opennomark" / "assets"), "opennomark/assets"),
    (str(repo_root / "LICENSE"), "."),
]
datas += collect_data_files("transformers", include_py_files=False)
datas += collect_data_files("huggingface_hub", include_py_files=False)

for distribution in (
    "fastapi",
    "huggingface-hub",
    "numpy",
    "opencv-python",
    "safetensors",
    "tokenizers",
    "torch",
    "torchvision",
    "transformers",
    "uvicorn",
):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        pass

hiddenimports = []
for package in (
    "uvicorn",
    "transformers.models.auto",
    "transformers.models.owlv2",
    "transformers.models.pp_ocrv5_mobile_det",
    "transformers.models.pp_ocrv5_mobile_rec",
):
    hiddenimports += collect_submodules(package)

a = Analysis(
    [str(repo_root / "packaging" / "desktop_backend.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="opennomark-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="opennomark-backend",
)

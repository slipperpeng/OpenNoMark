# Desktop packaging

OpenNoMark's desktop distribution keeps the existing React workbench and
FastAPI processing core. Electron owns the native window and launches a
PyInstaller-built Python sidecar that serves both the API and `frontend/dist`
on a random loopback port.

## Development

Requirements: Python 3.12, uv, Node.js 22+, and npm.

```bash
uv sync --frozen --extra api --extra desktop
npm ci --prefix frontend
npm ci --prefix desktop
npm --prefix frontend run build
npm --prefix desktop run dev
```

Set `OPENNOMARK_NO_PRELOAD=1` when you only need to smoke-test the desktop
window without downloading the model weights. Packaged builds preload the
models in the background by default.

The standard desktop shell stores models and runtime data under Electron's
per-user application data directory. Its first launch downloads OWLv2,
Big-LaMa, and the OCR models when needed. The separate offline Windows build
bundles those weights and never contacts a model host at runtime.

## Build an installer

Build on the same operating system and CPU architecture as the installer you
want to distribute.

```bash
# macOS: creates a DMG under desktop/release/
npm --prefix desktop run dist:mac

# Windows: creates an NSIS installer under desktop/release/
npm --prefix desktop run dist:win
```

PyInstaller uses one-folder mode because Torch and Transformers are more
reliable as a sidecar directory than as a self-extracting one-file binary.

## Build the complete offline Windows installer

The offline target creates one self-extracting NSIS installer named
`OpenNoMark-Offline-<version>-win-x64.exe`. The installed application still
uses a normal directory layout internally, but the recipient only needs the
single installer file. All four model families are included:

- OWLv2 base patch-16 ensemble
- PP-OCRv5 mobile text detection
- PP-OCRv5 mobile text recognition
- Big-LaMa inpainting

On an online Windows x64 build machine, run:

```bash
npm --prefix desktop run dist:win:offline
```

The build downloads the exact model revisions resolved by Hugging Face,
verifies every model again with network access disabled, and then copies the
verified cache into Electron's read-only `resources/models` directory. At
runtime, the presence of `offline-models.json` enables Hugging Face and
Transformers offline modes. Model data is read directly from the installed
application; no first-run download is required.

Expect a large installer and several gigabytes of installed size because it
also contains Electron, Python, Torch, Transformers, and the model weights.
The target computer should have at least 16 GB of memory. See
[`third-party-models.md`](third-party-models.md) for model sources and license
notices.

## CI builds

Run the **Desktop installers** workflow manually in GitHub Actions, or push a
tag such as `desktop-v0.2.0`. The workflow publishes unsigned macOS and Windows
artifacts. Public distribution should add:

- Apple Developer ID signing and notarization for macOS.
- Authenticode signing for Windows to reduce SmartScreen warnings.
- A review of the repository and model licenses before redistribution.

Run **Offline Windows installer** manually, or push a tag such as
`desktop-offline-v0.2.0`, to build the complete offline Windows x64 installer.

## Runtime security

- The backend binds only to `127.0.0.1` on a random port.
- Electron disables Node.js integration and opens external HTTPS links in the
  system browser.
- Desktop mode disables the development server's wildcard CORS policy.
- Downloads and uploads stay in the application's user-data/runtime folder.

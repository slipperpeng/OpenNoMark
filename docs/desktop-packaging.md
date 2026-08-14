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

The desktop shell stores models and runtime data under Electron's per-user
application data directory. The first launch downloads OWLv2, Big-LaMa, and
the OCR models when needed. These weights are deliberately not copied into the
installer.

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

## CI builds

Run the **Desktop installers** workflow manually in GitHub Actions, or push a
tag such as `desktop-v0.2.0`. The workflow publishes unsigned macOS and Windows
artifacts. Public distribution should add:

- Apple Developer ID signing and notarization for macOS.
- Authenticode signing for Windows to reduce SmartScreen warnings.
- A review of the repository and model licenses before redistribution.

## Runtime security

- The backend binds only to `127.0.0.1` on a random port.
- Electron disables Node.js integration and opens external HTTPS links in the
  system browser.
- Desktop mode disables the development server's wildcard CORS policy.
- Downloads and uploads stay in the application's user-data/runtime folder.

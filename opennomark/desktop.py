"""Desktop sidecar entry point for Electron and other native wrappers."""

from __future__ import annotations

import argparse
import os


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the OpenNoMark desktop backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--log-level", default="warning")
    parser.add_argument(
        "--no-preload-models",
        action="store_true",
        help="Start the UI without downloading or loading models in the background",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")

    os.environ.setdefault("OPENNOMARK_DESKTOP", "1")

    import uvicorn

    from . import api

    if not args.no_preload_models:
        api.start_pipeline_preload()

    uvicorn.run(
        api.app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        access_log=False,
    )


if __name__ == "__main__":
    main()

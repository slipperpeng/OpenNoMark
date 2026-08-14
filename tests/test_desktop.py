"""Tests for the packaged desktop backend entry point."""

import pytest

from opennomark.desktop import build_parser


def test_desktop_parser_accepts_loopback_port():
    args = build_parser().parse_args(["--port", "49123"])
    assert args.host == "127.0.0.1"
    assert args.port == 49123
    assert args.no_preload_models is False


def test_desktop_parser_requires_port():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])

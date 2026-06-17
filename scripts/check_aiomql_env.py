#!/usr/bin/env python3
"""Check an aiomql project environment without connecting to MetaTrader 5."""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import sys
from pathlib import Path
from typing import Any


SECRET_KEYS = {"password", "token", "secret", "api_key", "apikey", "key"}


def redact_config(data: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if any(secret in key.lower() for secret in SECRET_KEYS):
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, str(exc)


def check_project(project: Path) -> int:
    project = project.resolve()
    print(f"Project: {project}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {platform.system()} {platform.release()}")

    py_ok = sys.version_info >= (3, 13)
    is_windows = platform.system().lower() == "windows"
    runtime_ok = py_ok and is_windows

    print(f"Python 3.13 or newer: {'OK' if py_ok else 'WARN'}")
    print(f"Windows for live MT5: {'OK' if is_windows else 'WARN'}")
    print(f"aiomql live runtime ready: {'OK' if runtime_ok else 'WARN'}")

    try:
        aiomql = importlib.import_module("aiomql")
        version = getattr(aiomql, "__version__", "unknown")
        print(f"aiomql import: OK, version={version}")
    except Exception as exc:
        print(f"aiomql import: FAIL, {exc}")

    expected = [
        "requirements.txt",
        "requirements-aiomql.txt",
        "aiomql.json",
        "aiomql.json.example",
        ".gitignore",
        "strategies",
        "bot.py",
    ]
    for name in expected:
        path = project / name
        print(f"{name}: {'found' if path.exists() else 'missing'}")

    config_path = project / "aiomql.json"
    if config_path.exists():
        config, error = read_json(config_path)
        if error:
            print(f"aiomql.json parse: FAIL, {error}")
        else:
            print("aiomql.json parse: OK")
            print(json.dumps(redact_config(config or {}), indent=2))
    else:
        print("aiomql.json: not found. This is OK for Linux research; demo/live MT5 needs a local file on Windows.")

    if not runtime_ok:
        print("Install note: aiomql/MetaTrader5 should be installed on Windows with Python 3.13+.")
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check an aiomql project environment without connecting to MetaTrader 5.")
    parser.add_argument("--project", default=".", help="Project root to inspect")
    args = parser.parse_args()
    return check_project(Path(args.project))


if __name__ == "__main__":
    raise SystemExit(main())

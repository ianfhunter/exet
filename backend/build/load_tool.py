"""Load exet/tools/*.py modules (hyphenated filenames)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_tool_module(stem: str, tools_dir: Path) -> ModuleType:
    path = tools_dir / f"{stem}.py"
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(stem.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

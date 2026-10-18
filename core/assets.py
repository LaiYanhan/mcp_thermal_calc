"""JSON 资产目录与文件命名，不依赖进程工作目录。"""

import os
import re
from pathlib import Path

from core.storage import read_json


def asset_directory(category: str) -> Path:
    root = Path(os.environ.get("THERMAL_CALC_ASSET_DIR", Path(__file__).resolve().parents[1]))
    return root.resolve() / category


def validate_filename(filename: str) -> None:
    if (not isinstance(filename, str) or
            not re.fullmatch(r"[\w\u4e00-\u9fff][\w\u4e00-\u9fff.-]*\.json", filename) or
            ".." in filename or
            filename.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}):
        raise ValueError("文件名必须为 JSON 文件名，不允许目录、保留名或 Python 文件")


def definition_path(category: str, identifier: str, filename: str | None = None, name: str = "") -> Path:
    directory = asset_directory(category)
    if filename is None:
        for path in sorted(directory.rglob("*.json")):
            if read_json(path).get("id") == identifier:
                return path
        stem = re.sub(r"[^\w\u4e00-\u9fff]", "", name)
        filename = f"{stem}_{identifier}.json" if category == "formulas" else f"{identifier}.json"
    validate_filename(filename)
    path = directory / filename
    if path.exists() and read_json(path).get("id") != identifier:
        raise ValueError("JSON 文件名已被另一项定义使用")
    return path

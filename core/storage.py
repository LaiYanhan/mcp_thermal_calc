"""本地工程数据的原子 JSON 存取，不执行持久化文件中的代码。"""

import json
import os
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from functools import wraps


engine_lock = RLock()


def synchronized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with engine_lock:
            return function(*args, **kwargs)
    return wrapped


def data_directory() -> Path:
    default = Path(__file__).resolve().parents[1] / ".data"
    return Path(os.environ.get("THERMAL_CALC_DATA_DIR", default)).resolve()


def record_path(category: str, identifier: str) -> Path:
    filename = sha256(identifier.encode("utf-8")).hexdigest() + ".json"
    return data_directory() / category / filename


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, data) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

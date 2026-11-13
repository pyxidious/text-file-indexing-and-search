"""Serializzazione UTF-8 canonica: ordinamenti espliciti e newline LF."""
import hashlib
import json
from pathlib import Path


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True,
                                       indent=2, allow_nan=False) + "\n").encode("utf-8"))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(value: str, fallback: str = "file") -> str:
    name = _SAFE.sub("_", Path(value or fallback).name).strip("._")
    return name or fallback


class StorageBackend(Protocol):
    root: Path
    def write_json(self, relative: str, payload: Any) -> Path: ...
    def read_json(self, relative: str) -> Any: ...
    def write_text(self, relative: str, text: str) -> Path: ...
    def read_text(self, relative: str) -> str: ...


@dataclass
class LocalStorageBackend:
    root: Path

    def __post_init__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ("uploads", "runs", "sessions", "reports", "logs", "config", "tmp"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> Path:
        p = (self.root / relative).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError("Storage path escapes configured root")
        return p

    def write_json(self, relative: str, payload: Any) -> Path:
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(path)
        return path

    def read_json(self, relative: str) -> Any:
        return json.loads(self.path(relative).read_text(encoding="utf-8"))

    def write_text(self, relative: str, text: str) -> Path:
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def read_text(self, relative: str) -> str:
        return self.path(relative).read_text(encoding="utf-8")

    def save_upload(self, filename: str, data: bytes) -> dict[str, Any]:
        file_id = uuid4().hex
        name = safe_name(filename, "upload.bin")
        rel = f"uploads/{file_id}/{name}"
        path = self.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        meta = {"file_id": file_id, "filename": name, "size": len(data), "relative_path": rel}
        self.write_json(f"uploads/{file_id}/metadata.json", meta)
        return meta

    def get_upload(self, file_id: str) -> tuple[Path, dict[str, Any]]:
        meta = self.read_json(f"uploads/{safe_name(file_id)}/metadata.json")
        return self.path(meta["relative_path"]), meta

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import suffix_for

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def filename_for(source: str, pdf_url: str) -> str:
    stem = Path(unquote(urlparse(pdf_url).path)).stem
    stem = INVALID_FILENAME_CHARS.sub("-", stem).strip(" .") or "circular"
    return f"{stem}{suffix_for(source)}"


def find_hash(folder: Path, digest: str) -> Path | None:
    if not folder.is_dir():
        return None
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() != ".pdf":
            continue
        try:
            if sha256(path.read_bytes()) == digest:
                return path
        except OSError:
            continue
    return None


def _available_path(folder: Path, filename: str) -> Path:
    path = folder / filename
    if not path.exists():
        return path
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 2
    while True:
        candidate = folder / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def save_pdf(folder: Path, filename: str, data: bytes) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = _available_path(folder, filename)
    temp_path = folder / f".{path.name}.tmp"
    temp_path.write_bytes(data)
    os.replace(temp_path, path)
    return path

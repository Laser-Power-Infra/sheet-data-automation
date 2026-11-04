from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

State = dict[str, dict[str, Any]]


def load_state(path: Path) -> State:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        corrupt = path.with_name(f"{path.stem}.corrupt-{dt.datetime.now():%Y%m%d-%H%M%S}{path.suffix}")
        try:
            path.replace(corrupt)
        except OSError as move_exc:
            LOGGER.error("Could not move corrupt state file %s: %s", path, move_exc)
        else:
            LOGGER.error("Corrupt state file moved to %s: %s", corrupt, exc)
        return {}
    except OSError as exc:
        LOGGER.error("Could not read state file %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)

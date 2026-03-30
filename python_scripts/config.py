from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DOTENV_PATH = ROOT_DIR / '.env'


def load_dotenv(path: Path = DOTENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def hydrate_env(path: Path = DOTENV_PATH, *, overwrite: bool = False) -> dict[str, str]:
    values = load_dotenv(path)
    for key, value in values.items():
        if overwrite or key not in os.environ:
            os.environ[key] = value
    return values

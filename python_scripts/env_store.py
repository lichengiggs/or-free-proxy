from __future__ import annotations

from pathlib import Path


def upsert_env(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    updated = False
    out: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('#') or '=' not in line:
            out.append(line)
            continue

        current_key = line.split('=', 1)[0].strip()
        if current_key == key:
            out.append(f'{key}={value}')
            updated = True
        else:
            out.append(line)

    if not updated:
        out.append(f'{key}={value}')

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(out) + '\n', encoding='utf-8')

"""
config.txt reader / writer for car metadata.

File format (plain text, one key=value per line):
    color=Red
    plate=ABC-1234
    model=Toyota Corolla
    owner=John Doe

Each value is capped at MAX_LEN characters when written.
"""

from __future__ import annotations

from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.txt"

FIELDS = ("color", "plate", "model", "owner")
MAX_LEN = 25  # RF24 payload leaves 25 bytes per info field


def _defaults() -> dict[str, str]:
    return {
        "color": "Unknown",
        "plate": "UNKNOWN",
        "model": "Unknown",
        "owner": "Unknown",
    }


def read_config() -> dict[str, str]:
    """Read config.txt and return a dict with all four car metadata fields.

    Creates the file with defaults if it does not exist.
    """
    if not CONFIG_PATH.exists():
        cfg = _defaults()
        write_config(cfg)
        return cfg

    cfg = _defaults()
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            if key in FIELDS:
                cfg[key] = val.strip()[:MAX_LEN]

    return cfg


def write_config(cfg: dict[str, str]) -> None:
    """Write (or overwrite) config.txt with the given car metadata.

    Unknown keys are ignored; missing keys fall back to current file values.
    """
    current = read_config() if CONFIG_PATH.exists() else _defaults()
    current.update({k: str(v).strip()[:MAX_LEN] for k, v in cfg.items() if k in FIELDS})

    lines = [f"{field}={current[field]}" for field in FIELDS]
    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

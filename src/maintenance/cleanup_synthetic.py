"""Find and remove historical placeholder artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.config import Settings, get_settings

PLACEHOLDERS = (
    "NoVirtualMachines",
    "NoAksClusters",
    "NoUnattachedDisks",
)


def find_contaminated_files(settings: Settings) -> list[Path]:
    matches: list[Path] = []
    for root in (settings.raw_path, settings.processed_path):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if any(placeholder in text for placeholder in PLACEHOLDERS):
                matches.append(path)
    return sorted(matches)


def cleanup(settings: Settings, *, execute: bool = False) -> dict:
    files = find_contaminated_files(settings)
    removed: list[str] = []
    if execute:
        allowed_roots = (
            settings.raw_path.resolve(),
            settings.processed_path.resolve(),
        )
        for path in files:
            resolved = path.resolve()
            if not any(
                resolved == root or root in resolved.parents for root in allowed_roots
            ):
                raise RuntimeError(f"Refusing to remove file outside data roots: {path}")
            path.unlink()
            removed.append(str(path))
    return {
        "status": "completed" if execute else "dry_run",
        "placeholder_names": list(PLACEHOLDERS),
        "matched_count": len(files),
        "matched_files": [str(path) for path in files],
        "removed_files": removed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute", action="store_true", help="Delete contaminated artifacts"
    )
    args = parser.parse_args()
    print(json.dumps(cleanup(get_settings(), execute=args.execute), indent=2))


if __name__ == "__main__":
    main()

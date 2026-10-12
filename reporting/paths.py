"""Readable report locations anchored at the selected folder name."""
import os
from pathlib import Path


def display_path(path: str, root: str, folder_name: str | None = None) -> str:
    selected = Path(root)
    folder = selected.parent if selected.is_file() else selected
    relative = os.path.relpath(path, folder)
    label = folder_name or folder.name
    return str(Path(label) / relative) if relative != '.' else label

import os
from pathlib import Path

def get_project_root() -> Path:
    """Returns the root directory of the reader_app."""
    # This file is in reader_app/src/utils/paths.py
    # Root is 3 levels up
    return Path(__file__).resolve().parent.parent.parent

def get_obsidian_vault_dir() -> Path:
    """Returns the path to the Obsidian Vault."""
    return Path("/Users/hugovaillaud/Documents/synced_vault")

def get_obsidian_books_dir() -> Path:
    """Returns the path to the books folder in the Obsidian Vault."""
    path = get_obsidian_vault_dir() / "books"
    ensure_dir_exists(path)
    return path

def ensure_dir_exists(path: Path) -> None:
    """Ensures that a directory exists."""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)


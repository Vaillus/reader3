
import os
import sys
from pathlib import Path

def get_project_root() -> Path:
    """Returns the root directory of the project."""
    # Assuming this file is in src/utilities/paths.py
    # Root is 2 levels up
    return Path(__file__).resolve().parent.parent.parent

def get_kobo_db_path() -> Path:
    """Returns the path to the KoboReader.sqlite database on macOS."""
    # Standard location for Kobo Desktop Edition on macOS
    return Path(os.path.expanduser("~/Library/Application Support/Kobo/Kobo Desktop Edition/KoboReader.sqlite"))

def get_outputs_dir() -> Path:
    """Returns the directory where output files are stored."""
    path = get_project_root() / "reader_app"
    ensure_dir_exists(path)
    return path

def ensure_dir_exists(path: Path) -> None:
    """Ensures that a directory exists."""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)


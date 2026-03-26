"""Portable path detection for ChordCut application."""

import sys
from pathlib import Path


def get_app_dir() -> Path:
    """Get the application's root directory.

    When running as a frozen executable (PyInstaller), returns the
    directory containing the executable. When running from source,
    returns the project root.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return Path(sys.executable).parent
    else:
        # Running from source: utils/ → chordcut/ → src/ → project root
        return Path(__file__).parent.parent.parent.parent


def get_data_dir() -> Path:
    """Get the data directory, creating it if needed.

    Returns the path to the data/ subfolder where chordcut.db and other
    persistent data are stored.
    """
    data_dir = get_app_dir() / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


def get_db_path() -> Path:
    """Get the full path to the SQLite database file."""
    return get_data_dir() / "chordcut.db"


def get_settings_path() -> Path:
    """Get the full path to the settings JSON file.

    Settings live in the application root (next to the executable
    or project root in dev mode), separate from the database.
    """
    return get_app_dir() / "settings.json"


def get_icon_path() -> Path | None:
    """Get the path to the application icon file.

    Returns *None* when no icon file is found.
    """
    # Frozen: icon sits next to the executable
    # Dev: icon sits in resources/ under the project root
    app = get_app_dir()
    candidates = [
        app / "chordcut.ico",
        # PyInstaller --onedir puts datas in _internal/
        app / "_internal" / "chordcut.ico",
        app / "resources" / "chordcut.ico",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def get_locale_dir() -> Path:
    """Get the locale directory containing translation files.

    When running as a frozen executable (PyInstaller), returns the
    locale/ subfolder inside _internal/. When running from source,
    returns the locale/ folder in the project root.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / "_internal" / "locale"
    return get_app_dir() / "locale"

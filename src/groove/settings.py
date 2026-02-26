"""Application settings manager for Groove.

Settings are stored in a JSON file next to the executable (or the
project root in dev mode), separate from the SQLite database that
holds server credentials and library cache.
"""

import json
from pathlib import Path

from groove.utils.paths import get_settings_path

_DEFAULTS: dict = {
    # Folder where downloaded tracks are saved.
    # None means get_app_dir() / "music" at runtime.
    "download_dir": None,
    # Volume adjustment step in percentage points (1–20).
    "volume_step": 5,
    # Seek step in seconds (1–60).
    "seek_step": 5,
    # Whether to restore volume on next launch.
    "remember_volume": True,
    # Whether to restore audio device on next launch.
    "remember_device": True,
    # Last-saved volume level (0–100); used when remember_volume is True.
    "volume": 80,
    # Last-saved MPV device string; used when remember_device is True.
    "device": "auto",
    # Track list sort order.
    "track_sort": "date_desc",
}


class Settings:
    """Persistent user settings backed by a JSON file.

    The file is loaded once on construction and saved explicitly by
    calling :meth:`save`.  Individual properties can be mutated in
    memory at any time; the file is not written until ``save()`` is
    called.
    """

    def __init__(self) -> None:
        self._path: Path = get_settings_path()
        self._data: dict = dict(_DEFAULTS)
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load settings from file, silently ignoring errors."""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                loaded = json.load(f)
            for key in _DEFAULTS:
                if key in loaded:
                    self._data[key] = loaded[key]
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    def save(self) -> None:
        """Persist current settings to disk."""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def download_dir(self) -> Path:
        """Folder where downloaded tracks are saved."""
        val = self._data.get("download_dir")
        if val:
            return Path(val)
        from groove.utils.paths import get_app_dir
        return get_app_dir() / "music"

    @download_dir.setter
    def download_dir(self, value: "Path | str") -> None:
        self._data["download_dir"] = str(value)

    @property
    def volume_step(self) -> int:
        """Volume adjustment step in percentage points."""
        return max(1, min(20, int(self._data.get("volume_step", 5))))

    @volume_step.setter
    def volume_step(self, value: int) -> None:
        self._data["volume_step"] = max(1, min(20, int(value)))

    @property
    def seek_step(self) -> int:
        """Seek adjustment step in seconds."""
        return max(1, min(60, int(self._data.get("seek_step", 5))))

    @seek_step.setter
    def seek_step(self, value: int) -> None:
        self._data["seek_step"] = max(1, min(60, int(value)))

    @property
    def remember_volume(self) -> bool:
        """Whether to restore volume level on next launch."""
        return bool(self._data.get("remember_volume", True))

    @remember_volume.setter
    def remember_volume(self, value: bool) -> None:
        self._data["remember_volume"] = bool(value)

    @property
    def remember_device(self) -> bool:
        """Whether to restore audio device on next launch."""
        return bool(self._data.get("remember_device", True))

    @remember_device.setter
    def remember_device(self, value: bool) -> None:
        self._data["remember_device"] = bool(value)

    @property
    def volume(self) -> int:
        """Last-saved volume level (0–100)."""
        return max(0, min(100, int(self._data.get("volume", 80))))

    @volume.setter
    def volume(self, value: int) -> None:
        self._data["volume"] = max(0, min(100, int(value)))

    @property
    def device(self) -> str:
        """Last-saved MPV audio device string."""
        return str(self._data.get("device", "auto"))

    @device.setter
    def device(self, value: str) -> None:
        self._data["device"] = str(value)

    _VALID_TRACK_SORTS = {
        "alpha_asc", "alpha_desc", "date_desc", "date_asc",
    }

    @property
    def track_sort(self) -> str:
        """Track list sort order."""
        val = self._data.get("track_sort", "date_desc")
        if val in self._VALID_TRACK_SORTS:
            return val
        return "date_desc"

    @track_sort.setter
    def track_sort(self, value: str) -> None:
        if value in self._VALID_TRACK_SORTS:
            self._data["track_sort"] = value

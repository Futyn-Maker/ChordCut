"""Auto-update support for ChordCut via GitHub Releases."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from chordcut import __repo__, __version__
from chordcut.utils.paths import get_app_dir

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


@dataclass
class UpdateInfo:
    """Information about an available update."""

    current_version: str
    new_version: str
    changelog: str
    download_url: str
    asset_size: int


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple.

    Handles formats like ``"2026.03.13"`` and ``"v2026.03.13.1"``.
    """
    return tuple(int(p) for p in version_str.lstrip("v").split("."))


def check_for_update() -> UpdateInfo | None:
    """Check GitHub for a newer release.

    Returns an :class:`UpdateInfo` when a newer version exists, or
    *None* when the running version is already the latest.

    Raises :class:`urllib.error.URLError` or similar on network errors
    so the caller can decide whether to surface the problem.
    """
    url = f"{_GITHUB_API}/repos/{__repo__}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ChordCut-Updater",
        },
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())

    tag = data.get("tag_name", "")
    if not tag:
        return None

    remote_ver = tag.lstrip("v")
    if _parse_version(remote_ver) <= _parse_version(__version__):
        return None

    # Find the Windows ZIP asset.
    download_url = ""
    asset_size = 0
    for asset in data.get("assets", []):
        if asset["name"].endswith(".zip"):
            download_url = asset["browser_download_url"]
            asset_size = asset.get("size", 0)
            break

    if not download_url:
        return None

    return UpdateInfo(
        current_version=__version__,
        new_version=remote_ver,
        changelog=data.get("body", "") or "",
        download_url=download_url,
        asset_size=asset_size,
    )


def download_update(
    info: UpdateInfo,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[Path, Path]:
    """Download and extract the update ZIP.

    Returns ``(new_files_dir, temp_root)`` where *new_files_dir*
    contains the extracted application files and *temp_root* is the
    temporary directory that should be cleaned up after the update.

    *progress_callback* receives ``(bytes_downloaded, total_bytes)``
    and is called from the download thread.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="chordcut_update_"))
    zip_path = tmp_dir / "update.zip"

    try:
        req = urllib.request.Request(
            info.download_url,
            headers={"User-Agent": "ChordCut-Updater"},
        )

        with urllib.request.urlopen(req, timeout=300) as resp:
            total = (
                int(resp.headers.get("Content-Length", 0))
                or info.asset_size
            )
            downloaded = 0

            with open(zip_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        # Extract the ZIP.
        extract_dir = tmp_dir / "extracted"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

        zip_path.unlink()

        # The release ZIP wraps everything in a ChordCut/ subfolder.
        inner = extract_dir / "ChordCut"
        if inner.is_dir():
            return inner, tmp_dir

        # Fallback: single top-level directory.
        children = list(extract_dir.iterdir())
        if len(children) == 1 and children[0].is_dir():
            return children[0], tmp_dir

        return extract_dir, tmp_dir

    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def apply_update(update_dir: Path, temp_root: Path) -> None:
    """Replace current application files and restart.

    Writes a small batch script that waits for this process to
    terminate, copies the new files over the old ones (preserving
    ``data/``, ``settings.json`` and ``music/``), then launches the
    updated executable.

    Only works on Windows with a frozen (PyInstaller) build.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Cannot apply updates in development mode")

    app_dir = get_app_dir()
    pid = os.getpid()

    bat_path = Path(tempfile.gettempdir()) / "chordcut_update.bat"
    script = (
        "@echo off\r\n"
        "chcp 65001 >nul 2>&1\r\n"
        "\r\n"
        ":: Wait for the running instance to exit\r\n"
        ":wait_loop\r\n"
        "timeout /t 1 /nobreak >nul\r\n"
        f'tasklist /FO CSV /fi "PID eq {pid}" 2>nul | findstr "{pid}" >nul\r\n'
        "if not errorlevel 1 goto wait_loop\r\n"
        "\r\n"
        ":: Remove directories that must be fully replaced\r\n"
        f'cd /d "{app_dir}"\r\n'
        'if exist "_internal" rmdir /S /Q "_internal"\r\n'
        "\r\n"
        ":: Copy new files (data/, settings.json, music/ are not in\r\n"
        ":: the ZIP so they are preserved automatically)\r\n"
        f'xcopy /E /Y /I "{update_dir}\\*" "{app_dir}\\" >nul\r\n'
        "\r\n"
        ":: Launch the updated application\r\n"
        f'start "" "{app_dir}\\ChordCut.exe"\r\n'
        "\r\n"
        ":: Clean up\r\n"
        f'rmdir /S /Q "{temp_root}"\r\n'
        "\r\n"
        ":: Self-delete\r\n"
        '(goto) 2>nul & del "%~f0"\r\n'
    )

    bat_path.write_text(script, encoding="utf-8")

    logger.info("Launching update script: %s", bat_path)
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat_path)],
        creationflags=0x08000000,  # CREATE_NO_WINDOW
        close_fds=True,
    )

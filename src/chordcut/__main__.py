"""Entry point for running ChordCut as a module."""

import os
import sys
from pathlib import Path


def _setup_dev_environment() -> None:
    """Set up paths needed when running from source (not frozen)."""
    if getattr(sys, "frozen", False):
        return
    # Project root: __main__.py → chordcut/ → src/ → project root
    project_root = Path(__file__).parent.parent.parent
    # Add libmpv DLL directory to PATH so `import mpv` can find it.
    mpv_dir = project_root / "resources" / "libmpv"
    if mpv_dir.is_dir():
        os.environ["PATH"] = str(mpv_dir) + os.pathsep + os.environ.get("PATH", "")


_setup_dev_environment()

from chordcut.app import run  # noqa: E402


def main() -> None:
    """Main entry point."""
    run()


if __name__ == "__main__":
    main()

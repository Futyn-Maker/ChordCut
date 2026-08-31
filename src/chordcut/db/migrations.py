"""Schema migrations for the ChordCut database.

Each migration is a function that receives a ``sqlite3.Connection``
and upgrades the schema from the previous version.  Migrations must
be **defensive** — safe to run on both existing databases (where the
change is needed) and fresh databases (where ``SCHEMA`` already
includes the change).

To add a migration:

1. Write a function ``_migrate_to_N(conn)`` that performs the change.
2. Append ``(N, _migrate_to_N)`` to :data:`MIGRATIONS`.
3. Set :data:`SCHEMA_VERSION` to ``N``.
4. Update ``SCHEMA`` in ``models.py`` so fresh installs get the
   final state directly.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

# Increment when the schema changes and add a migration below.
SCHEMA_VERSION = 2

# Ordered list of (target_version, migration_callable).
MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = []


def _migrate_to_2(conn: sqlite3.Connection) -> None:
    """Add cover art image tag columns to tracks and albums."""
    track_cols = {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}
    if "primary_image_tag" not in track_cols:
        conn.execute("ALTER TABLE tracks ADD COLUMN primary_image_tag TEXT")
    if "album_primary_image_tag" not in track_cols:
        conn.execute("ALTER TABLE tracks ADD COLUMN album_primary_image_tag TEXT")
    album_cols = {row[1] for row in conn.execute("PRAGMA table_info(albums)")}
    if "primary_image_tag" not in album_cols:
        conn.execute("ALTER TABLE albums ADD COLUMN primary_image_tag TEXT")


MIGRATIONS.append((2, _migrate_to_2))

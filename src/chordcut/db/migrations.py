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
from typing import Callable

# Increment when the schema changes and add a migration below.
SCHEMA_VERSION = 1

# Ordered list of (target_version, migration_callable).
MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = []


# -- Example (uncomment and adapt when you need migration 2) ----------
#
# def _migrate_to_2(conn: sqlite3.Connection) -> None:
#     cols = {row[1] for row in conn.execute(
#         "PRAGMA table_info(tracks)",
#     )}
#     if "genre" not in cols:
#         conn.execute(
#             "ALTER TABLE tracks ADD COLUMN genre TEXT",
#         )
#
# SCHEMA_VERSION = 2
# MIGRATIONS.append((2, _migrate_to_2))

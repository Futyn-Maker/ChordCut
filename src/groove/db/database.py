"""SQLite database manager for Groove."""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from groove.utils.paths import get_db_path


@dataclass
class ServerCredentials:
    """Stored server connection credentials."""

    id: int | None
    url: str
    user_id: str
    username: str
    access_token: str
    device_id: str


SCHEMA = """
-- Server credentials
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    access_token TEXT NOT NULL,
    device_id TEXT NOT NULL
);

-- Music libraries
CREATE TABLE IF NOT EXISTS libraries (
    id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    -- Total tracks the server reported for this library the last
    -- time a full load completed.  0 means "never finished loading".
    expected_track_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Cached tracks
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    album_name TEXT,
    artist_name TEXT,
    artist_display TEXT,
    album_id TEXT,
    artist_id TEXT,
    duration_ticks INTEGER,
    track_number INTEGER,
    library_id TEXT,
    date_created TEXT,
    PRIMARY KEY (id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tracks_name ON tracks(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_server ON tracks(server_id);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_library ON tracks(library_id);
CREATE INDEX IF NOT EXISTS idx_tracks_date ON tracks(date_created);

-- Artists (from track ArtistItems)
CREATE TABLE IF NOT EXISTS artists (
    id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Album artists (from track AlbumArtists)
CREATE TABLE IF NOT EXISTS album_artists (
    id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Albums
CREATE TABLE IF NOT EXISTS albums (
    id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    artist_display TEXT,
    library_id TEXT,
    PRIMARY KEY (id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_albums_server ON albums(server_id);
CREATE INDEX IF NOT EXISTS idx_albums_library ON albums(library_id);

-- Track-to-artist mapping (many-to-many)
CREATE TABLE IF NOT EXISTS track_artists (
    track_id TEXT NOT NULL,
    artist_id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    PRIMARY KEY (track_id, artist_id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Album-to-album_artist mapping
CREATE TABLE IF NOT EXISTS album_album_artists (
    album_id TEXT NOT NULL,
    album_artist_id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    PRIMARY KEY (album_id, album_artist_id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Playlists
CREATE TABLE IF NOT EXISTS playlists (
    id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Playlist tracks
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id TEXT NOT NULL,
    track_id TEXT NOT NULL,
    playlist_item_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    server_id INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, playlist_item_id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Playback positions (for audiobooks, future use)
CREATE TABLE IF NOT EXISTS playback_positions (
    item_id TEXT PRIMARY KEY,
    position_ticks INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """SQLite database manager with connection pooling."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_db_path()
        self._init_schema()

    def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection as a context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- Server credentials ---

    def save_server(self, creds: ServerCredentials) -> int:
        """Save or update server credentials.

        When *creds.id* is set, that row is updated directly.
        Otherwise we look for an existing row with the same
        ``url`` + ``user_id`` and update it (reusing the old
        ``server_id`` so that cached data stays valid).  A new
        row is only inserted if no match exists.
        """
        with self.connection() as conn:
            if creds.id is not None:
                conn.execute(
                    """
                    UPDATE servers SET
                        url = ?, user_id = ?, username = ?,
                        access_token = ?, device_id = ?
                    WHERE id = ?
                    """,
                    (
                        creds.url,
                        creds.user_id,
                        creds.username,
                        creds.access_token,
                        creds.device_id,
                        creds.id,
                    ),
                )
                return creds.id

            # Check for an existing row (same server + user)
            existing = conn.execute(
                "SELECT id FROM servers"
                " WHERE url = ? AND user_id = ?",
                (creds.url, creds.user_id),
            ).fetchone()

            if existing:
                # Reuse existing server_id — keeps
                # cached tracks, playlists, etc.
                conn.execute(
                    """
                    UPDATE servers SET
                        username = ?,
                        access_token = ?,
                        device_id = ?
                    WHERE id = ?
                    """,
                    (
                        creds.username,
                        creds.access_token,
                        creds.device_id,
                        existing["id"],
                    ),
                )
                return existing["id"]

            cursor = conn.execute(
                """
                INSERT INTO servers
                    (url, user_id, username,
                     access_token, device_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    creds.url,
                    creds.user_id,
                    creds.username,
                    creds.access_token,
                    creds.device_id,
                ),
            )
            return cursor.lastrowid or 0

    def get_server(self, server_id: int) -> ServerCredentials | None:
        """Get server credentials by ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM servers WHERE id = ?",
                (server_id,),
            ).fetchone()
            if row:
                return self._row_to_creds(row)
            return None

    def get_all_servers(self) -> list[ServerCredentials]:
        """Get all saved server credentials ordered by id."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM servers ORDER BY id"
            ).fetchall()
            return [self._row_to_creds(r) for r in rows]

    @staticmethod
    def _row_to_creds(row: sqlite3.Row) -> ServerCredentials:
        return ServerCredentials(
            id=row["id"],
            url=row["url"],
            user_id=row["user_id"],
            username=row["username"],
            access_token=row["access_token"],
            device_id=row["device_id"],
        )

    def delete_server(self, server_id: int) -> None:
        """Delete a server and its cached data."""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM servers WHERE id = ?", (server_id,)
            )

    # --- Library caching ---

    def cache_libraries(
        self, server_id: int, libraries: list[dict],
    ) -> None:
        """Cache the list of music libraries for a server.

        Existing ``enabled`` states and ``expected_track_count``
        values are preserved; newly discovered libraries default to
        enabled=1 and expected_track_count=0.
        """
        with self.connection() as conn:
            # Remember per-library user settings.
            rows = conn.execute(
                "SELECT id, enabled, expected_track_count"
                " FROM libraries WHERE server_id = ?",
                (server_id,),
            ).fetchall()
            enabled_states = {
                r["id"]: r["enabled"] for r in rows
            }
            expected_counts = {
                r["id"]: r["expected_track_count"]
                for r in rows
            }

            conn.execute(
                "DELETE FROM libraries WHERE server_id = ?",
                (server_id,),
            )
            conn.executemany(
                "INSERT INTO libraries"
                " (id, server_id, name, enabled,"
                "  expected_track_count)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        lib["Id"],
                        server_id,
                        lib.get("Name", ""),
                        enabled_states.get(lib["Id"], 1),
                        expected_counts.get(lib["Id"], 0),
                    )
                    for lib in libraries
                    if lib.get("Id")
                ],
            )

    def get_libraries(self, server_id: int) -> list[dict]:
        """Get cached music libraries for a server.

        Returns dicts with ``Id``, ``Name``, ``Enabled``, and
        ``ExpectedTrackCount`` keys.
        """
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM libraries
                WHERE server_id = ?
                ORDER BY name COLLATE NOCASE
                """,
                (server_id,),
            ).fetchall()
            return [
                {
                    "Id": r["id"],
                    "Name": r["name"],
                    "Enabled": bool(r["enabled"]),
                    "ExpectedTrackCount": (
                        r["expected_track_count"]
                    ),
                }
                for r in rows
            ]

    def set_libraries_expected_counts(
        self,
        server_id: int,
        counts: dict[str, int],
    ) -> None:
        """Persist per-library expected track counts.

        ``counts`` maps library ID to the total number of tracks
        the server reported for that library.  Only the listed
        libraries are updated; others are left unchanged.
        """
        with self.connection() as conn:
            for lib_id, count in counts.items():
                conn.execute(
                    "UPDATE libraries"
                    " SET expected_track_count = ?"
                    " WHERE server_id = ? AND id = ?",
                    (count, server_id, lib_id),
                )

    def set_library_enabled(
        self,
        server_id: int,
        library_id: str,
        enabled: bool,
    ) -> None:
        """Persist the enabled state of a music library."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE libraries SET enabled = ?"
                " WHERE server_id = ? AND id = ?",
                (int(enabled), server_id, library_id),
            )

    def count_tracks(self, server_id: int) -> int:
        """Count all cached tracks for a server (unfiltered)."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM tracks"
                " WHERE server_id = ?",
                (server_id,),
            ).fetchone()
            return row[0]

    def clear_library_cache(
        self, server_id: int,
    ) -> None:
        """Delete all library cache data for a server.

        Clears tracks, artists, album_artists, albums,
        and all mapping tables.  Does NOT touch libraries
        or playlists.
        """
        with self.connection() as conn:
            for table in (
                "track_artists", "album_album_artists",
                "tracks", "artists",
                "album_artists", "albums",
            ):
                conn.execute(
                    f"DELETE FROM {table}"
                    f" WHERE server_id = ?",
                    (server_id,),
                )

    @staticmethod
    def _insert_library_data(
        conn: sqlite3.Connection,
        server_id: int,
        tracks: list[dict],
    ) -> None:
        """Insert tracks and extracted entities into DB.

        Extracts artists, album_artists, albums, and all
        mapping tables from the tracks list and bulk-inserts.
        Uses INSERT OR REPLACE for tracks and INSERT OR
        IGNORE for everything else (safe for cross-batch
        duplicates).
        """
        artists_seen: dict[str, str] = {}
        album_artists_seen: dict[str, str] = {}
        albums_seen: dict[str, tuple[str, str, str]] = {}
        track_artist_links: list[tuple[str, str]] = []
        album_aa_links: set[tuple[str, str]] = set()
        track_rows: list[tuple] = []

        for track in tracks:
            track_id = track.get("Id")
            if not track_id:
                continue

            library_id = track.get("LibraryId", "")

            # All artist names for display
            artists_list = track.get("Artists", [])
            artist_items = track.get("ArtistItems", [])
            artist_display = (
                ", ".join(artists_list) if artists_list
                else track.get("AlbumArtist", "")
            )

            # First artist for backward compat
            artist_name = track.get("AlbumArtist") or (
                artists_list[0] if artists_list else ""
            )
            first_artist_id = (
                artist_items[0].get("Id")
                if artist_items else None
            )

            # Collect unique artists
            for ai in artist_items:
                aid = ai.get("Id")
                if aid:
                    artists_seen.setdefault(
                        aid, ai.get("Name", ""),
                    )
                    track_artist_links.append(
                        (track_id, aid),
                    )

            # Collect unique album artists
            album_artists_items = track.get(
                "AlbumArtists", [],
            )
            for aai in album_artists_items:
                aaid = aai.get("Id")
                if aaid:
                    album_artists_seen.setdefault(
                        aaid, aai.get("Name", ""),
                    )

            # Collect unique albums and link to album artists
            album_id = track.get("AlbumId")
            if album_id and album_id not in albums_seen:
                albums_seen[album_id] = (
                    track.get("Album", ""),
                    track.get("AlbumArtist", ""),
                    library_id,
                )
                for aai in album_artists_items:
                    aaid = aai.get("Id")
                    if aaid:
                        album_aa_links.add(
                            (album_id, aaid),
                        )

            # Collect track row for bulk insert
            track_rows.append((
                track_id,
                server_id,
                track.get("Name", "Unknown"),
                track.get("Album", ""),
                artist_name,
                artist_display,
                album_id,
                first_artist_id,
                track.get("RunTimeTicks"),
                track.get("IndexNumber"),
                library_id,
                track.get("DateCreated"),
            ))

        # Bulk insert tracks
        conn.executemany(
            "INSERT OR REPLACE INTO tracks ("
            "  id, server_id, name, album_name,"
            "  artist_name, artist_display,"
            "  album_id, artist_id,"
            "  duration_ticks, track_number,"
            "  library_id, date_created"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            track_rows,
        )

        # Bulk insert artists
        conn.executemany(
            "INSERT OR IGNORE INTO artists"
            " (id, server_id, name) VALUES (?, ?, ?)",
            [
                (aid, server_id, name)
                for aid, name in artists_seen.items()
            ],
        )

        # Bulk insert album artists
        conn.executemany(
            "INSERT OR IGNORE INTO album_artists"
            " (id, server_id, name) VALUES (?, ?, ?)",
            [
                (aaid, server_id, name)
                for aaid, name
                in album_artists_seen.items()
            ],
        )

        # Bulk insert albums
        conn.executemany(
            "INSERT OR IGNORE INTO albums"
            " (id, server_id, name, artist_display,"
            " library_id)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (aid, server_id, aname, adisplay, lib_id)
                for aid, (aname, adisplay, lib_id)
                in albums_seen.items()
            ],
        )

        # Bulk insert track-artist links
        conn.executemany(
            "INSERT OR IGNORE INTO track_artists"
            " (track_id, artist_id, server_id)"
            " VALUES (?, ?, ?)",
            [
                (tid, aid, server_id)
                for tid, aid in track_artist_links
            ],
        )

        # Bulk insert album-album_artist links
        conn.executemany(
            "INSERT OR IGNORE INTO album_album_artists"
            " (album_id, album_artist_id, server_id)"
            " VALUES (?, ?, ?)",
            [
                (aid, aaid, server_id)
                for aid, aaid in album_aa_links
            ],
        )

    def cache_library(
        self, server_id: int, tracks: list[dict],
    ) -> None:
        """Cache the full library (clear + insert).

        Populates tracks, artists, album_artists, albums,
        and all mapping tables from a tracks API response.
        Clears existing data first (single transaction).
        """
        with self.connection() as conn:
            for table in (
                "track_artists", "album_album_artists",
                "tracks", "artists",
                "album_artists", "albums",
            ):
                conn.execute(
                    f"DELETE FROM {table}"
                    f" WHERE server_id = ?",
                    (server_id,),
                )
            self._insert_library_data(
                conn, server_id, tracks,
            )

    def cache_library_batch(
        self, server_id: int, tracks: list[dict],
    ) -> None:
        """Insert a batch of tracks (no clear).

        Used during progressive loading to add tracks
        incrementally without deleting existing data.
        """
        with self.connection() as conn:
            self._insert_library_data(
                conn, server_id, tracks,
            )

    def cache_playlists(
        self,
        server_id: int,
        playlists: list[dict],
        playlist_tracks: dict[str, list[dict]],
    ) -> None:
        """Cache playlists and their track listings."""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM playlist_tracks"
                " WHERE server_id = ?",
                (server_id,),
            )
            conn.execute(
                "DELETE FROM playlists WHERE server_id = ?",
                (server_id,),
            )

            for pl in playlists:
                pl_id = pl.get("Id")
                if not pl_id:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO playlists"
                    " (id, server_id, name)"
                    " VALUES (?, ?, ?)",
                    (pl_id, server_id, pl.get("Name", "")),
                )

                items = playlist_tracks.get(pl_id, [])
                conn.executemany(
                    "INSERT OR IGNORE INTO playlist_tracks"
                    " (playlist_id, track_id,"
                    " playlist_item_id, position,"
                    " server_id)"
                    " VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            pl_id, item.get("Id"),
                            item.get(
                                "PlaylistItemId",
                                item.get("Id"),
                            ),
                            i, server_id,
                        )
                        for i, item in enumerate(items)
                        if item.get("Id")
                    ],
                )

    # --- Row converters ---

    @staticmethod
    def _track_to_dict(row: sqlite3.Row) -> dict:
        """Convert a track DB row to a Jellyfin-API-compatible dict."""
        return {
            "Id": row["id"],
            "Name": row["name"],
            "Album": row["album_name"] or "",
            "AlbumArtist": row["artist_name"] or "",
            "ArtistDisplay": (
                row["artist_display"]
                or row["artist_name"] or ""
            ),
            "AlbumId": row["album_id"],
            "RunTimeTicks": row["duration_ticks"],
            "IndexNumber": row["track_number"],
            "LibraryId": row["library_id"] or "",
            "DateCreated": row["date_created"] or "",
        }

    @staticmethod
    def _artist_to_dict(row: sqlite3.Row) -> dict:
        return {"Id": row["id"], "Name": row["name"]}

    @staticmethod
    def _album_to_dict(row: sqlite3.Row) -> dict:
        return {
            "Id": row["id"],
            "Name": row["name"],
            "ArtistDisplay": row["artist_display"] or "",
            "LibraryId": row["library_id"] or "",
        }

    @staticmethod
    def _playlist_to_dict(row: sqlite3.Row) -> dict:
        return {"Id": row["id"], "Name": row["name"]}

    # --- Query helpers ---

    @staticmethod
    def _lib_filter(
        library_ids: set[str] | None,
        column: str = "library_id",
    ) -> tuple[str, tuple]:
        """Build a SQL fragment for library filtering.

        Returns (sql_fragment, params) where sql_fragment is
        either empty or " AND column IN (?, ?, ...)".
        """
        if library_ids is None:
            return "", ()
        if not library_ids:
            # Empty set: nothing matches
            return " AND 0", ()
        ph = ",".join("?" * len(library_ids))
        return (
            f" AND {column} IN ({ph})",
            tuple(library_ids),
        )

    # --- Query methods ---

    _TRACK_SORT_SQL: dict[str, str] = {
        "alpha_asc": (
            "artist_name COLLATE NOCASE,"
            " album_name COLLATE NOCASE,"
            " track_number"
        ),
        "alpha_desc": (
            "artist_name COLLATE NOCASE DESC,"
            " album_name COLLATE NOCASE DESC,"
            " track_number DESC"
        ),
        "date_desc": (
            "date_created DESC,"
            " name COLLATE NOCASE"
        ),
        "date_asc": (
            "date_created ASC,"
            " name COLLATE NOCASE"
        ),
    }

    def get_all_tracks(
        self,
        server_id: int,
        library_ids: set[str] | None = None,
        sort: str = "alpha_asc",
    ) -> list[dict]:
        """Get all cached tracks for a server."""
        lib_sql, lib_params = self._lib_filter(library_ids)
        order = self._TRACK_SORT_SQL.get(
            sort, self._TRACK_SORT_SQL["alpha_asc"],
        )
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM tracks
                WHERE server_id = ?{lib_sql}
                ORDER BY {order}
                """,
                (server_id, *lib_params),
            ).fetchall()
            return [self._track_to_dict(r) for r in rows]

    def get_all_artists(
        self,
        server_id: int,
        library_ids: set[str] | None = None,
    ) -> list[dict]:
        """Get all cached artists sorted by name."""
        if library_ids is not None:
            lib_sql, lib_params = self._lib_filter(
                library_ids, "t.library_id",
            )
            with self.connection() as conn:
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT a.* FROM artists a
                    JOIN track_artists ta
                        ON ta.artist_id = a.id
                        AND ta.server_id = a.server_id
                    JOIN tracks t
                        ON t.id = ta.track_id
                        AND t.server_id = ta.server_id
                    WHERE a.server_id = ?{lib_sql}
                    ORDER BY a.name COLLATE NOCASE
                    """,
                    (server_id, *lib_params),
                ).fetchall()
                return [self._artist_to_dict(r) for r in rows]

        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM artists
                WHERE server_id = ?
                ORDER BY name COLLATE NOCASE
                """,
                (server_id,),
            ).fetchall()
            return [self._artist_to_dict(r) for r in rows]

    def get_all_album_artists(
        self,
        server_id: int,
        library_ids: set[str] | None = None,
    ) -> list[dict]:
        """Get all cached album artists sorted by name."""
        if library_ids is not None:
            lib_sql, lib_params = self._lib_filter(
                library_ids, "al.library_id",
            )
            with self.connection() as conn:
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT aa.* FROM album_artists aa
                    JOIN album_album_artists aaa
                        ON aaa.album_artist_id = aa.id
                        AND aaa.server_id = aa.server_id
                    JOIN albums al
                        ON al.id = aaa.album_id
                        AND al.server_id = aaa.server_id
                    WHERE aa.server_id = ?{lib_sql}
                    ORDER BY aa.name COLLATE NOCASE
                    """,
                    (server_id, *lib_params),
                ).fetchall()
                return [self._artist_to_dict(r) for r in rows]

        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM album_artists
                WHERE server_id = ?
                ORDER BY name COLLATE NOCASE
                """,
                (server_id,),
            ).fetchall()
            return [self._artist_to_dict(r) for r in rows]

    def get_all_albums(
        self,
        server_id: int,
        library_ids: set[str] | None = None,
    ) -> list[dict]:
        """Get all cached albums sorted by artist then name."""
        lib_sql, lib_params = self._lib_filter(library_ids)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM albums
                WHERE server_id = ?{lib_sql}
                ORDER BY artist_display COLLATE NOCASE,
                         name COLLATE NOCASE
                """,
                (server_id, *lib_params),
            ).fetchall()
            return [self._album_to_dict(r) for r in rows]

    def get_all_playlists(self, server_id: int) -> list[dict]:
        """Get all cached playlists sorted by name."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM playlists
                WHERE server_id = ?
                ORDER BY name COLLATE NOCASE
                """,
                (server_id,),
            ).fetchall()
            return [self._playlist_to_dict(r) for r in rows]

    def get_albums_by_artist(
        self,
        server_id: int,
        artist_id: str,
        library_ids: set[str] | None = None,
    ) -> list[dict]:
        """Get albums that contain tracks by the given artist."""
        lib_sql, lib_params = self._lib_filter(
            library_ids, "a.library_id",
        )
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT a.* FROM albums a
                JOIN tracks t ON t.album_id = a.id
                    AND t.server_id = a.server_id
                JOIN track_artists ta ON ta.track_id = t.id
                    AND ta.server_id = t.server_id
                WHERE ta.artist_id = ?
                    AND a.server_id = ?{lib_sql}
                ORDER BY a.artist_display COLLATE NOCASE,
                         a.name COLLATE NOCASE
                """,
                (artist_id, server_id, *lib_params),
            ).fetchall()
            return [self._album_to_dict(r) for r in rows]

    def get_albums_by_album_artist(
        self,
        server_id: int,
        album_artist_id: str,
        library_ids: set[str] | None = None,
    ) -> list[dict]:
        """Get albums by the given album artist."""
        lib_sql, lib_params = self._lib_filter(
            library_ids, "a.library_id",
        )
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT a.* FROM albums a
                JOIN album_album_artists aaa
                    ON aaa.album_id = a.id
                    AND aaa.server_id = a.server_id
                WHERE aaa.album_artist_id = ?
                    AND a.server_id = ?{lib_sql}
                ORDER BY a.artist_display COLLATE NOCASE,
                         a.name COLLATE NOCASE
                """,
                (album_artist_id, server_id, *lib_params),
            ).fetchall()
            return [self._album_to_dict(r) for r in rows]

    def get_tracks_by_album(
        self,
        server_id: int,
        album_id: str,
        library_ids: set[str] | None = None,
    ) -> list[dict]:
        """Get tracks in the given album, ordered by track number."""
        lib_sql, lib_params = self._lib_filter(library_ids)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM tracks
                WHERE server_id = ?
                    AND album_id = ?{lib_sql}
                ORDER BY track_number, name COLLATE NOCASE
                """,
                (server_id, album_id, *lib_params),
            ).fetchall()
            return [self._track_to_dict(r) for r in rows]

    def get_playlist_tracks(
        self, server_id: int, playlist_id: str,
    ) -> list[dict]:
        """Get tracks in the given playlist, ordered by position."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT t.*, pt.playlist_item_id
                FROM tracks t
                JOIN playlist_tracks pt
                    ON pt.track_id = t.id
                    AND pt.server_id = t.server_id
                WHERE pt.playlist_id = ?
                    AND t.server_id = ?
                ORDER BY pt.position
                """,
                (playlist_id, server_id),
            ).fetchall()
            result = []
            for r in rows:
                d = self._track_to_dict(r)
                d["PlaylistItemId"] = (
                    r["playlist_item_id"]
                )
                result.append(d)
            return result

    def search_tracks(self, server_id: int, query: str) -> list[dict]:
        """Search cached tracks by name."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tracks
                WHERE server_id = ? AND name LIKE ?
                ORDER BY name COLLATE NOCASE
                LIMIT 500
                """,
                (server_id, f"%{query}%"),
            ).fetchall()
            return [self._track_to_dict(r) for r in rows]

    # --- Stats for properties ---

    def get_artist_stats(
        self,
        server_id: int,
        artist_id: str,
        artist_type: str = "artists",
        library_ids: set[str] | None = None,
    ) -> dict:
        """Get album and track counts for an artist.

        Returns ``{album_count, track_count}``.
        """
        a_lib_sql, a_lib_params = self._lib_filter(
            library_ids, "a.library_id",
        )
        t_lib_sql, t_lib_params = self._lib_filter(
            library_ids, "t.library_id",
        )
        with self.connection() as conn:
            if artist_type == "album_artists":
                album_count = conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT a.id)
                    FROM albums a
                    JOIN album_album_artists aaa
                        ON aaa.album_id = a.id
                        AND aaa.server_id = a.server_id
                    WHERE a.server_id = ?
                        AND aaa.album_artist_id = ?
                        {a_lib_sql}
                    """,
                    (
                        server_id, artist_id,
                        *a_lib_params,
                    ),
                ).fetchone()[0]
                track_count = conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT t.id)
                    FROM tracks t
                    JOIN albums al
                        ON al.id = t.album_id
                        AND al.server_id = t.server_id
                    JOIN album_album_artists aaa
                        ON aaa.album_id = al.id
                        AND aaa.server_id = al.server_id
                    WHERE t.server_id = ?
                        AND aaa.album_artist_id = ?
                        {t_lib_sql}
                    """,
                    (
                        server_id, artist_id,
                        *t_lib_params,
                    ),
                ).fetchone()[0]
            else:
                album_count = conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT t.album_id)
                    FROM tracks t
                    JOIN track_artists ta
                        ON ta.track_id = t.id
                        AND ta.server_id = t.server_id
                    WHERE t.server_id = ?
                        AND ta.artist_id = ?
                        {t_lib_sql}
                    """,
                    (
                        server_id, artist_id,
                        *t_lib_params,
                    ),
                ).fetchone()[0]
                track_count = conn.execute(
                    f"""
                    SELECT COUNT(t.id) FROM tracks t
                    JOIN track_artists ta
                        ON ta.track_id = t.id
                        AND ta.server_id = t.server_id
                    WHERE t.server_id = ?
                        AND ta.artist_id = ?
                        {t_lib_sql}
                    """,
                    (
                        server_id, artist_id,
                        *t_lib_params,
                    ),
                ).fetchone()[0]

            return {
                "album_count": album_count,
                "track_count": track_count,
            }

    def get_album_stats(
        self,
        server_id: int,
        album_id: str,
        library_ids: set[str] | None = None,
    ) -> dict:
        """Get track count and total duration for an album.

        Returns ``{track_count, total_duration_ticks}``.
        """
        lib_sql, lib_params = self._lib_filter(library_ids)
        with self.connection() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(id),
                       COALESCE(SUM(duration_ticks), 0)
                FROM tracks
                WHERE server_id = ?
                    AND album_id = ?{lib_sql}
                """,
                (server_id, album_id, *lib_params),
            ).fetchone()
            return {
                "track_count": row[0],
                "total_duration_ticks": row[1],
            }

    def get_playlist_stats(
        self, server_id: int, playlist_id: str,
    ) -> dict:
        """Get track count and total duration for a playlist.

        Returns ``{track_count, total_duration_ticks}``.
        """
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(t.id),
                       COALESCE(SUM(t.duration_ticks), 0)
                FROM tracks t
                JOIN playlist_tracks pt
                    ON pt.track_id = t.id
                    AND pt.server_id = t.server_id
                WHERE pt.playlist_id = ?
                    AND t.server_id = ?
                """,
                (playlist_id, server_id),
            ).fetchone()
            return {
                "track_count": row[0],
                "total_duration_ticks": row[1],
            }

    # --- Playlist mutations ---

    # --- Playlist CRUD ---

    def create_playlist(
        self,
        server_id: int,
        playlist_id: str,
        name: str,
    ) -> None:
        """Insert a new playlist into the cache."""
        with self.connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO playlists"
                " (id, server_id, name)"
                " VALUES (?, ?, ?)",
                (playlist_id, server_id, name),
            )

    def rename_playlist(
        self,
        server_id: int,
        playlist_id: str,
        new_name: str,
    ) -> None:
        """Rename a cached playlist."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE playlists SET name = ?"
                " WHERE id = ? AND server_id = ?",
                (new_name, playlist_id, server_id),
            )

    def delete_playlist(
        self,
        server_id: int,
        playlist_id: str,
    ) -> None:
        """Delete a playlist and its track associations."""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM playlist_tracks"
                " WHERE playlist_id = ?"
                " AND server_id = ?",
                (playlist_id, server_id),
            )
            conn.execute(
                "DELETE FROM playlists"
                " WHERE id = ? AND server_id = ?",
                (playlist_id, server_id),
            )

    # --- Playlist item mutations ---

    def get_playlist_track_ids(
        self, server_id: int, playlist_id: str,
    ) -> set[str]:
        """Get track IDs present in a playlist."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT track_id FROM playlist_tracks"
                " WHERE playlist_id = ?"
                " AND server_id = ?",
                (playlist_id, server_id),
            ).fetchall()
            return {r["track_id"] for r in rows}

    def add_playlist_track(
        self,
        server_id: int,
        playlist_id: str,
        track_id: str,
        playlist_item_id: str,
    ) -> None:
        """Insert a track at position 0, shifting others."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE playlist_tracks"
                " SET position = position + 1"
                " WHERE playlist_id = ?"
                " AND server_id = ?",
                (playlist_id, server_id),
            )
            conn.execute(
                "INSERT OR IGNORE INTO playlist_tracks"
                " (playlist_id, track_id,"
                " playlist_item_id, position,"
                " server_id)"
                " VALUES (?, ?, ?, 0, ?)",
                (
                    playlist_id, track_id,
                    playlist_item_id, server_id,
                ),
            )

    def remove_playlist_track(
        self,
        server_id: int,
        playlist_id: str,
        playlist_item_id: str,
    ) -> None:
        """Remove a track and recompact positions."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT position FROM playlist_tracks"
                " WHERE playlist_id = ?"
                " AND playlist_item_id = ?"
                " AND server_id = ?",
                (
                    playlist_id, playlist_item_id,
                    server_id,
                ),
            ).fetchone()
            if not row:
                return
            pos = row["position"]
            conn.execute(
                "DELETE FROM playlist_tracks"
                " WHERE playlist_id = ?"
                " AND playlist_item_id = ?"
                " AND server_id = ?",
                (
                    playlist_id, playlist_item_id,
                    server_id,
                ),
            )
            conn.execute(
                "UPDATE playlist_tracks"
                " SET position = position - 1"
                " WHERE playlist_id = ?"
                " AND server_id = ?"
                " AND position > ?",
                (playlist_id, server_id, pos),
            )

    def move_playlist_track(
        self,
        server_id: int,
        playlist_id: str,
        playlist_item_id: str,
        old_index: int,
        new_index: int,
    ) -> None:
        """Move a track from old_index to new_index."""
        if old_index == new_index:
            return
        with self.connection() as conn:
            if old_index < new_index:
                conn.execute(
                    "UPDATE playlist_tracks"
                    " SET position = position - 1"
                    " WHERE playlist_id = ?"
                    " AND server_id = ?"
                    " AND position > ?"
                    " AND position <= ?",
                    (
                        playlist_id, server_id,
                        old_index, new_index,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE playlist_tracks"
                    " SET position = position + 1"
                    " WHERE playlist_id = ?"
                    " AND server_id = ?"
                    " AND position >= ?"
                    " AND position < ?",
                    (
                        playlist_id, server_id,
                        new_index, old_index,
                    ),
                )
            conn.execute(
                "UPDATE playlist_tracks"
                " SET position = ?"
                " WHERE playlist_id = ?"
                " AND playlist_item_id = ?"
                " AND server_id = ?",
                (
                    new_index, playlist_id,
                    playlist_item_id, server_id,
                ),
            )

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
    is_active: bool = True


SCHEMA = """
-- Server credentials
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    access_token TEXT NOT NULL,
    device_id TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);

-- Music libraries
CREATE TABLE IF NOT EXISTS libraries (
    id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (id, server_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Cached tracks
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
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
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tracks_name ON tracks(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_server ON tracks(server_id);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album_id);
CREATE INDEX IF NOT EXISTS idx_tracks_library ON tracks(library_id);

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
    PRIMARY KEY (track_id, artist_id),
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Album-to-album_artist mapping
CREATE TABLE IF NOT EXISTS album_album_artists (
    album_id TEXT NOT NULL,
    album_artist_id TEXT NOT NULL,
    server_id INTEGER NOT NULL,
    PRIMARY KEY (album_id, album_artist_id),
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
    position INTEGER NOT NULL,
    server_id INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, track_id),
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
        """Save or update server credentials."""
        with self.connection() as conn:
            if creds.id is not None:
                conn.execute(
                    """
                    UPDATE servers SET
                        url = ?, user_id = ?, username = ?,
                        access_token = ?, device_id = ?, is_active = ?
                    WHERE id = ?
                    """,
                    (
                        creds.url,
                        creds.user_id,
                        creds.username,
                        creds.access_token,
                        creds.device_id,
                        int(creds.is_active),
                        creds.id,
                    ),
                )
                return creds.id
            else:
                conn.execute("UPDATE servers SET is_active = 0")
                cursor = conn.execute(
                    """
                    INSERT INTO servers
                        (url, user_id, username, access_token, device_id,
                         is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
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

    def get_active_server(self) -> ServerCredentials | None:
        """Get the currently active server credentials."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM servers WHERE is_active = 1 LIMIT 1"
            ).fetchone()
            if row:
                return ServerCredentials(
                    id=row["id"],
                    url=row["url"],
                    user_id=row["user_id"],
                    username=row["username"],
                    access_token=row["access_token"],
                    device_id=row["device_id"],
                    is_active=bool(row["is_active"]),
                )
            return None

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
        """Cache the list of music libraries for a server."""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM libraries WHERE server_id = ?",
                (server_id,),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO libraries"
                " (id, server_id, name) VALUES (?, ?, ?)",
                [
                    (lib["Id"], server_id, lib.get("Name", ""))
                    for lib in libraries
                    if lib.get("Id")
                ],
            )

    def get_libraries(self, server_id: int) -> list[dict]:
        """Get cached music libraries for a server."""
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
                {"Id": r["id"], "Name": r["name"]}
                for r in rows
            ]

    def cache_library(
        self, server_id: int, tracks: list[dict],
    ) -> None:
        """Cache the full library extracted from the tracks response.

        Populates tracks, artists, album_artists, albums, and all
        mapping tables from a single get_all_tracks() API response.
        Each track dict may contain a "LibraryId" key indicating
        which music library it belongs to.
        """
        with self.connection() as conn:
            # Clear existing library data for this server
            for table in (
                "track_artists", "album_album_artists",
                "tracks", "artists", "album_artists", "albums",
            ):
                conn.execute(
                    f"DELETE FROM {table} WHERE server_id = ?",
                    (server_id,),
                )

            artists_seen: dict[str, str] = {}
            album_artists_seen: dict[str, str] = {}
            albums_seen: dict[str, tuple[str, str, str]] = {}
            track_artist_links: list[tuple[str, str]] = []
            album_aa_links: set[tuple[str, str]] = set()

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

                # Insert track
                conn.execute(
                    """
                    INSERT OR REPLACE INTO tracks (
                        id, server_id, name, album_name,
                        artist_name, artist_display,
                        album_id, artist_id,
                        duration_ticks, track_number,
                        library_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
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
                    ),
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
                    " (playlist_id, track_id, position,"
                    " server_id)"
                    " VALUES (?, ?, ?, ?)",
                    [
                        (
                            pl_id, item.get("Id"),
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

    def get_all_tracks(
        self,
        server_id: int,
        library_ids: set[str] | None = None,
    ) -> list[dict]:
        """Get all cached tracks for a server."""
        lib_sql, lib_params = self._lib_filter(library_ids)
        with self.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM tracks
                WHERE server_id = ?{lib_sql}
                ORDER BY
                    artist_name COLLATE NOCASE,
                    album_name COLLATE NOCASE,
                    track_number
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
                SELECT t.* FROM tracks t
                JOIN playlist_tracks pt ON pt.track_id = t.id
                    AND pt.server_id = t.server_id
                WHERE pt.playlist_id = ? AND t.server_id = ?
                ORDER BY pt.position
                """,
                (playlist_id, server_id),
            ).fetchall()
            return [self._track_to_dict(r) for r in rows]

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

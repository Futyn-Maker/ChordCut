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

-- Cached tracks for searching
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    album_name TEXT,
    artist_name TEXT,
    album_id TEXT,
    artist_id TEXT,
    duration_ticks INTEGER,
    track_number INTEGER,
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

-- Index for fast search
CREATE INDEX IF NOT EXISTS idx_tracks_name ON tracks(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tracks_server ON tracks(server_id);

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
        """Initialize database manager.

        Args:
            db_path: Path to database file. If None, uses default location.
        """
        self.db_path = db_path or get_db_path()
        self._init_schema()

    def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection as a context manager.

        Yields:
            SQLite connection with row factory set to sqlite3.Row.
        """
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

    def save_server(self, creds: ServerCredentials) -> int:
        """Save or update server credentials.

        Args:
            creds: Server credentials to save.

        Returns:
            The server ID.
        """
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
                # Deactivate other servers
                conn.execute("UPDATE servers SET is_active = 0")
                cursor = conn.execute(
                    """
                    INSERT INTO servers
                        (url, user_id, username, access_token, device_id, is_active)
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
                # lastrowid is always set after INSERT
                return cursor.lastrowid or 0

    def get_active_server(self) -> ServerCredentials | None:
        """Get the currently active server credentials.

        Returns:
            ServerCredentials if an active server exists, None otherwise.
        """
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
        """Delete a server and its cached data.

        Args:
            server_id: ID of the server to delete.
        """
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM tracks WHERE server_id = ?", (server_id,)
            )
            conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))

    def cache_tracks(self, server_id: int, tracks: list[dict]) -> None:
        """Cache track data for fast local searching.

        Args:
            server_id: Server ID these tracks belong to.
            tracks: List of track dictionaries from Jellyfin API.
        """
        with self.connection() as conn:
            # Clear existing tracks for this server
            conn.execute(
                "DELETE FROM tracks WHERE server_id = ?", (server_id,)
            )

            # Insert new tracks
            for track in tracks:
                # Extract artist name from various possible fields
                artists = track.get("Artists", [])
                artist_name = track.get("AlbumArtist") or (
                    artists[0] if artists else ""
                )

                # Extract artist ID if available
                artist_items = track.get("ArtistItems", [])
                artist_id = (
                    artist_items[0].get("Id") if artist_items else None
                )

                conn.execute(
                    """
                    INSERT INTO tracks (
                        id, server_id, name, album_name, artist_name,
                        album_id, artist_id, duration_ticks, track_number
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        track.get("Id"),
                        server_id,
                        track.get("Name", "Unknown"),
                        track.get("Album", ""),
                        artist_name,
                        track.get("AlbumId"),
                        artist_id,
                        track.get("RunTimeTicks"),
                        track.get("IndexNumber"),
                    ),
                )

    @staticmethod
    def _row_to_api_format(row: sqlite3.Row) -> dict:
        """Convert a DB row to Jellyfin-API-compatible dict.

        The UI expects PascalCase keys matching the Jellyfin API
        (Id, Name, Album, AlbumArtist, RunTimeTicks, etc.).
        """
        return {
            "Id": row["id"],
            "Name": row["name"],
            "Album": row["album_name"] or "",
            "AlbumArtist": row["artist_name"] or "",
            "AlbumId": row["album_id"],
            "RunTimeTicks": row["duration_ticks"],
            "IndexNumber": row["track_number"],
        }

    def search_tracks(self, server_id: int, query: str) -> list[dict]:
        """Search cached tracks by name.

        Args:
            server_id: Server ID to search within.
            query: Search query (partial match).

        Returns:
            List of matching track dicts (Jellyfin API key format).
        """
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
            return [self._row_to_api_format(r) for r in rows]

    def get_all_tracks(self, server_id: int) -> list[dict]:
        """Get all cached tracks for a server.

        Args:
            server_id: Server ID to get tracks for.

        Returns:
            List of all track dicts (Jellyfin API key format).
        """
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tracks
                WHERE server_id = ?
                ORDER BY
                    artist_name COLLATE NOCASE,
                    album_name COLLATE NOCASE,
                    track_number
                """,
                (server_id,),
            ).fetchall()
            return [self._row_to_api_format(r) for r in rows]

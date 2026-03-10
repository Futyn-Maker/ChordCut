"""Database schema and data models for ChordCut."""

from dataclasses import dataclass


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
"""

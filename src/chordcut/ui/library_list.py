"""Display formatters for library items.

These strings are what screen readers announce for each list row, so
they stay deliberately terse: one line per item.
"""

from collections.abc import Callable

from chordcut.i18n import _
from chordcut.player.mpv_player import format_duration

# --- Formatting functions ---


def format_track(track: dict) -> str:
    """Format a track for display.

    Format: "Artist(s) \u2014 Title  Duration"
    Falls back to "Title  Duration" when no artist.
    """
    artist = track.get(
        "ArtistDisplay",
        track.get("AlbumArtist", ""),
    )
    # Translators: Fallback when a track has no title.
    name = track.get("Name") or _("Untitled")
    ticks = track.get("RunTimeTicks", 0)
    dur = format_duration(ticks / 10_000_000) if ticks else ""

    if artist:
        # Translators: Track format: {artist} \u2014 {title}  {duration}
        return _("{artist} — {title}  {duration}").format(
            artist=artist,
            title=name,
            duration=dur,
        )
    # Translators: Track format without artist.
    return _("{title}  {duration}").format(
        title=name,
        duration=dur,
    )


def format_artist(item: dict) -> str:
    """Format an artist / album artist for display."""
    # Translators: Fallback when an artist has no name.
    return item.get("Name") or _("Untitled")


def format_album(item: dict) -> str:
    """Format an album for display.

    Format: "Artist(s) \u2014 Album Name"
    Falls back to just the album name when no artist.
    """
    artist = item.get("ArtistDisplay", "")
    # Translators: Fallback when an album has no title.
    name = item.get("Name") or _("Untitled")
    if artist:
        return f"{artist} \u2014 {name}"
    return name


def format_playlist(item: dict) -> str:
    """Format a playlist for display."""
    # Translators: Fallback when a playlist has no name.
    return item.get("Name") or _("Untitled")


# Formatter lookup by level type
FORMATTERS: dict[str, Callable[[dict], str]] = {
    "tracks": format_track,
    "artists": format_artist,
    "album_artists": format_artist,
    "albums": format_album,
    "playlists": format_playlist,
}

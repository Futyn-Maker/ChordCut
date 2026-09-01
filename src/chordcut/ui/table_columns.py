"""Column models for TrackTableView.

Columns are purely visual. Screen reader names always come from the
formatters in library_list.py (FORMATTERS), never from columns.
"""

from collections.abc import Callable
from dataclasses import dataclass

import wx

from chordcut.i18n import _
from chordcut.player.mpv_player import format_duration


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    # Deferred so the translation is looked up at draw time.
    heading: Callable[[], str]
    weight: int  # proportional width; 0 = fixed
    fixed_dip: int  # used when weight == 0
    align: int  # wx.ALIGN_LEFT or wx.ALIGN_RIGHT
    cell: Callable[[dict], str]
    secondary: bool = False  # drawn in the secondary text color
    # Dropped when the window is too narrow to give every flexible
    # column a readable width (the way streaming players hide their
    # secondary columns in small windows).
    optional: bool = False


def _artist_of(item: dict) -> str:
    return item.get("ArtistDisplay") or item.get("AlbumArtist", "") or ""


def _duration_of(item: dict) -> str:
    ticks = item.get("RunTimeTicks", 0)
    return format_duration(ticks / 10_000_000) if ticks else ""


def _index_of(item: dict) -> str:
    idx = item.get("IndexNumber")
    return str(idx) if idx else ""


COLUMN_MODELS: dict[str, list[ColumnSpec]] = {
    "tracks": [
        ColumnSpec(
            "title",
            # Translators: Column header for the track title.
            lambda: _("Title"),
            weight=4,
            fixed_dip=0,
            align=wx.ALIGN_LEFT,
            cell=lambda i: i.get("Name") or "",
        ),
        ColumnSpec(
            "artist",
            # Translators: Column header for the track artist.
            lambda: _("Artist"),
            weight=3,
            fixed_dip=0,
            align=wx.ALIGN_LEFT,
            cell=_artist_of,
            secondary=True,
        ),
        ColumnSpec(
            "album",
            # Translators: Column header for the album name.
            lambda: _("Album"),
            weight=3,
            fixed_dip=0,
            align=wx.ALIGN_LEFT,
            cell=lambda i: i.get("Album") or "",
            secondary=True,
            optional=True,
        ),
        ColumnSpec(
            "index",
            # Translators: Column header for the track number. Keep short.
            lambda: _("#"),
            weight=0,
            fixed_dip=40,
            align=wx.ALIGN_RIGHT,
            cell=_index_of,
            secondary=True,
        ),
        ColumnSpec(
            "duration",
            # Translators: Column header for the track duration.
            lambda: _("Length"),
            weight=0,
            fixed_dip=64,
            align=wx.ALIGN_RIGHT,
            cell=_duration_of,
            secondary=True,
        ),
    ],
    "albums": [
        ColumnSpec(
            "album",
            # Translators: Column header for the album name.
            lambda: _("Album"),
            weight=4,
            fixed_dip=0,
            align=wx.ALIGN_LEFT,
            cell=lambda i: i.get("Name") or "",
        ),
        ColumnSpec(
            "artist",
            # Translators: Column header for the album artist.
            lambda: _("Artist"),
            weight=3,
            fixed_dip=0,
            align=wx.ALIGN_LEFT,
            cell=lambda i: i.get("ArtistDisplay") or "",
            secondary=True,
        ),
    ],
    "artists": [
        ColumnSpec(
            "name",
            # Translators: Column header for the artist name.
            lambda: _("Artist"),
            weight=1,
            fixed_dip=0,
            align=wx.ALIGN_LEFT,
            cell=lambda i: i.get("Name") or "",
        ),
    ],
    "album_artists": [
        ColumnSpec(
            "name",
            # Translators: Column header for the album artist name.
            lambda: _("Album artist"),
            weight=1,
            fixed_dip=0,
            align=wx.ALIGN_LEFT,
            cell=lambda i: i.get("Name") or "",
        ),
    ],
    "playlists": [
        ColumnSpec(
            "name",
            # Translators: Column header for the playlist name.
            lambda: _("Playlist"),
            weight=1,
            fixed_dip=0,
            align=wx.ALIGN_LEFT,
            cell=lambda i: i.get("Name") or "",
        ),
    ],
}

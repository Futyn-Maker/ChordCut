"""Reusable list widget and formatters for library items."""

from typing import Callable

import wx

from groove.i18n import _
from groove.player.mpv_player import format_duration


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
    # Translators: Fallback track title when the track has no name.
    name = track.get("Name", _("Unknown"))
    ticks = track.get("RunTimeTicks", 0)
    dur = format_duration(ticks / 10_000_000) if ticks else ""

    if artist:
        # Translators: Track format: {artist} \u2014 {title}  {duration}
        return _(
            "{artist} \u2014 {title}  {duration}"
        ).format(artist=artist, title=name, duration=dur)
    # Translators: Track format without artist.
    return _("{title}  {duration}").format(
        title=name, duration=dur,
    )


def format_artist(item: dict) -> str:
    """Format an artist / album artist for display."""
    return item.get("Name", "")


def format_album(item: dict) -> str:
    """Format an album for display.

    Format: "Artist(s) \u2014 Album Name"
    Falls back to just the album name when no artist.
    """
    artist = item.get("ArtistDisplay", "")
    name = item.get("Name", "")
    if artist:
        return f"{artist} \u2014 {name}"
    return name


def format_playlist(item: dict) -> str:
    """Format a playlist for display."""
    return item.get("Name", "")


# Formatter lookup by level type
FORMATTERS: dict[str, Callable[[dict], str]] = {
    "tracks": format_track,
    "artists": format_artist,
    "album_artists": format_artist,
    "albums": format_album,
    "playlists": format_playlist,
}


class LibraryListBox(wx.ListBox):
    """Generic list control for library items.

    Uses a native Win32 LISTBOX for perfect NVDA/JAWS support.
    Stores a parallel list[dict] and uses a pluggable formatter.
    """

    def __init__(self, parent: wx.Window):
        super().__init__(
            parent,
            style=wx.LB_SINGLE,
            # Translators: Accessible name for the library list.
            name=_("Library"),
        )
        self._items: list[dict] = []
        self._formatter: Callable[[dict], str] = format_track

    def set_formatter(
        self, formatter: Callable[[dict], str],
    ) -> None:
        """Change the display formatter."""
        self._formatter = formatter

    def set_items(self, items: list[dict]) -> None:
        """Replace all items, preserving focus by Id."""
        old_id = self._get_focused_id()
        had_items = len(self._items) > 0

        self._items = items

        self.Freeze()
        self.Clear()
        if items:
            self.Set([self._formatter(i) for i in items])
        self.Thaw()

        if old_id and items:
            new_idx = self._find_by_id(old_id)
            if new_idx is not None:
                self.SetSelection(new_idx)
            else:
                sel = self.GetSelection()
                self.SetSelection(
                    min(max(sel, 0), len(items) - 1)
                )
        elif not had_items and items:
            self.SetSelection(0)

    def set_selection_by_id(self, item_id: str) -> None:
        """Set selection to the item with the given Id."""
        idx = self._find_by_id(item_id)
        if idx is not None:
            self.SetSelection(idx)

    def get_selected_item(self) -> dict | None:
        """Get the currently selected item dict."""
        idx = self.GetSelection()
        if 0 <= idx < len(self._items):
            return self._items[idx]
        return None

    def get_item(self, index: int) -> dict | None:
        """Get the item dict at the given index."""
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def _get_focused_id(self) -> str | None:
        idx = self.GetSelection()
        if idx != wx.NOT_FOUND and idx < len(self._items):
            return self._items[idx].get("Id")
        return None

    def _find_by_id(self, item_id: str) -> int | None:
        for i, item in enumerate(self._items):
            if item.get("Id") == item_id:
                return i
        return None

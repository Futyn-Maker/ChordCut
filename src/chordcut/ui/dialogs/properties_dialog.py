"""Properties dialog for library items."""

import wx

from chordcut.i18n import _, ngettext
from chordcut.player.mpv_player import format_duration


class PropertiesDialog(wx.Dialog):
    """Shows properties of a library item in a ListBox."""

    def __init__(
        self,
        parent: wx.Window,
        title: str,
        properties: list[str],
    ):
        super().__init__(
            parent,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(450, 350),
        )

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self._list = wx.ListBox(
            panel,
            style=wx.LB_SINGLE,
            name=title,
        )
        self._list.Set(properties)
        if properties:
            self._list.SetSelection(0)

        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 10)

        close_btn = wx.Button(panel, wx.ID_CLOSE)
        sizer.Add(
            close_btn, 0,
            wx.ALIGN_CENTER | wx.BOTTOM, 10,
        )

        panel.SetSizer(sizer)

        close_btn.Bind(
            wx.EVT_BUTTON, lambda e: self.Close(),
        )
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_key(self, event: wx.KeyEvent) -> None:
        code = event.GetKeyCode()
        if code == wx.WXK_ESCAPE:
            self.Close()
            return
        if event.ControlDown() and code == ord("C"):
            idx = self._list.GetSelection()
            if idx != wx.NOT_FOUND:
                text = self._list.GetString(idx)
                # Copy only the value (after ": ")
                if ": " in text:
                    text = text.split(": ", 1)[1]
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(
                        wx.TextDataObject(text),
                    )
                    wx.TheClipboard.Close()
            return
        event.Skip()


def _fmt_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return "{n} B".format(n=size_bytes)
    if size_bytes < 1024 * 1024:
        return "{n:.1f} KB".format(
            n=size_bytes / 1024,
        )
    if size_bytes < 1024 * 1024 * 1024:
        return "{n:.1f} MB".format(
            n=size_bytes / (1024 * 1024),
        )
    return "{n:.2f} GB".format(
        n=size_bytes / (1024 * 1024 * 1024),
    )


def _fmt_bitrate(bps: int) -> str:
    """Format bitrate in kbps."""
    return "{n} kbps".format(n=bps // 1000)


def build_track_properties(
    track: dict,
    details: dict | None = None,
) -> list[str]:
    """Build property lines for a track."""
    props = []
    # Translators: Track property: title.
    props.append(
        _("Title: {value}").format(
            value=track.get("Name", ""),
        )
    )
    # Translators: Track property: artist.
    props.append(
        _("Artist: {value}").format(
            value=track.get("ArtistDisplay", ""),
        )
    )
    # Translators: Track property: album artist.
    props.append(
        _("Album Artist: {value}").format(
            value=track.get("AlbumArtist", ""),
        )
    )
    # Translators: Track property: album.
    props.append(
        _("Album: {value}").format(
            value=track.get("Album", ""),
        )
    )

    ticks = track.get("RunTimeTicks", 0)
    if ticks:
        # Translators: Track property: duration.
        props.append(
            _("Duration: {value}").format(
                value=format_duration(
                    ticks / 10_000_000,
                ),
            )
        )

    idx_num = track.get("IndexNumber")
    if idx_num:
        # Translators: Track property: track number.
        props.append(
            _("Track Number: {value}").format(
                value=idx_num,
            )
        )

    # Details from API (MediaSources)
    if details:
        sources = details.get("MediaSources", [])
        if sources:
            src = sources[0]
            container = src.get("Container", "")
            if container:
                # Translators: Track property: format.
                props.append(
                    _("Format: {value}").format(
                        value=container.upper(),
                    )
                )
            bitrate = src.get("Bitrate", 0)
            if bitrate:
                # Translators: Track property: bitrate.
                props.append(
                    _("Bitrate: {value}").format(
                        value=_fmt_bitrate(bitrate),
                    )
                )
            size = src.get("Size", 0)
            if size:
                # Translators: Track property: file size.
                props.append(
                    _("File Size: {value}").format(
                        value=_fmt_size(size),
                    )
                )

        date_created = details.get("DateCreated", "")
        if date_created:
            # Show just the date part
            date_str = date_created[:10]
            # Translators: Track property: date added.
            props.append(
                _("Date Added: {value}").format(
                    value=date_str,
                )
            )

    return props


def build_artist_properties(
    artist: dict, stats: dict,
) -> list[str]:
    """Build property lines for an artist."""
    props = []
    # Translators: Artist property: name.
    props.append(
        _("Name: {value}").format(
            value=artist.get("Name", ""),
        )
    )
    n_albums = stats.get("album_count", 0)
    # Translators: Artist property: album count.
    props.append(
        ngettext(
            "{n} album", "{n} albums", n_albums,
        ).format(n=n_albums)
    )
    n_tracks = stats.get("track_count", 0)
    # Translators: Artist property: track count.
    props.append(
        ngettext(
            "{n} track", "{n} tracks", n_tracks,
        ).format(n=n_tracks)
    )
    return props


def build_album_properties(
    album: dict, stats: dict,
) -> list[str]:
    """Build property lines for an album."""
    props = []
    # Translators: Album property: name.
    props.append(
        _("Name: {value}").format(
            value=album.get("Name", ""),
        )
    )
    # Translators: Album property: artist.
    props.append(
        _("Artist: {value}").format(
            value=album.get("ArtistDisplay", ""),
        )
    )
    n_tracks = stats.get("track_count", 0)
    # Translators: Album property: track count.
    props.append(
        ngettext(
            "{n} track", "{n} tracks", n_tracks,
        ).format(n=n_tracks)
    )
    total_ticks = stats.get("total_duration_ticks", 0)
    if total_ticks:
        # Translators: Album property: total duration.
        props.append(
            _("Total Duration: {value}").format(
                value=format_duration(
                    total_ticks / 10_000_000,
                ),
            )
        )
    return props


def build_playlist_properties(
    playlist: dict, stats: dict,
) -> list[str]:
    """Build property lines for a playlist."""
    props = []
    # Translators: Playlist property: name.
    props.append(
        _("Name: {value}").format(
            value=playlist.get("Name", ""),
        )
    )
    n_tracks = stats.get("track_count", 0)
    # Translators: Playlist property: track count.
    props.append(
        ngettext(
            "{n} track", "{n} tracks", n_tracks,
        ).format(n=n_tracks)
    )
    total_ticks = stats.get("total_duration_ticks", 0)
    if total_ticks:
        # Translators: Playlist property: total duration.
        props.append(
            _("Total Duration: {value}").format(
                value=format_duration(
                    total_ticks / 10_000_000,
                ),
            )
        )
    return props

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

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: Button to copy the selected property value to the clipboard.
        copy_btn = wx.Button(panel, wx.ID_ANY, _("&Copy"))
        close_btn = wx.Button(panel, wx.ID_CLOSE)
        btn_sizer.Add(copy_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(close_btn, 0)
        sizer.Add(
            btn_sizer,
            0,
            wx.ALIGN_CENTER | wx.BOTTOM,
            10,
        )

        panel.SetSizer(sizer)

        copy_btn.Bind(
            wx.EVT_BUTTON,
            lambda e: self._copy_selected(),
        )
        close_btn.Bind(
            wx.EVT_BUTTON,
            lambda e: self.Close(),
        )
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _copy_selected(self) -> None:
        """Copy the selected property value to the clipboard."""
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

    def _on_key(self, event: wx.KeyEvent) -> None:
        code = event.GetKeyCode()
        if code == wx.WXK_ESCAPE:
            self.Close()
            return
        if event.ControlDown() and code == ord("C"):
            self._copy_selected()
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
    props.append(
        # Translators: Track property: title.
        _("Title: {value}").format(
            value=track.get("Name", ""),
        )
    )
    props.append(
        # Translators: Track property: artist.
        _("Artist: {value}").format(
            value=track.get("ArtistDisplay", ""),
        )
    )
    props.append(
        # Translators: Track property: album artist.
        _("Album Artist: {value}").format(
            value=track.get("AlbumArtist", ""),
        )
    )
    props.append(
        # Translators: Track property: album.
        _("Album: {value}").format(
            value=track.get("Album", ""),
        )
    )

    ticks = track.get("RunTimeTicks", 0)
    if ticks:
        props.append(
            # Translators: Track property: duration.
            _("Duration: {value}").format(
                value=format_duration(
                    ticks / 10_000_000,
                ),
            )
        )

    idx_num = track.get("IndexNumber")
    if idx_num:
        props.append(
            # Translators: Track property: track number.
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
                props.append(
                    # Translators: Track property: format.
                    _("Format: {value}").format(
                        value=container.upper(),
                    )
                )
            bitrate = src.get("Bitrate", 0)
            if bitrate:
                props.append(
                    # Translators: Track property: bitrate.
                    _("Bitrate: {value}").format(
                        value=_fmt_bitrate(bitrate),
                    )
                )
            size = src.get("Size", 0)
            if size:
                props.append(
                    # Translators: Track property: file size.
                    _("File Size: {value}").format(
                        value=_fmt_size(size),
                    )
                )

        date_created = details.get("DateCreated", "")
        if date_created:
            # Show just the date part
            date_str = date_created[:10]
            props.append(
                # Translators: Track property: date added.
                _("Date Added: {value}").format(
                    value=date_str,
                )
            )

    return props


def build_artist_properties(
    artist: dict,
    stats: dict,
) -> list[str]:
    """Build property lines for an artist."""
    props = []
    props.append(
        # Translators: Artist property: name.
        _("Name: {value}").format(
            value=artist.get("Name", ""),
        )
    )
    n_albums = stats.get("album_count", 0)
    props.append(
        # Translators: Artist property: album count.
        ngettext("{n} album", "{n} albums", n_albums).format(n=n_albums)
    )
    n_tracks = stats.get("track_count", 0)
    props.append(
        # Translators: Artist property: track count.
        ngettext("{n} track", "{n} tracks", n_tracks).format(n=n_tracks)
    )
    return props


def build_album_properties(
    album: dict,
    stats: dict,
) -> list[str]:
    """Build property lines for an album."""
    props = []
    props.append(
        # Translators: Album property: name.
        _("Name: {value}").format(
            value=album.get("Name", ""),
        )
    )
    props.append(
        # Translators: Album property: artist.
        _("Artist: {value}").format(
            value=album.get("ArtistDisplay", ""),
        )
    )
    n_tracks = stats.get("track_count", 0)
    props.append(
        # Translators: Album property: track count.
        ngettext("{n} track", "{n} tracks", n_tracks).format(n=n_tracks)
    )
    total_ticks = stats.get("total_duration_ticks", 0)
    if total_ticks:
        props.append(
            # Translators: Album property: total duration.
            _("Total Duration: {value}").format(
                value=format_duration(
                    total_ticks / 10_000_000,
                ),
            )
        )
    return props


def build_playlist_properties(
    playlist: dict,
    stats: dict,
) -> list[str]:
    """Build property lines for a playlist."""
    props = []
    props.append(
        # Translators: Playlist property: name.
        _("Name: {value}").format(
            value=playlist.get("Name", ""),
        )
    )
    n_tracks = stats.get("track_count", 0)
    props.append(
        # Translators: Playlist property: track count.
        ngettext("{n} track", "{n} tracks", n_tracks).format(n=n_tracks)
    )
    total_ticks = stats.get("total_duration_ticks", 0)
    if total_ticks:
        props.append(
            # Translators: Playlist property: total duration.
            _("Total Duration: {value}").format(
                value=format_duration(
                    total_ticks / 10_000_000,
                ),
            )
        )
    return props

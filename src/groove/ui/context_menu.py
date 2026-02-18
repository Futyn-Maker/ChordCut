"""Dynamic context menu builder for library items."""

import wx

from groove.i18n import _

# Stable IDs for context menu items
ID_PLAY = wx.NewIdRef()
ID_OPEN = wx.NewIdRef()
ID_GO_BACK = wx.NewIdRef()
ID_GO_TO_ARTIST = wx.NewIdRef()
ID_GO_TO_ALBUM_ARTIST = wx.NewIdRef()
ID_GO_TO_ALBUM = wx.NewIdRef()
ID_VIEW_LYRICS = wx.NewIdRef()
ID_SYNCED_LYRICS = wx.NewIdRef()
ID_DOWNLOAD = wx.NewIdRef()
ID_COPY_LINK = wx.NewIdRef()
ID_COPY_STREAM = wx.NewIdRef()
ID_PROPERTIES = wx.NewIdRef()


def build_context_menu(
    level_type: str,
    item: dict,
    nav_depth: int,
) -> wx.Menu:
    """Build a context menu for the given item type."""
    menu = wx.Menu()

    if level_type == "tracks":
        # Translators: Context menu: play track.
        menu.Append(ID_PLAY, _("&Play"))
        if nav_depth > 0:
            # Translators: Context menu: go back.
            menu.Append(
                ID_GO_BACK, _("Go &Back\tBackspace"),
            )
        menu.AppendSeparator()
        # Translators: Context menu: go to artist.
        menu.Append(
            ID_GO_TO_ARTIST, _("Go to &Artist"),
        )
        # Translators: Context menu: go to album artist.
        menu.Append(
            ID_GO_TO_ALBUM_ARTIST,
            _("Go to Album A&rtist"),
        )
        # Translators: Context menu: go to album.
        menu.Append(
            ID_GO_TO_ALBUM, _("Go to A&lbum"),
        )
        menu.AppendSeparator()
        # Translators: Context menu: view lyrics.
        menu.Append(
            ID_VIEW_LYRICS, _("View &Lyrics"),
        )
        # Translators: Context menu: synced lyrics.
        menu.Append(
            ID_SYNCED_LYRICS, _("&Synced Lyrics"),
        )
        menu.AppendSeparator()
        # Translators: Context menu: download track.
        menu.Append(
            ID_DOWNLOAD,
            _("&Download\tCtrl+Shift+Enter"),
        )
    else:
        # Non-track items: artists, albums, playlists
        # Translators: Context menu: open item.
        menu.Append(ID_OPEN, _("&Open\tEnter"))
        if nav_depth > 0:
            # Translators: Context menu: go back.
            menu.Append(
                ID_GO_BACK, _("Go &Back\tBackspace"),
            )

        if level_type == "albums":
            menu.AppendSeparator()
            # Translators: Context menu: go to album artist.
            menu.Append(
                ID_GO_TO_ALBUM_ARTIST,
                _("Go to Album A&rtist"),
            )

    menu.AppendSeparator()
    # Translators: Context menu: copy link.
    menu.Append(
        ID_COPY_LINK, _("&Copy Link\tCtrl+C"),
    )
    if level_type == "tracks":
        # Translators: Context menu: copy stream link.
        menu.Append(
            ID_COPY_STREAM,
            _("Copy &Stream Link\tCtrl+Shift+C"),
        )
    # Translators: Context menu: properties.
    menu.Append(
        ID_PROPERTIES, _("P&roperties\tAlt+Enter"),
    )

    return menu

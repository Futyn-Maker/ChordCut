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
ID_REMOVE_FROM_PLAYLIST = wx.NewIdRef()
ID_MOVE_UP = wx.NewIdRef()
ID_MOVE_DOWN = wx.NewIdRef()
ID_RENAME_PLAYLIST = wx.NewIdRef()
ID_DELETE_PLAYLIST = wx.NewIdRef()


def build_context_menu(
    level_type: str,
    item: dict,
    nav_depth: int,
    *,
    in_playlist: bool = False,
    playlists: list[dict] | None = None,
    track_in_playlists: set[str] | None = None,
    item_index: int = 0,
    total_items: int = 0,
) -> tuple[wx.Menu, dict[int, dict]]:
    """Build a context menu for the given item type.

    Returns ``(menu, playlist_id_map)`` where
    *playlist_id_map* maps wx menu-item IDs to playlist
    dicts (only populated for the "Add to Playlist"
    submenu).
    """
    menu = wx.Menu()
    playlist_id_map: dict[int, dict] = {}

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

        # "Add to Playlist" submenu
        if playlists:
            sub = wx.Menu()
            track_pls = track_in_playlists or set()
            for pl in playlists:
                mid = wx.NewIdRef()
                mi = sub.Append(
                    mid, pl.get("Name", ""),
                )
                playlist_id_map[int(mid)] = pl
                if pl.get("Id", "") in track_pls:
                    mi.Enable(False)
            # Translators: Context menu: add to playlist.
            menu.AppendSubMenu(
                sub, _("Add to &Playlist"),
            )

        # Playlist-specific actions
        if in_playlist:
            # Translators: Context menu: remove track
            # from playlist.
            menu.Append(
                ID_REMOVE_FROM_PLAYLIST,
                _("&Remove from Playlist\tDelete"),
            )
            menu.AppendSeparator()
            # Translators: Context menu: move track up
            # in playlist.
            mi_up = menu.Append(
                ID_MOVE_UP,
                _("Move &Up\tAlt+Up"),
            )
            # Translators: Context menu: move track down
            # in playlist.
            mi_down = menu.Append(
                ID_MOVE_DOWN,
                _("Move Dow&n\tAlt+Down"),
            )
            if item_index <= 0:
                mi_up.Enable(False)
            if item_index >= total_items - 1:
                mi_down.Enable(False)

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
            # Translators: Context menu: go to album
            # artist.
            menu.Append(
                ID_GO_TO_ALBUM_ARTIST,
                _("Go to Album A&rtist"),
            )

        if level_type == "playlists":
            menu.AppendSeparator()
            # Translators: Context menu: rename playlist.
            menu.Append(
                ID_RENAME_PLAYLIST,
                _("&Rename\tF2"),
            )
            # Translators: Context menu: delete playlist.
            menu.Append(
                ID_DELETE_PLAYLIST,
                _("&Delete\tDelete"),
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

    return menu, playlist_id_map

"""Dynamic context menu builder for library items."""

import wx

from chordcut.i18n import _

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

# Selection area context menu IDs
ID_SEL_PLAY = wx.NewIdRef()
ID_SEL_REMOVE = wx.NewIdRef()
ID_SEL_DOWNLOAD_ALL = wx.NewIdRef()
ID_SEL_COPY_LINKS = wx.NewIdRef()
ID_SEL_COPY_STREAM_LINKS = wx.NewIdRef()
ID_SEL_REMOVE_FROM_PLAYLIST = wx.NewIdRef()
ID_SEL_MOVE_UP = wx.NewIdRef()
ID_SEL_MOVE_DOWN = wx.NewIdRef()


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
    moves_locked: bool = False,
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
            menu.Append(
                ID_GO_BACK,
                # Translators: Context menu: go back.
                _("Go &Back\tBackspace"),
            )
        menu.AppendSeparator()
        menu.Append(
            ID_GO_TO_ARTIST,
            # Translators: Context menu: go to artist.
            _("Go to &Artist"),
        )
        menu.Append(
            ID_GO_TO_ALBUM_ARTIST,
            # Translators: Context menu: go to album artist.
            _("Go to Album A&rtist"),
        )
        menu.Append(
            ID_GO_TO_ALBUM,
            # Translators: Context menu: go to album.
            _("Go to A&lbum"),
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
            menu.AppendSubMenu(
                sub,
                # Translators: Context menu: add to playlist.
                _("Add to &Playlist"),
            )

        # Playlist-specific actions
        if in_playlist:
            menu.Append(
                ID_REMOVE_FROM_PLAYLIST,
                # Translators: Context menu: remove track
                # from playlist.
                _("&Remove from Playlist\tDelete"),
            )
            menu.AppendSeparator()
            mi_up = menu.Append(
                ID_MOVE_UP,
                # Translators: Context menu: move track up
                # in playlist.
                _("Move &Up\tAlt+Up"),
            )
            mi_down = menu.Append(
                ID_MOVE_DOWN,
                # Translators: Context menu: move track down
                # in playlist.
                _("Move Dow&n\tAlt+Down"),
            )
            if moves_locked or item_index <= 0:
                mi_up.Enable(False)
            if moves_locked or item_index >= total_items - 1:
                mi_down.Enable(False)

        menu.AppendSeparator()
        menu.Append(
            ID_VIEW_LYRICS,
            # Translators: Context menu: view lyrics.
            _("View &Lyrics"),
        )
        menu.Append(
            ID_SYNCED_LYRICS,
            # Translators: Context menu: synced lyrics.
            _("&Synced Lyrics"),
        )
        menu.AppendSeparator()
        menu.Append(
            ID_DOWNLOAD,
            # Translators: Context menu: download track.
            _("&Download\tCtrl+Shift+Enter"),
        )
    else:
        # Non-track items: artists, albums, playlists
        # Translators: Context menu: open item.
        menu.Append(ID_OPEN, _("&Open\tEnter"))
        if nav_depth > 0:
            menu.Append(
                ID_GO_BACK,
                # Translators: Context menu: go back.
                _("Go &Back\tBackspace"),
            )

        if level_type == "albums":
            menu.AppendSeparator()
            menu.Append(
                ID_GO_TO_ALBUM_ARTIST,
                # Translators: Context menu: go to album
                # artist.
                _("Go to Album A&rtist"),
            )

        if level_type == "playlists":
            menu.AppendSeparator()
            menu.Append(
                ID_RENAME_PLAYLIST,
                # Translators: Context menu: rename playlist.
                _("&Rename\tF2"),
            )
            menu.Append(
                ID_DELETE_PLAYLIST,
                # Translators: Context menu: delete playlist.
                _("&Delete\tDelete"),
            )

    menu.AppendSeparator()
    menu.Append(
        ID_COPY_LINK,
        # Translators: Context menu: copy link.
        _("&Copy Link\tCtrl+C"),
    )
    if level_type == "tracks":
        menu.Append(
            ID_COPY_STREAM,
            # Translators: Context menu: copy stream link.
            _("Copy &Stream Link\tCtrl+Shift+C"),
        )
    menu.Append(
        ID_PROPERTIES,
        # Translators: Context menu: properties.
        _("P&roperties\tAlt+Enter"),
    )

    return menu, playlist_id_map


def build_selection_context_menu(
    *,
    playlists: list[dict] | None = None,
    all_in_playlists: dict[str, bool] | None = None,
    can_remove_from_playlist: bool = False,
    item_index: int = 0,
    total_items: int = 0,
) -> tuple[wx.Menu, dict[int, dict]]:
    """Build context menu for the selected-tracks area.

    Returns ``(menu, playlist_id_map)`` like
    :func:`build_context_menu`.
    """
    menu = wx.Menu()
    playlist_id_map: dict[int, dict] = {}

    # Translators: Selection context menu: play track.
    menu.Append(ID_SEL_PLAY, _("&Play"))
    menu.AppendSeparator()

    # "Add All to Playlist" submenu
    if playlists:
        sub = wx.Menu()
        all_in = all_in_playlists or {}
        for pl in playlists:
            mid = wx.NewIdRef()
            mi = sub.Append(
                mid, pl.get("Name", ""),
            )
            playlist_id_map[int(mid)] = pl
            if all_in.get(pl.get("Id", "")):
                mi.Enable(False)
        menu.AppendSubMenu(
            sub,
            # Translators: Selection context menu:
            # add all to playlist.
            _("Add &All to Playlist"),
        )

    if can_remove_from_playlist:
        menu.Append(
            ID_SEL_REMOVE_FROM_PLAYLIST,
            # Translators: Selection context menu:
            # remove from playlist.
            _("&Remove All from Playlist"),
        )

    menu.AppendSeparator()
    menu.Append(
        ID_SEL_DOWNLOAD_ALL,
        # Translators: Selection context menu: download all.
        _("&Download All\tCtrl+Shift+Enter"),
    )
    menu.AppendSeparator()
    menu.Append(
        ID_SEL_COPY_LINKS,
        # Translators: Selection context menu: copy all links.
        _("&Copy All Links\tCtrl+C"),
    )
    menu.Append(
        ID_SEL_COPY_STREAM_LINKS,
        # Translators: Selection context menu:
        # copy all stream links.
        _("Copy All &Stream Links\tCtrl+Shift+C"),
    )
    menu.AppendSeparator()

    mi_up = menu.Append(
        ID_SEL_MOVE_UP,
        # Translators: Selection context menu: move up.
        _("Move &Up\tAlt+Up"),
    )
    mi_down = menu.Append(
        ID_SEL_MOVE_DOWN,
        # Translators: Selection context menu: move down.
        _("Move Dow&n\tAlt+Down"),
    )
    if item_index <= 0:
        mi_up.Enable(False)
    if item_index >= total_items - 1:
        mi_down.Enable(False)

    menu.AppendSeparator()
    menu.Append(
        ID_SEL_REMOVE,
        # Translators: Selection context menu:
        # remove from selection.
        _("Remove from Se&lection\tSpace"),
    )

    return menu, playlist_id_map

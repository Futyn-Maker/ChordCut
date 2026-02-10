"""Main application window for Groove."""

from dataclasses import dataclass

import wx

from groove import __app_name__, __version__
from groove.api import JellyfinClient
from groove.db import Database
from groove.i18n import _, ngettext
from groove.player import Player
from groove.player.mpv_player import format_duration
from groove.ui.library_list import (
    FORMATTERS,
    LibraryListBox,
)

# Section identifiers (order matches the wx.Choice control)
SECTIONS = (
    "tracks",
    "playlists",
    "artists",
    "album_artists",
    "albums",
)


def _section_display_names() -> list[str]:
    """Translated display names for the section selector."""
    return [
        # Translators: Section selector: all tracks.
        _("Tracks"),
        # Translators: Section selector: playlists.
        _("Playlists"),
        # Translators: Section selector: artists.
        _("Artists"),
        # Translators: Section selector: album artists.
        _("Album Artists"),
        # Translators: Section selector: albums.
        _("Albums"),
    ]


@dataclass
class _NavState:
    """Snapshot of one navigation level (for Backspace)."""

    all_items: list[dict]
    level_type: str
    context_name: str | None
    selected_id: str | None


class MainWindow(wx.Frame):
    """Main window with library navigation and playback."""

    _SEARCH_DELAY_MS = 50

    def __init__(
        self,
        db: Database,
        client: JellyfinClient,
        player: Player,
    ):
        super().__init__(
            None,
            title="{name} - {ver}".format(
                name=__app_name__, ver=__version__,
            ),
            size=(800, 600),
        )

        self._db = db
        self._client = client
        self._player = player

        # Current playback
        self._current_track: dict | None = None

        # Navigation state
        self._nav_stack: list[_NavState] = []
        self._current_level_type: str = "tracks"
        self._context_name: str | None = None
        self._all_items: list[dict] = []
        self._filtered_items: list[dict] = []

        # In-memory library (loaded from DB cache)
        self._lib_tracks: list[dict] = []
        self._lib_playlists: list[dict] = []
        self._lib_artists: list[dict] = []
        self._lib_album_artists: list[dict] = []
        self._lib_albums: list[dict] = []

        # Search debounce timer
        self._search_timer = wx.Timer(self)

        # Build UI
        self._create_menu_bar()
        self._create_controls()
        self._do_layout()
        self._bind_events()
        self._setup_player_callbacks()
        self._setup_accelerators()

        # Status bar
        self.CreateStatusBar(3)
        self.SetStatusWidths([-2, 150, 100])
        # Translators: Initial status bar message.
        self._update_status(_("Ready"))

        self.CenterOnScreen()

    # ------------------------------------------------------------------
    # UI creation
    # ------------------------------------------------------------------

    def _create_menu_bar(self) -> None:
        """Create the application menu bar."""
        menubar = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        self._menu_change_server = file_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item to switch server.
            _("Change &Server...\tCtrl+Shift+S"),
            # Translators: Help text for Change Server.
            _("Connect to a different server"),
        )
        file_menu.AppendSeparator()
        self._menu_exit = file_menu.Append(
            wx.ID_EXIT,
            # Translators: Menu item to exit.
            _("E&xit\tAlt+F4"),
            # Translators: Help text for Exit.
            _("Exit the application"),
        )
        # Translators: File menu label.
        menubar.Append(file_menu, _("&File"))

        # Playback menu
        playback_menu = wx.Menu()
        self._menu_play = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item to play.
            _("&Play"),
            # Translators: Help text for Play.
            _("Play selected track"),
        )
        self._menu_pause = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item to pause/resume.
            _("P&ause/Resume\tEscape"),
            # Translators: Help text for Pause/Resume.
            _("Pause or resume playback"),
        )
        self._menu_stop = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item to stop.
            _("&Stop\tCtrl+S"),
            # Translators: Help text for Stop.
            _("Stop playback"),
        )
        playback_menu.AppendSeparator()
        self._menu_volume_up = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item for volume up.
            _("Volume &Up\tCtrl+Up"),
            # Translators: Help text for Volume Up.
            _("Increase volume"),
        )
        self._menu_volume_down = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item for volume down.
            _("Volume &Down\tCtrl+Down"),
            # Translators: Help text for Volume Down.
            _("Decrease volume"),
        )
        playback_menu.AppendSeparator()
        self._menu_seek_fwd = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item to seek forward.
            _("Seek &Forward\tCtrl+Right"),
            # Translators: Help text for Seek Forward.
            _("Seek forward 10 seconds"),
        )
        self._menu_seek_bwd = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item to seek backward.
            _("Seek &Backward\tCtrl+Left"),
            # Translators: Help text for Seek Backward.
            _("Seek backward 10 seconds"),
        )
        # Translators: Playback menu label.
        menubar.Append(playback_menu, _("&Playback"))

        # View menu
        view_menu = wx.Menu()
        self._menu_refresh = view_menu.Append(
            wx.ID_REFRESH,
            # Translators: Menu item to refresh library.
            _("&Refresh Library\tF5"),
            # Translators: Help text for Refresh Library.
            _("Reload library from server"),
        )
        # Translators: View menu label.
        menubar.Append(view_menu, _("&View"))

        # Help menu
        help_menu = wx.Menu()
        self._menu_shortcuts = help_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item for shortcuts.
            _("&Keyboard Shortcuts\tF1"),
            # Translators: Help text for Keyboard Shortcuts.
            _("Show keyboard shortcuts"),
        )
        help_menu.AppendSeparator()
        self._menu_about = help_menu.Append(
            wx.ID_ABOUT,
            # Translators: Menu item for About.
            _("&About"),
            # Translators: Help text for About.
            _("About Groove"),
        )
        # Translators: Help menu label.
        menubar.Append(help_menu, _("&Help"))

        self.SetMenuBar(menubar)

    def _create_controls(self) -> None:
        """Create the window controls."""
        self._panel = wx.Panel(self)

        # Section selector (tab order: 1)
        self._section_label = wx.StaticText(
            self._panel,
            # Translators: Label for the section selector.
            label=_("&Section:"),
        )
        self._section_choice = wx.Choice(
            self._panel,
            choices=_section_display_names(),
            # Translators: Accessible name for section selector.
            name=_("Section"),
        )
        self._section_choice.SetSelection(0)

        # Search box (tab order: 2)
        self._search_label = wx.StaticText(
            self._panel,
            # Translators: Label for the search field.
            label=_("S&earch:"),
        )
        self._search_text = wx.TextCtrl(
            self._panel,
            # Translators: Accessible name for search field.
            name=_("Search"),
            style=wx.TE_PROCESS_ENTER,
        )
        # Translators: Placeholder in the search field.
        self._search_text.SetHint(
            _("Type to filter...")
        )

        # List count label (tab order: 3, before the list)
        self._list_label = wx.StaticText(
            self._panel,
            label=ngettext(
                "{n} track", "{n} tracks", 0,
            ).format(n=0),
        )

        # Library list
        self._list = LibraryListBox(self._panel)

        # Now-playing label
        self._now_playing_label = wx.StaticText(
            self._panel,
            # Translators: Label when nothing is playing.
            label=_("Not playing"),
            # Translators: Accessible name for now-playing.
            name=_("Now playing"),
        )

    def _do_layout(self) -> None:
        """Layout the window controls."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Section row
        sec_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sec_sizer.Add(
            self._section_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        sec_sizer.Add(
            self._section_choice,
            proportion=0,
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        main_sizer.Add(
            sec_sizer,
            flag=wx.EXPAND | wx.ALL,
            border=10,
        )

        # Search row
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_sizer.Add(
            self._search_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        search_sizer.Add(
            self._search_text,
            proportion=1,
            flag=wx.EXPAND,
        )
        main_sizer.Add(
            search_sizer,
            flag=(
                wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM
            ),
            border=10,
        )

        # List label + list
        main_sizer.Add(
            self._list_label,
            flag=wx.LEFT | wx.RIGHT,
            border=10,
        )
        main_sizer.Add(
            self._list,
            proportion=1,
            flag=(
                wx.EXPAND
                | wx.LEFT | wx.RIGHT | wx.BOTTOM
            ),
            border=5,
        )

        # Now playing
        main_sizer.Add(
            self._now_playing_label,
            flag=(
                wx.EXPAND
                | wx.LEFT | wx.RIGHT | wx.BOTTOM
            ),
            border=10,
        )

        self._panel.SetSizer(main_sizer)

    def _bind_events(self) -> None:
        """Bind event handlers."""
        # Menu events
        self.Bind(
            wx.EVT_MENU, self._on_change_server,
            self._menu_change_server,
        )
        self.Bind(
            wx.EVT_MENU, self._on_exit, self._menu_exit,
        )
        self.Bind(
            wx.EVT_MENU, self._on_play, self._menu_play,
        )
        self.Bind(
            wx.EVT_MENU, self._on_pause,
            self._menu_pause,
        )
        self.Bind(
            wx.EVT_MENU, self._on_stop, self._menu_stop,
        )
        self.Bind(
            wx.EVT_MENU, self._on_volume_up,
            self._menu_volume_up,
        )
        self.Bind(
            wx.EVT_MENU, self._on_volume_down,
            self._menu_volume_down,
        )
        self.Bind(
            wx.EVT_MENU, self._on_seek_forward,
            self._menu_seek_fwd,
        )
        self.Bind(
            wx.EVT_MENU, self._on_seek_backward,
            self._menu_seek_bwd,
        )
        self.Bind(
            wx.EVT_MENU, self._on_refresh,
            self._menu_refresh,
        )
        self.Bind(
            wx.EVT_MENU, self._on_shortcuts,
            self._menu_shortcuts,
        )
        self.Bind(
            wx.EVT_MENU, self._on_about,
            self._menu_about,
        )

        # Section selector
        self._section_choice.Bind(
            wx.EVT_CHOICE, self._on_section_change,
        )

        # Search
        self._search_text.Bind(
            wx.EVT_TEXT, self._on_search_input,
        )
        self.Bind(
            wx.EVT_TIMER, self._on_search_timer,
            self._search_timer,
        )

        # List (double-click only; Enter/Backspace via CHAR_HOOK)
        self._list.Bind(
            wx.EVT_LISTBOX_DCLICK, self._on_list_activate,
        )

        # Frame-level key hook — fires before accelerators
        # and before the native control swallows Enter.
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        # Window
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _setup_accelerators(self) -> None:
        """Set up keyboard accelerators."""
        accel = wx.AcceleratorTable([
            (
                wx.ACCEL_NORMAL, wx.WXK_ESCAPE,
                self._menu_pause.GetId(),
            ),
            (
                wx.ACCEL_CTRL, wx.WXK_UP,
                self._menu_volume_up.GetId(),
            ),
            (
                wx.ACCEL_CTRL, wx.WXK_DOWN,
                self._menu_volume_down.GetId(),
            ),
            (
                wx.ACCEL_CTRL, wx.WXK_RIGHT,
                self._menu_seek_fwd.GetId(),
            ),
            (
                wx.ACCEL_CTRL, wx.WXK_LEFT,
                self._menu_seek_bwd.GetId(),
            ),
        ])
        self.SetAcceleratorTable(accel)

    def _setup_player_callbacks(self) -> None:
        """Set up player event callbacks."""
        def on_pos(pos: float) -> None:
            wx.CallAfter(self._update_position, pos)

        def on_dur(dur: float) -> None:
            wx.CallAfter(self._update_duration, dur)

        def on_end() -> None:
            wx.CallAfter(self._on_track_end)

        self._player.set_on_position_change(on_pos)
        self._player.set_on_duration_change(on_dur)
        self._player.set_on_end_file(on_end)

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def _update_status(self, message: str) -> None:
        self.SetStatusText(message, 0)

    def _update_position(self, position: float) -> None:
        dur = format_duration(self._player.duration)
        pos = format_duration(position)
        self.SetStatusText(f"{pos} / {dur}", 1)

    def _update_duration(self, duration: float) -> None:
        pos = format_duration(self._player.position)
        dur = format_duration(duration)
        self.SetStatusText(f"{pos} / {dur}", 1)

    def _update_volume_display(self) -> None:
        # Translators: Volume in status bar.
        self.SetStatusText(
            _("Vol: {volume}%").format(
                volume=self._player.volume,
            ),
            2,
        )

    def _update_title(self) -> None:
        base = "{name} - {ver}".format(
            name=__app_name__, ver=__version__,
        )
        if self._current_track:
            # Translators: Fallback track title.
            title = (
                self._current_track.get("Name")
                or _("Untitled")
            )
            self.SetTitle(f"{title} - {base}")
        else:
            self.SetTitle(base)

    # ------------------------------------------------------------------
    # List label
    # ------------------------------------------------------------------

    def _update_list_label(self) -> None:
        """Update visible label + accessible name."""
        n = len(self._filtered_items)
        label = self._count_label(
            self._current_level_type, n,
            self._context_name,
        )
        self._list_label.SetLabel(label)
        self._list.SetName(label)

    @staticmethod
    def _count_label(
        level_type: str,
        n: int,
        context: str | None = None,
    ) -> str:
        """Build a count string like '5 Albums by X'."""
        if level_type == "tracks":
            if context:
                # Translators: Track count with context.
                # {n} = count, {name} = parent name.
                return ngettext(
                    "{n} track in {name}",
                    "{n} tracks in {name}",
                    n,
                ).format(n=n, name=context)
            # Translators: Track count.
            return ngettext(
                "{n} track", "{n} tracks", n,
            ).format(n=n)

        if level_type == "artists":
            # Translators: Artist count.
            return ngettext(
                "{n} artist", "{n} artists", n,
            ).format(n=n)

        if level_type == "album_artists":
            # Translators: Album artist count.
            return ngettext(
                "{n} album artist",
                "{n} album artists",
                n,
            ).format(n=n)

        if level_type == "albums":
            if context:
                # Translators: Album count with context.
                return ngettext(
                    "{n} album by {name}",
                    "{n} albums by {name}",
                    n,
                ).format(n=n, name=context)
            # Translators: Album count.
            return ngettext(
                "{n} album", "{n} albums", n,
            ).format(n=n)

        if level_type == "playlists":
            # Translators: Playlist count.
            return ngettext(
                "{n} playlist", "{n} playlists", n,
            ).format(n=n)

        return str(n)

    # ------------------------------------------------------------------
    # Library data loading
    # ------------------------------------------------------------------

    def load_library(self) -> None:
        """Load library: show cache, then refresh in background."""
        server = self._db.get_active_server()
        if not server or not server.id:
            # Translators: No server configured.
            self._update_status(
                _("Not connected to server")
            )
            return

        # Load cached data into memory
        self._load_library_from_db(server.id)
        had_cache = bool(self._lib_tracks)

        # Display current section from cache
        self._switch_to_section(
            self._section_choice.GetSelection(),
        )

        if had_cache:
            # Translators: Showing cached library.
            self._update_status(
                _("Library loaded from cache, updating...")
            )
        else:
            # Translators: First time loading.
            self._update_status(
                _("Loading library from server...")
            )

        # Background refresh
        def on_loaded(tracks, playlists, pl_items):
            wx.CallAfter(
                self._on_library_loaded,
                tracks, playlists, pl_items,
            )

        def on_error(e):
            # Translators: Background refresh error.
            msg = _("Error refreshing: {error}").format(
                error=e,
            )
            wx.CallAfter(self._update_status, msg)

        self._client.get_library_async(
            on_loaded, on_error,
        )

    def _load_library_from_db(self, server_id: int) -> None:
        """Populate in-memory lists from the DB cache."""
        self._lib_tracks = (
            self._db.get_all_tracks(server_id)
        )
        self._lib_artists = (
            self._db.get_all_artists(server_id)
        )
        self._lib_album_artists = (
            self._db.get_all_album_artists(server_id)
        )
        self._lib_albums = (
            self._db.get_all_albums(server_id)
        )
        self._lib_playlists = (
            self._db.get_all_playlists(server_id)
        )

    def _on_library_loaded(
        self,
        tracks: list[dict],
        playlists: list[dict],
        playlist_items: dict[str, list[dict]],
    ) -> None:
        """Handle fresh library data from the server."""
        server = self._db.get_active_server()
        if not server or not server.id:
            return

        self._db.cache_library(server.id, tracks)
        self._db.cache_playlists(
            server.id, playlists, playlist_items,
        )
        self._load_library_from_db(server.id)

        # If at top level, refresh the display
        if not self._nav_stack:
            self._switch_to_section(
                self._section_choice.GetSelection(),
            )

        # Translators: Library updated status.
        self._update_status(_("Library updated"))

    # ------------------------------------------------------------------
    # Section / navigation
    # ------------------------------------------------------------------

    def _items_for_section(self, idx: int) -> list[dict]:
        """Return top-level items for the given section."""
        section = SECTIONS[idx]
        if section == "tracks":
            return self._lib_tracks
        if section == "playlists":
            return self._lib_playlists
        if section == "artists":
            return self._lib_artists
        if section == "album_artists":
            return self._lib_album_artists
        if section == "albums":
            return self._lib_albums
        return []

    def _switch_to_section(self, idx: int) -> None:
        """Reset navigation and display a top-level section."""
        self._nav_stack.clear()
        self._search_text.ChangeValue("")

        section = SECTIONS[idx]
        items = self._items_for_section(idx)

        self._display_level(items, section, None)

    def _display_level(
        self,
        items: list[dict],
        level_type: str,
        context_name: str | None,
    ) -> None:
        """Show *items* in the list with the right formatter."""
        self._all_items = items
        self._current_level_type = level_type
        self._context_name = context_name

        fmt = FORMATTERS.get(level_type, FORMATTERS["tracks"])
        self._list.set_formatter(fmt)

        self._apply_filter(self._search_text.GetValue())

    def _apply_filter(self, query: str) -> None:
        """Filter current items and refresh the list."""
        if not query:
            self._filtered_items = self._all_items
        else:
            q = query.lower()
            lt = self._current_level_type
            self._filtered_items = [
                i for i in self._all_items
                if self._matches(i, q, lt)
            ]

        self._list.set_items(self._filtered_items)
        self._update_list_label()

    @staticmethod
    def _matches(
        item: dict, q: str, level_type: str,
    ) -> bool:
        """Check if *item* matches the search query."""
        if level_type in ("artists", "album_artists"):
            return q in item.get("Name", "").lower()
        if level_type == "playlists":
            return q in item.get("Name", "").lower()
        if level_type == "albums":
            return (
                q in item.get("Name", "").lower()
                or q in item.get(
                    "ArtistDisplay", "",
                ).lower()
            )
        # tracks
        return (
            q in item.get("Name", "").lower()
            or q in item.get(
                "ArtistDisplay", "",
            ).lower()
            or q in item.get(
                "AlbumArtist", "",
            ).lower()
        )

    # --- Drill down / go back ---

    def _drill_down(self, item: dict) -> None:
        """Enter a sub-level for the selected item."""
        lt = self._current_level_type
        server = self._db.get_active_server()
        if not server or not server.id:
            return

        item_id = item.get("Id", "")
        item_name = item.get("Name", "")

        new_items: list[dict] | None = None
        new_type: str = ""
        new_ctx: str | None = None

        if lt == "artists":
            new_items = self._db.get_albums_by_artist(
                server.id, item_id,
            )
            new_type = "albums"
            new_ctx = item_name
        elif lt == "album_artists":
            new_items = (
                self._db.get_albums_by_album_artist(
                    server.id, item_id,
                )
            )
            new_type = "albums"
            new_ctx = item_name
        elif lt == "albums":
            new_items = self._db.get_tracks_by_album(
                server.id, item_id,
            )
            new_type = "tracks"
            new_ctx = item_name
        elif lt == "playlists":
            new_items = self._db.get_playlist_tracks(
                server.id, item_id,
            )
            new_type = "tracks"
            new_ctx = item_name

        if new_items is None:
            return

        # Push current state
        self._nav_stack.append(_NavState(
            all_items=self._all_items,
            level_type=self._current_level_type,
            context_name=self._context_name,
            selected_id=item_id,
        ))

        self._search_text.ChangeValue("")
        self._display_level(new_items, new_type, new_ctx)

    def _go_back(self) -> None:
        """Return to the previous navigation level."""
        if not self._nav_stack:
            return

        state = self._nav_stack.pop()
        self._search_text.ChangeValue("")
        self._display_level(
            state.all_items,
            state.level_type,
            state.context_name,
        )

        # Restore focus to the item we came from
        if state.selected_id:
            self._list.set_selection_by_id(
                state.selected_id,
            )

    # ------------------------------------------------------------------
    # Search debounce
    # ------------------------------------------------------------------

    def _on_search_input(self, event: wx.CommandEvent):
        self._search_timer.Stop()
        self._search_timer.StartOnce(
            self._SEARCH_DELAY_MS,
        )

    def _on_search_timer(self, event: wx.TimerEvent):
        query = self._search_text.GetValue()
        self._apply_filter(query)

    # ------------------------------------------------------------------
    # Section change
    # ------------------------------------------------------------------

    def _on_section_change(self, event: wx.CommandEvent):
        idx = self._section_choice.GetSelection()
        self._switch_to_section(idx)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def _play_track(self, track: dict) -> None:
        """Play a track."""
        track_id = track.get("Id") or track.get("id")
        if not track_id:
            return

        url = self._client.get_stream_url(track_id)
        if not url:
            return

        self._current_track = track
        self._player.play(url)

        # Translators: Fallback when a track has no title.
        title = track.get("Name") or _("Untitled")
        artist = (
            track.get("ArtistDisplay")
            or track.get("AlbumArtist")
            or ""
        )
        if artist:
            # Translators: Now-playing with artist.
            np = _(
                "Now playing: {title} - {artist}"
            ).format(title=title, artist=artist)
        else:
            # Translators: Now-playing without artist.
            np = _(
                "Now playing: {title}"
            ).format(title=title)
        self._now_playing_label.SetLabel(np)
        # Translators: Status bar when playing.
        self._update_status(
            _("Playing: {title}").format(title=title)
        )
        self._update_volume_display()
        self._update_title()

    def _on_track_end(self) -> None:
        """Handle track end (with race-condition guard)."""
        if self._player.is_loaded:
            return

        self._current_track = None
        # Translators: Not playing label.
        self._now_playing_label.SetLabel(
            _("Not playing")
        )
        # Translators: Playback finished status.
        self._update_status(_("Playback finished"))
        self._update_title()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        """Handle Enter/Backspace when the list is focused.

        EVT_CHAR_HOOK fires before accelerators and before
        the native LISTBOX control swallows the key.
        """
        code = event.GetKeyCode()
        focused = self.FindFocus()

        if focused is self._list:
            if code in (
                wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER,
            ):
                item = self._list.get_selected_item()
                if item:
                    if (
                        self._current_level_type
                        == "tracks"
                    ):
                        self._play_track(item)
                    else:
                        self._drill_down(item)
                return
            if code == wx.WXK_BACK:
                if self._nav_stack:
                    self._go_back()
                    return

        event.Skip()

    def _on_list_activate(self, event: wx.CommandEvent):
        item = self._list.get_selected_item()
        if not item:
            return
        if self._current_level_type == "tracks":
            self._play_track(item)
        else:
            self._drill_down(item)

    def _on_play(self, event: wx.CommandEvent):
        item = self._list.get_selected_item()
        if item and self._current_level_type == "tracks":
            self._play_track(item)
        elif (
            self._current_track
            and not self._player.is_playing
        ):
            self._player.resume()

    def _on_pause(self, event: wx.CommandEvent):
        self._player.toggle_pause()
        if self._player.is_playing:
            # Translators: Playing status.
            self._update_status(_("Playing"))
        else:
            # Translators: Paused status.
            self._update_status(_("Paused"))

    def _on_stop(self, event: wx.CommandEvent):
        self._player.stop()
        self._current_track = None
        # Translators: Not playing label.
        self._now_playing_label.SetLabel(
            _("Not playing")
        )
        # Translators: Stopped status.
        self._update_status(_("Stopped"))
        self._update_title()

    def _on_volume_up(self, event: wx.CommandEvent):
        self._player.volume_up()
        self._update_volume_display()

    def _on_volume_down(self, event: wx.CommandEvent):
        self._player.volume_down()
        self._update_volume_display()

    def _on_seek_forward(self, event: wx.CommandEvent):
        self._player.seek(10)

    def _on_seek_backward(self, event: wx.CommandEvent):
        self._player.seek(-10)

    def _on_refresh(self, event: wx.CommandEvent):
        self.load_library()

    def _on_change_server(self, event: wx.CommandEvent):
        wx.PostEvent(
            self,
            wx.PyCommandEvent(
                wx.EVT_MENU.typeId, wx.ID_NEW,
            ),
        )

    def _on_shortcuts(self, event: wx.CommandEvent):
        # Translators: Keyboard shortcuts help text.
        shortcuts = _(
            "Keyboard Shortcuts:\n\n"
            "Navigation:\n"
            "  Tab          - Move between controls\n"
            "  Up/Down      - Navigate items\n"
            "  Enter        - Play track / open item\n"
            "  Backspace    - Go back one level\n\n"
            "Playback:\n"
            "  Escape       - Pause/Resume\n"
            "  Ctrl+S       - Stop\n"
            "  Ctrl+Up      - Volume up\n"
            "  Ctrl+Down    - Volume down\n"
            "  Ctrl+Right   - Seek forward 10s\n"
            "  Ctrl+Left    - Seek backward 10s\n\n"
            "Other:\n"
            "  F5           - Refresh library\n"
            "  F1           - Show this help\n"
            "  Alt+F4       - Exit"
        )
        wx.MessageBox(
            shortcuts,
            # Translators: Shortcuts dialog title.
            _("Keyboard Shortcuts"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _on_about(self, event: wx.CommandEvent):
        wx.MessageBox(
            # Translators: About dialog text.
            _(
                "{app_name} v{version}\n\n"
                "An accessible Jellyfin music client."
                "\n\n"
                "Designed for keyboard and "
                "screen reader users."
            ).format(
                app_name=__app_name__,
                version=__version__,
            ),
            # Translators: About dialog title.
            _("About {app_name}").format(
                app_name=__app_name__,
            ),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _on_exit(self, event: wx.CommandEvent):
        self.Close()

    def _on_close(self, event: wx.CloseEvent):
        self._search_timer.Stop()
        self._player.shutdown()
        self._client.shutdown()
        event.Skip()

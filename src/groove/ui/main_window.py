"""Main application window for Groove."""

import wx

from groove import __app_name__, __version__
from groove.api import JellyfinClient
from groove.db import Database
from groove.i18n import _, ngettext
from groove.player import Player
from groove.player.mpv_player import format_duration


def _format_track_label(track: dict) -> str:
    """Format a track dict into a single display string.

    Format: "Artist — Title  Duration"
    (or "Title  Duration" if no artist).
    """
    artist = track.get("AlbumArtist", "")
    # Translators: Fallback track title shown when the track has no name.
    name = track.get("Name", _("Unknown"))
    ticks = track.get("RunTimeTicks", 0)
    dur = format_duration(ticks / 10_000_000) if ticks else ""

    if artist:
        # Translators: Track display format: {artist} is the artist name,
        # {title} is the track title, {duration} is the track length.
        return _("{artist} \u2014 {title}  {duration}").format(
            artist=artist, title=name, duration=dur,
        )
    # Translators: Track display format when no artist is available.
    # {title} is the track title, {duration} is the track length.
    return _("{title}  {duration}").format(title=name, duration=dur)


class TrackListBox(wx.ListBox):
    """Single-column list of tracks using native wx.ListBox.

    Uses a native Win32 LISTBOX control, which screen readers
    (NVDA, JAWS) handle perfectly without any custom IAccessible.
    Each item is a pre-formatted string; a parallel list of dicts
    provides the data for playback and filtering.
    """

    def __init__(self, parent: wx.Window):
        super().__init__(
            parent,
            style=wx.LB_SINGLE,
            # Translators: Accessible name for the track list control.
            name=_("Track list"),
        )
        self._items: list[dict] = []

    def set_tracks(self, tracks: list[dict]) -> None:
        """Replace all items, preserving focus by track Id."""
        old_focused_id = self._get_focused_track_id()
        had_items = len(self._items) > 0

        self._items = tracks

        # Batch update with Freeze/Thaw to suppress repaints
        self.Freeze()
        self.Clear()
        if tracks:
            self.Set([_format_track_label(t) for t in tracks])
        self.Thaw()

        # Restore or set selection
        if old_focused_id and tracks:
            new_index = self._find_track_index(old_focused_id)
            if new_index is not None:
                self.SetSelection(new_index)
            else:
                # Item gone — nearest valid index
                self.SetSelection(min(
                    max(self.GetSelection(), 0),
                    len(tracks) - 1,
                ))
        elif not had_items and tracks:
            self.SetSelection(0)

    def _get_focused_track_id(self) -> str | None:
        """Return the Id of the currently selected track."""
        idx = self.GetSelection()
        if idx != wx.NOT_FOUND and idx < len(self._items):
            return self._items[idx].get("Id")
        return None

    def _find_track_index(self, track_id: str) -> int | None:
        """Find the index of a track by its Jellyfin Id."""
        for i, t in enumerate(self._items):
            if t.get("Id") == track_id:
                return i
        return None

    def get_track(self, index: int) -> dict | None:
        """Get the track dict at the given index."""
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def get_selected_track(self) -> dict | None:
        """Get the currently selected track dict."""
        return self.get_track(self.GetSelection())


class MainWindow(wx.Frame):
    """Main application window with track list and playback controls."""

    # Debounce delay for search input (milliseconds)
    _SEARCH_DELAY_MS = 50

    def __init__(
        self,
        db: Database,
        client: JellyfinClient,
        player: Player,
    ):
        super().__init__(
            None,
            title="{app_name} - {version}".format(
                app_name=__app_name__, version=__version__,
            ),
            size=(800, 600),
        )

        self._db = db
        self._client = client
        self._player = player

        # Track data
        self._tracks: list[dict] = []
        self._filtered_tracks: list[dict] = []
        self._current_track: dict | None = None

        # Search debounce timer
        self._search_timer = wx.Timer(self)

        # Create UI
        self._create_menu_bar()
        self._create_controls()
        self._do_layout()
        self._bind_events()
        self._setup_player_callbacks()
        self._setup_accelerators()

        # Status bar
        self.CreateStatusBar(3)
        self.SetStatusWidths([-2, 150, 100])
        # Translators: Initial status bar message when the application is ready.
        self._update_status(_("Ready"))

        self.CenterOnScreen()

    def _create_menu_bar(self) -> None:
        """Create the application menu bar."""
        menubar = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        self._menu_change_server = file_menu.Append(
            wx.ID_ANY,
            # Translators: File menu item to connect to a different Jellyfin server.
            # The ampersand indicates the keyboard mnemonic. \t separates the accelerator key.
            _("Change &Server...\tCtrl+Shift+S"),
            # Translators: Help text for the Change Server menu item.
            _("Connect to a different server"),
        )
        file_menu.AppendSeparator()
        self._menu_exit = file_menu.Append(
            wx.ID_EXIT,
            # Translators: File menu item to exit the application.
            _("E&xit\tAlt+F4"),
            # Translators: Help text for the Exit menu item.
            _("Exit the application"),
        )
        # Translators: Label for the File menu in the menu bar.
        menubar.Append(file_menu, _("&File"))

        # Playback menu
        playback_menu = wx.Menu()
        self._menu_play = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Playback menu item to play the selected track.
            _("&Play\tEnter"),
            # Translators: Help text for the Play menu item.
            _("Play selected track"),
        )
        self._menu_pause = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Playback menu item to pause or resume playback.
            _("P&ause/Resume\tEscape"),
            # Translators: Help text for the Pause/Resume menu item.
            _("Pause or resume playback"),
        )
        self._menu_stop = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Playback menu item to stop playback.
            _("&Stop\tCtrl+S"),
            # Translators: Help text for the Stop menu item.
            _("Stop playback"),
        )
        playback_menu.AppendSeparator()
        self._menu_volume_up = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Playback menu item to increase volume.
            _("Volume &Up\tCtrl+Up"),
            # Translators: Help text for the Volume Up menu item.
            _("Increase volume"),
        )
        self._menu_volume_down = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Playback menu item to decrease volume.
            _("Volume &Down\tCtrl+Down"),
            # Translators: Help text for the Volume Down menu item.
            _("Decrease volume"),
        )
        playback_menu.AppendSeparator()
        self._menu_seek_forward = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Playback menu item to seek forward.
            _("Seek &Forward\tCtrl+Right"),
            # Translators: Help text for the Seek Forward menu item.
            _("Seek forward 10 seconds"),
        )
        self._menu_seek_backward = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Playback menu item to seek backward.
            _("Seek &Backward\tCtrl+Left"),
            # Translators: Help text for the Seek Backward menu item.
            _("Seek backward 10 seconds"),
        )
        # Translators: Label for the Playback menu in the menu bar.
        menubar.Append(playback_menu, _("&Playback"))

        # View menu
        view_menu = wx.Menu()
        self._menu_refresh = view_menu.Append(
            wx.ID_REFRESH,
            # Translators: View menu item to refresh the track library from the server.
            _("&Refresh Library\tF5"),
            # Translators: Help text for the Refresh Library menu item.
            _("Reload tracks from server"),
        )
        # Translators: Label for the View menu in the menu bar.
        menubar.Append(view_menu, _("&View"))

        # Help menu
        help_menu = wx.Menu()
        self._menu_shortcuts = help_menu.Append(
            wx.ID_ANY,
            # Translators: Help menu item to show keyboard shortcuts.
            _("&Keyboard Shortcuts\tF1"),
            # Translators: Help text for the Keyboard Shortcuts menu item.
            _("Show keyboard shortcuts"),
        )
        help_menu.AppendSeparator()
        self._menu_about = help_menu.Append(
            wx.ID_ABOUT,
            # Translators: Help menu item to show the About dialog.
            _("&About"),
            # Translators: Help text for the About menu item.
            _("About Groove"),
        )
        # Translators: Label for the Help menu in the menu bar.
        menubar.Append(help_menu, _("&Help"))

        self.SetMenuBar(menubar)

    def _create_controls(self) -> None:
        """Create the window controls."""
        self._panel = wx.Panel(self)

        # Search box
        self._search_label = wx.StaticText(
            self._panel,
            # Translators: Label for the search input field. The ampersand indicates the keyboard mnemonic.
            label=_("&Search:"),
        )
        self._search_text = wx.TextCtrl(
            self._panel,
            # Translators: Accessible name for the search input field.
            name=_("Search tracks"),
            style=wx.TE_PROCESS_ENTER,
        )
        # Translators: Placeholder hint shown in the search field when it is empty.
        self._search_text.SetHint(_("Type to filter tracks..."))

        # Track list label (shows item count; read by screen reader on Tab)
        self._track_count_label = wx.StaticText(
            self._panel,
            # Translators: Initial track count label shown before tracks are loaded.
            label=ngettext("{n} track", "{n} tracks", 0).format(n=0),
        )

        # Track list (native ListBox for screen reader compatibility)
        self._track_list = TrackListBox(self._panel)

        # Playback info label (for screen readers)
        self._now_playing_label = wx.StaticText(
            self._panel,
            # Translators: Label shown when no track is currently playing.
            label=_("Not playing"),
            # Translators: Accessible name for the now-playing status label.
            name=_("Now playing"),
        )

    def _do_layout(self) -> None:
        """Layout the window controls."""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Search row
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_sizer.Add(
            self._search_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        search_sizer.Add(
            self._search_text, proportion=1, flag=wx.EXPAND
        )

        main_sizer.Add(
            search_sizer, flag=wx.EXPAND | wx.ALL, border=10,
        )

        # Track list label + list
        main_sizer.Add(
            self._track_count_label,
            flag=wx.LEFT | wx.RIGHT,
            border=10,
        )
        main_sizer.Add(
            self._track_list,
            proportion=1,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=5,
        )

        # Now playing info
        main_sizer.Add(
            self._now_playing_label,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
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
        self.Bind(wx.EVT_MENU, self._on_exit, self._menu_exit)
        self.Bind(wx.EVT_MENU, self._on_play, self._menu_play)
        self.Bind(wx.EVT_MENU, self._on_pause, self._menu_pause)
        self.Bind(wx.EVT_MENU, self._on_stop, self._menu_stop)
        self.Bind(
            wx.EVT_MENU, self._on_volume_up, self._menu_volume_up
        )
        self.Bind(
            wx.EVT_MENU, self._on_volume_down, self._menu_volume_down
        )
        self.Bind(
            wx.EVT_MENU, self._on_seek_forward,
            self._menu_seek_forward,
        )
        self.Bind(
            wx.EVT_MENU, self._on_seek_backward,
            self._menu_seek_backward,
        )
        self.Bind(wx.EVT_MENU, self._on_refresh, self._menu_refresh)
        self.Bind(
            wx.EVT_MENU, self._on_shortcuts, self._menu_shortcuts
        )
        self.Bind(wx.EVT_MENU, self._on_about, self._menu_about)

        # Control events
        self._search_text.Bind(wx.EVT_TEXT, self._on_search_input)
        self._track_list.Bind(
            wx.EVT_LISTBOX_DCLICK, self._on_track_activate
        )
        self._track_list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)

        # Search debounce timer
        self.Bind(
            wx.EVT_TIMER, self._on_search_timer, self._search_timer
        )

        # Window events
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _setup_accelerators(self) -> None:
        """Set up keyboard accelerators."""
        accel_table = wx.AcceleratorTable([
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
                self._menu_seek_forward.GetId(),
            ),
            (
                wx.ACCEL_CTRL, wx.WXK_LEFT,
                self._menu_seek_backward.GetId(),
            ),
        ])
        self.SetAcceleratorTable(accel_table)

    def _setup_player_callbacks(self) -> None:
        """Set up player event callbacks."""
        def on_position(pos: float) -> None:
            wx.CallAfter(self._update_position, pos)

        def on_duration(dur: float) -> None:
            wx.CallAfter(self._update_duration, dur)

        def on_end() -> None:
            wx.CallAfter(self._on_track_end)

        self._player.set_on_position_change(on_position)
        self._player.set_on_duration_change(on_duration)
        self._player.set_on_end_file(on_end)

    def _update_status(self, message: str) -> None:
        """Update the status bar message."""
        self.SetStatusText(message, 0)

    def _update_position(self, position: float) -> None:
        """Update position display."""
        dur_str = format_duration(self._player.duration)
        pos_str = format_duration(position)
        self.SetStatusText(f"{pos_str} / {dur_str}", 1)

    def _update_duration(self, duration: float) -> None:
        """Update duration display."""
        pos_str = format_duration(self._player.position)
        dur_str = format_duration(duration)
        self.SetStatusText(f"{pos_str} / {dur_str}", 1)

    def _update_volume_display(self) -> None:
        """Update volume display."""
        # Translators: Volume level shown in the status bar. {volume} is the percentage.
        self.SetStatusText(
            _("Vol: {volume}%").format(volume=self._player.volume), 2,
        )

    # --- Track loading ---

    def load_tracks(self) -> None:
        """Load tracks: show cache immediately, refresh from server."""
        server = self._db.get_active_server()
        if not server or not server.id:
            # Translators: Status message when no server connection is configured.
            self._update_status(_("Not connected to server"))
            return

        # 1. Instantly show whatever is in the local cache
        cached = self._db.get_all_tracks(server.id)
        if cached:
            self._set_tracks(cached)
            # Translators: Status message when showing cached tracks while updating from server.
            # {n} is the number of cached tracks.
            self._update_status(ngettext(
                "{n} track (from cache, updating...)",
                "{n} tracks (from cache, updating...)",
                len(cached),
            ).format(n=len(cached)))
        else:
            # Translators: Status message when loading tracks from server for the first time.
            self._update_status(_("Loading tracks from server..."))

        # 2. Fetch fresh data from server in background
        def on_tracks_loaded(tracks: list[dict]) -> None:
            wx.CallAfter(self._on_server_tracks_loaded, tracks)

        def on_error(e: Exception) -> None:
            if cached:
                # Translators: Status bar error when background refresh fails.
                # {error} is the error description.
                msg = _("Error refreshing: {error}").format(error=e)
            else:
                # Translators: Status bar error when initial track loading fails.
                # {error} is the error description.
                msg = _("Error loading tracks: {error}").format(error=e)
            wx.CallAfter(self._update_status, msg)

        self._client.get_all_tracks_async(on_tracks_loaded, on_error)

    def _on_server_tracks_loaded(self, tracks: list[dict]) -> None:
        """Handle fresh tracks from server."""
        # Cache for next startup
        server = self._db.get_active_server()
        if server and server.id:
            self._db.cache_tracks(server.id, tracks)

        self._set_tracks(tracks)
        # Translators: Status message showing total number of tracks after loading.
        # {n} is the number of tracks.
        self._update_status(
            ngettext("{n} track", "{n} tracks", len(tracks)).format(
                n=len(tracks),
            )
        )

    def _set_tracks(self, tracks: list[dict]) -> None:
        """Set the full track list and apply current filter."""
        self._tracks = tracks
        # Re-apply current search filter
        query = self._search_text.GetValue()
        self._apply_filter(query)

    def _apply_filter(self, query: str) -> None:
        """Filter tracks and push results to the list."""
        if not query:
            self._filtered_tracks = self._tracks
        else:
            q = query.lower()
            self._filtered_tracks = [
                t for t in self._tracks
                if q in t.get("Name", "").lower()
                or q in t.get("Album", "").lower()
                or q in t.get("AlbumArtist", "").lower()
            ]

        self._track_list.set_tracks(self._filtered_tracks)
        self._update_track_count()

    def _update_track_count(self) -> None:
        """Update the track list label and accessible name."""
        n = len(self._filtered_tracks)
        # Translators: Track count label shown above the track list and used
        # as the accessible name. {n} is the number of tracks.
        label = ngettext("{n} track", "{n} tracks", n).format(n=n)
        self._track_count_label.SetLabel(label)
        self._track_list.SetName(label)

    # --- Search debounce ---

    def _on_search_input(self, event: wx.CommandEvent) -> None:
        """Restart debounce timer on every keystroke."""
        self._search_timer.Stop()
        self._search_timer.StartOnce(self._SEARCH_DELAY_MS)

    def _on_search_timer(self, event: wx.TimerEvent) -> None:
        """Timer fired - now actually apply the filter."""
        query = self._search_text.GetValue()
        self._apply_filter(query)
        n = len(self._filtered_tracks)
        total = len(self._tracks)
        if query:
            # Translators: Status message when search filter is active.
            # {n} is the number of matching tracks, {total} is the total number of tracks.
            self._update_status(
                ngettext(
                    "Found {n} of {total} track",
                    "Found {n} of {total} tracks",
                    total,
                ).format(n=n, total=total)
            )
        else:
            # Translators: Status message showing total tracks when no search filter is active.
            # {n} is the number of tracks.
            self._update_status(
                ngettext("{n} track", "{n} tracks", total).format(n=total)
            )

    # --- Playback ---

    def _update_title(self) -> None:
        """Set the window title from the current playback state.

        Format:  Track - AppName - Version   (when a track is active)
                 AppName - Version            (when idle)
        """
        base = "{app_name} - {version}".format(
            app_name=__app_name__, version=__version__,
        )
        if self._current_track:
            title = self._current_track.get(
                # Translators: Fallback track title used when the track has no name.
                "Name", self._current_track.get("name", _("Unknown"))
            )
            self.SetTitle(f"{title} - {base}")
        else:
            self.SetTitle(base)

    def _play_track(self, track: dict) -> None:
        """Play a track."""
        track_id = track.get("Id") or track.get("id")
        if not track_id:
            return

        url = self._client.get_stream_url(track_id)
        if url:
            self._current_track = track
            self._player.play(url)

            # Translators: Fallback track title used in playback display.
            title = track.get("Name", track.get("name", _("Unknown")))
            artist = track.get(
                "AlbumArtist",
                # Translators: Fallback artist name when the track has no artist.
                track.get("artist_name", _("Unknown Artist")),
            )
            # Translators: Now-playing label shown below the track list.
            # {title} is the track title, {artist} is the artist name.
            self._now_playing_label.SetLabel(
                _("Now playing: {title} - {artist}").format(
                    title=title, artist=artist,
                )
            )
            # Translators: Status bar message when a track starts playing.
            # {title} is the track title.
            self._update_status(
                _("Playing: {title}").format(title=title)
            )
            self._update_volume_display()
            self._update_title()

    def _on_track_end(self) -> None:
        """Handle track end.

        MPV fires end-file both when a track finishes naturally AND
        when it is interrupted by play() loading a new file.  In the
        latter case the new track is already loaded by the time this
        callback arrives via wx.CallAfter, so we must check whether
        the player is still active before clearing the UI.
        """
        if self._player.is_loaded:
            return

        self._current_track = None
        # Translators: Label shown when no track is currently playing.
        self._now_playing_label.SetLabel(_("Not playing"))
        # Translators: Status message after a track finishes playing.
        self._update_status(_("Playback finished"))
        self._update_title()

    # --- Event handlers ---

    def _on_list_key(self, event: wx.KeyEvent) -> None:
        """Handle Enter key on the track list."""
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            track = self._track_list.get_selected_track()
            if track:
                self._play_track(track)
        else:
            event.Skip()

    def _on_track_activate(self, event: wx.CommandEvent) -> None:
        """Handle track double-click."""
        track = self._track_list.get_selected_track()
        if track:
            self._play_track(track)

    def _on_play(self, event: wx.CommandEvent) -> None:
        """Handle play command."""
        track = self._track_list.get_selected_track()
        if track:
            self._play_track(track)
        elif self._current_track and not self._player.is_playing:
            self._player.resume()

    def _on_pause(self, event: wx.CommandEvent) -> None:
        """Handle pause/resume command."""
        self._player.toggle_pause()
        if self._player.is_playing:
            # Translators: Status bar message when playback is active.
            self._update_status(_("Playing"))
        else:
            # Translators: Status bar message when playback is paused.
            self._update_status(_("Paused"))

    def _on_stop(self, event: wx.CommandEvent) -> None:
        """Handle stop command."""
        self._player.stop()
        self._current_track = None
        # Translators: Label shown when no track is currently playing.
        self._now_playing_label.SetLabel(_("Not playing"))
        # Translators: Status bar message when playback is stopped.
        self._update_status(_("Stopped"))
        self._update_title()

    def _on_volume_up(self, event: wx.CommandEvent) -> None:
        self._player.volume_up()
        self._update_volume_display()

    def _on_volume_down(self, event: wx.CommandEvent) -> None:
        self._player.volume_down()
        self._update_volume_display()

    def _on_seek_forward(self, event: wx.CommandEvent) -> None:
        self._player.seek(10)

    def _on_seek_backward(self, event: wx.CommandEvent) -> None:
        self._player.seek(-10)

    def _on_refresh(self, event: wx.CommandEvent) -> None:
        self.load_tracks()

    def _on_change_server(self, event: wx.CommandEvent) -> None:
        wx.PostEvent(
            self, wx.PyCommandEvent(wx.EVT_MENU.typeId, wx.ID_NEW)
        )

    def _on_shortcuts(self, event: wx.CommandEvent) -> None:
        """Show keyboard shortcuts dialog."""
        # Translators: Full text of the keyboard shortcuts help dialog.
        # Key names (Tab, Enter, Escape, Ctrl, etc.) should not be translated.
        shortcuts = _(
            "Keyboard Shortcuts:\n\n"
            "Navigation:\n"
            "  Tab          - Move between search and track list\n"
            "  Up/Down      - Navigate tracks\n"
            "  Enter        - Play selected track\n\n"
            "Playback:\n"
            "  Escape       - Pause/Resume\n"
            "  Ctrl+S       - Stop\n"
            "  Ctrl+Up      - Volume up\n"
            "  Ctrl+Down    - Volume down\n"
            "  Ctrl+Right   - Seek forward 10 seconds\n"
            "  Ctrl+Left    - Seek backward 10 seconds\n\n"
            "Other:\n"
            "  F5           - Refresh library\n"
            "  F1           - Show this help\n"
            "  Alt+F4       - Exit"
        )
        wx.MessageBox(
            shortcuts,
            # Translators: Title of the keyboard shortcuts dialog.
            _("Keyboard Shortcuts"),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _on_about(self, event: wx.CommandEvent) -> None:
        wx.MessageBox(
            # Translators: About dialog text. {app_name} is the application name,
            # {version} is the version number.
            _("{app_name} v{version}\n\n"
              "An accessible Jellyfin music client.\n\n"
              "Designed for keyboard and screen reader users.").format(
                app_name=__app_name__, version=__version__,
            ),
            # Translators: Title of the About dialog. {app_name} is the application name.
            _("About {app_name}").format(app_name=__app_name__),
            wx.OK | wx.ICON_INFORMATION,
            self,
        )

    def _on_exit(self, event: wx.CommandEvent) -> None:
        self.Close()

    def _on_close(self, event: wx.CloseEvent) -> None:
        self._search_timer.Stop()
        self._player.shutdown()
        self._client.shutdown()
        event.Skip()

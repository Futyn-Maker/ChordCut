"""Main application window for ChordCut."""

import random
import subprocess
from dataclasses import dataclass

import wx
import wx.adv

from chordcut import __app_name__, __version__
from chordcut.api import JellyfinClient
from chordcut.db import Database, ServerCredentials
from chordcut.i18n import _, ngettext
from chordcut.player import Player
from chordcut.player.mpv_player import format_duration
from chordcut.settings import Settings
from chordcut.ui.library_list import (
    FORMATTERS,
    LibraryListBox,
)
from chordcut.ui.tray_icon import TrayIcon
from chordcut.utils.text import normalize_search

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


@dataclass
class _QueueOrigin:
    """Remembers where a playback queue was created."""

    section_idx: int
    nav_depth: int
    level_type: str
    context_name: str | None


class MainWindow(wx.Frame):
    """Main window with library navigation and playback."""

    _SEARCH_DELAY_MS = 50

    def __init__(
        self,
        db: Database,
        client: JellyfinClient,
        player: Player,
        settings: Settings,
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
        self._settings = settings

        # Current playback
        self._current_track: dict | None = None

        # Playback queue
        self._queue: list[dict] = []
        self._queue_index: int = -1
        self._queue_origin: _QueueOrigin | None = None
        self._original_queue: list[dict] = []

        # Playback modes
        self._shuffle_enabled: bool = False
        self._repeat_enabled: bool = False

        # Lyrics cache: track_id -> dict | "none"
        self._lyrics_cache: dict[str, dict | str] = {}
        # True while synced lyrics dialog is open
        self._synced_lyrics_active: bool = False

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

        # Active server (set in load_library, cleared on switch)
        self._current_server: ServerCredentials | None = None
        # Server ID that initiated the current background load;
        # callbacks check against this to ignore stale results.
        self._load_server_id: int | None = None

        # Music libraries (for filtering)
        self._libraries: list[dict] = []
        self._selected_library_ids: set[str] | None = None
        self._library_menu_ids: dict[int, str] = {}
        # Server submenu: menu_item_id → server_id
        self._server_menu_items: dict[int, int] = {}

        # Progressive loading state
        self._initial_loading: bool = False
        self._loading_in_progress: bool = False
        self._lib_track_counts: dict[str, int] = {}
        self._lib_loaded_counts: dict[str, int] = {}

        # List shuffle state (not persisted)
        self._list_shuffle_active: bool = False
        # Original (pre-shuffle) items for the current level
        self._pre_shuffle_items: list[dict] = []

        # Search debounce timer
        self._search_timer = wx.Timer(self)

        # Sleep timer
        self._countdown_seconds: int = 0
        self._timer_action: str = ""
        self._countdown_timer = wx.Timer(self)

        # Focus tracking for window activation
        self._last_focused_window: wx.Window | None = None

        # When True, _on_close always exits (bypass close_to_tray).
        self._force_closing: bool = False

        # Build UI
        self._create_menu_bar()
        self._create_controls()
        self._do_layout()
        self._bind_events()
        self._setup_player_callbacks()
        self._setup_accelerators()

        # Status bar
        self.CreateStatusBar(4)
        self.SetStatusWidths([-2, 150, 100, 130])
        # Translators: Initial status bar message.
        self._update_status(_("Ready"))

        # Restore saved volume and audio device
        self._apply_startup_settings()

        # Window icon (title bar + taskbar)
        from chordcut.utils.paths import get_icon_path
        _ico_path = get_icon_path()
        if _ico_path:
            self.SetIcon(
                wx.Icon(str(_ico_path), wx.BITMAP_TYPE_ICO)
            )

        # System tray icon (always visible)
        self._tray_icon: TrayIcon | None = TrayIcon(self)

        self.CenterOnScreen()

    # ------------------------------------------------------------------
    # UI creation
    # ------------------------------------------------------------------

    def _create_menu_bar(self) -> None:
        """Create the application menu bar."""
        menubar = wx.MenuBar()

        # File menu
        file_menu = wx.Menu()
        self._menu_new_playlist = file_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item to create playlist.
            _("&New Playlist...\tCtrl+N"),
            # Translators: Help text for New Playlist.
            _("Create a new playlist"),
        )
        file_menu.AppendSeparator()
        self._servers_submenu = wx.Menu()
        self._servers_submenu_item = file_menu.AppendSubMenu(
            self._servers_submenu,
            # Translators: Submenu label for switching servers.
            _("Change &Server"),
        )
        file_menu.AppendSeparator()
        self._menu_settings = file_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item to open settings.
            _("Se&ttings...\tF8"),
            # Translators: Help text for Settings.
            _("Configure application settings"),
        )
        file_menu.AppendSeparator()
        self._menu_timer = file_menu.AppendCheckItem(
            wx.ID_ANY,
            # Translators: Menu item to set up (or cancel) the sleep timer.
            _("Sleep &Timer..."),
            # Translators: Help text for Sleep Timer.
            _("Set a timer to close or shut down after a delay"),
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
            _("&Stop\tCtrl+Alt+Q"),
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
        playback_menu.AppendSeparator()
        self._menu_next = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item for next track.
            _("&Next Track\tShift+Right"),
            # Translators: Help text for Next Track.
            _("Play next track in queue"),
        )
        self._menu_prev = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item for previous track.
            _("Pre&vious Track\tShift+Left"),
            # Translators: Help text for Previous Track.
            _("Play previous track in queue"),
        )
        self._menu_restart = playback_menu.Append(
            wx.ID_ANY,
            # Translators: Menu item to restart current track.
            _("R&estart Track\tCtrl+Alt+X"),
            # Translators: Help text for Restart Track.
            _("Replay current track from beginning"),
        )
        playback_menu.AppendSeparator()
        self._menu_repeat = playback_menu.AppendCheckItem(
            wx.ID_ANY,
            # Translators: Menu item for repeat mode.
            _("&Repeat\tCtrl+Alt+R"),
            # Translators: Help text for Repeat.
            _("Toggle repeat mode"),
        )
        self._menu_shuffle = playback_menu.AppendCheckItem(
            wx.ID_ANY,
            # Translators: Menu item for shuffle mode.
            _("S&huffle\tCtrl+Alt+S"),
            # Translators: Help text for Shuffle.
            _("Toggle shuffle mode"),
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
        view_menu.AppendSeparator()
        self._sort_menu = wx.Menu()
        self._sort_menu_ids: dict[int, str] = {}
        sort_items = [
            # Translators: Sort option: alphabetical A-Z.
            ("alpha_asc", _("Alphabetical A\u2013Z")),
            # Translators: Sort option: alphabetical Z-A.
            ("alpha_desc", _("Alphabetical Z\u2013A")),
            # Translators: Sort option: newest first.
            ("date_desc",
             _("By date added (newest first)")),
            # Translators: Sort option: oldest first.
            ("date_asc",
             _("By date added (oldest first)")),
        ]
        current_sort = self._settings.track_sort
        for sort_key, label in sort_items:
            item = self._sort_menu.AppendRadioItem(
                wx.ID_ANY, label,
            )
            self._sort_menu_ids[item.GetId()] = sort_key
            if sort_key == current_sort:
                item.Check(True)
            self.Bind(
                wx.EVT_MENU,
                self._on_sort_change,
                item,
            )
        view_menu.AppendSubMenu(
            self._sort_menu,
            # Translators: Sorting submenu label.
            _("&Sorting"),
        )
        self._menu_list_shuffle = view_menu.AppendCheckItem(
            wx.ID_ANY,
            # Translators: Menu item to shuffle the
            # currently visible list.
            _("&Shuffle List"),
            # Translators: Help text for Shuffle List.
            _("Shuffle the visible list order"),
        )
        self.Bind(
            wx.EVT_MENU,
            self._on_list_shuffle_toggle,
            self._menu_list_shuffle,
        )
        view_menu.AppendSeparator()
        self._libraries_menu = wx.Menu()
        view_menu.AppendSubMenu(
            self._libraries_menu,
            # Translators: Libraries submenu label.
            _("&Libraries"),
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
            _("About ChordCut"),
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

        # Audio device selector (tab order: last)
        self._device_label = wx.StaticText(
            self._panel,
            # Translators: Label for audio device selector.
            label=_("&Output device:"),
        )
        self._device_choice = wx.Choice(
            self._panel,
            # Translators: Accessible name for device selector.
            name=_("Output device"),
        )
        self._device_names: list[str] = []
        self._populate_audio_devices()

        # Album art (hidden until a track with art plays)
        self._ART_SIZE = 60
        self._art_bitmap = wx.StaticBitmap(
            self._panel,
            size=(self._ART_SIZE, self._ART_SIZE),
        )
        self._art_bitmap.Hide()
        # Track which image request is current so stale
        # callbacks don't overwrite a newer image.
        self._art_request_id: str = ""

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
        self._search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._search_sizer.Add(
            self._search_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        self._search_sizer.Add(
            self._search_text,
            proportion=1,
            flag=wx.EXPAND,
        )
        main_sizer.Add(
            self._search_sizer,
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

        # Audio device row
        dev_sizer = wx.BoxSizer(wx.HORIZONTAL)
        dev_sizer.Add(
            self._device_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        dev_sizer.Add(
            self._device_choice,
            proportion=0,
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        main_sizer.Add(
            dev_sizer,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT,
            border=10,
        )

        # Now playing row (album art + label)
        self._np_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._np_sizer.Add(
            self._art_bitmap,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=8,
        )
        self._np_sizer.Add(
            self._now_playing_label,
            proportion=1,
            flag=wx.ALIGN_CENTER_VERTICAL,
        )
        main_sizer.Add(
            self._np_sizer,
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
            wx.EVT_MENU, self._on_new_playlist,
            self._menu_new_playlist,
        )
        self.Bind(
            wx.EVT_MENU, self._on_settings,
            self._menu_settings,
        )
        self.Bind(
            wx.EVT_MENU, self._on_timer_menu,
            self._menu_timer,
        )
        self.Bind(
            wx.EVT_TIMER, self._on_countdown_tick,
            self._countdown_timer,
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
        self.Bind(
            wx.EVT_MENU, self._on_next_track,
            self._menu_next,
        )
        self.Bind(
            wx.EVT_MENU, self._on_prev_track,
            self._menu_prev,
        )
        self.Bind(
            wx.EVT_MENU, self._on_restart_track,
            self._menu_restart,
        )
        self.Bind(
            wx.EVT_MENU, self._on_toggle_repeat,
            self._menu_repeat,
        )
        self.Bind(
            wx.EVT_MENU, self._on_toggle_shuffle,
            self._menu_shuffle,
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

        # Audio device selector
        self._device_choice.Bind(
            wx.EVT_CHOICE, self._on_device_change,
        )

        # List (double-click only; Enter/Backspace via CHAR_HOOK)
        self._list.Bind(
            wx.EVT_LISTBOX_DCLICK, self._on_list_activate,
        )
        self._list.Bind(
            wx.EVT_CONTEXT_MENU, self._on_context_menu,
        )

        # Frame-level key hook — fires before accelerators
        # and before the native control swallows Enter.
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        # Window
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_ACTIVATE, self._on_activate)

    def _setup_accelerators(self) -> None:
        """Set up keyboard accelerators."""
        # IDs for accelerator-only actions (no menu item)
        self._id_properties = wx.NewIdRef()
        self._id_copy_link = wx.NewIdRef()
        self._id_copy_stream = wx.NewIdRef()
        self._id_download = wx.NewIdRef()

        self.Bind(
            wx.EVT_MENU, self._on_properties_accel,
            id=self._id_properties,
        )
        self.Bind(
            wx.EVT_MENU, self._on_copy_link_accel,
            id=self._id_copy_link,
        )
        self.Bind(
            wx.EVT_MENU, self._on_copy_stream_accel,
            id=self._id_copy_stream,
        )
        self.Bind(
            wx.EVT_MENU, self._on_download_accel,
            id=self._id_download,
        )

        accel = wx.AcceleratorTable([
            (
                wx.ACCEL_NORMAL, wx.WXK_F8,
                self._menu_settings.GetId(),
            ),
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
            # Shift+Left/Right handled in _on_char_hook
            # to avoid conflict with search box selection
            (
                wx.ACCEL_CTRL | wx.ACCEL_ALT, ord("X"),
                self._menu_restart.GetId(),
            ),
            (
                wx.ACCEL_CTRL | wx.ACCEL_ALT, ord("R"),
                self._menu_repeat.GetId(),
            ),
            (
                wx.ACCEL_CTRL | wx.ACCEL_ALT, ord("S"),
                self._menu_shuffle.GetId(),
            ),
            (
                wx.ACCEL_ALT, wx.WXK_RETURN,
                self._id_properties,
            ),
            # Ctrl+C for copy link handled in _on_char_hook
            (
                wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("C"),
                self._id_copy_stream,
            ),
            (
                wx.ACCEL_CTRL | wx.ACCEL_SHIFT,
                wx.WXK_RETURN,
                self._id_download,
            ),
            (
                wx.ACCEL_CTRL, ord("N"),
                self._menu_new_playlist.GetId(),
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

    def _apply_startup_settings(self) -> None:
        """Restore saved volume and audio device from settings."""
        if self._settings.remember_volume:
            self._player.volume = self._settings.volume
        else:
            self._player.volume = 80
        self._update_volume_display()

        if self._settings.remember_device:
            saved = self._settings.device
            if saved and saved != "auto":
                self._player.set_audio_device(saved)
                try:
                    idx = self._device_names.index(saved)
                    self._device_choice.SetSelection(idx)
                except ValueError:
                    # Device no longer available; stay on default.
                    pass

    # ------------------------------------------------------------------
    # Tray icon helpers
    # ------------------------------------------------------------------

    def _minimize_to_tray(self) -> None:
        """Hide the main window, leaving the tray icon visible."""
        self.Hide()

    def _restore_from_tray(self) -> None:
        """Show and raise the main window."""
        self.Show()
        self.Restore()
        self.Raise()

    def _force_close(self) -> None:
        """Close the application from the tray icon context menu."""
        self._force_closing = True
        if self._tray_icon:
            self._tray_icon.RemoveIcon()
            self._tray_icon.Destroy()
            self._tray_icon = None
        self.Close()

    # ------------------------------------------------------------------
    # Settings dialog
    # ------------------------------------------------------------------

    def _on_settings(
        self, _event: wx.CommandEvent,
    ) -> None:
        """Open the settings dialog."""
        from chordcut.ui.dialogs.settings_dialog import (
            SettingsDialog,
        )
        dlg = SettingsDialog(self, self._settings)
        dlg.ShowModal()
        dlg.Destroy()

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
        if self._tray_icon:
            self._tray_icon.update_tooltip(
                self._current_track,
            )

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
        """Load library: show cache, then refresh."""
        server_id = self._settings.active_server_id
        server = (
            self._db.get_server(server_id)
            if server_id is not None
            else None
        )
        if not server or not server.id:
            # Translators: No server configured.
            self._update_status(
                _("Not connected to server")
            )
            return

        if self._loading_in_progress:
            return
        self._loading_in_progress = True

        self._current_server = server
        self._load_server_id = server.id

        # Rebuild the servers submenu to reflect all saved servers
        self._rebuild_servers_menu()

        # Decide warm vs cold based on whether the last load
        # completed fully.  Each library stores how many tracks
        # the server reported; if the DB total matches the sum
        # of those expected counts the cache is complete.
        libraries = self._db.get_libraries(server.id)
        total_expected = sum(
            lib.get("ExpectedTrackCount", 0)
            for lib in libraries
        )
        total_cached = self._db.count_tracks(server.id)

        if total_expected > 0 and total_cached >= total_expected:
            # Cache is complete — show it instantly, then refresh.
            self._load_library_from_db(server.id)
            self._start_warm_load(server)
        else:
            # No cache or interrupted load — fetch from scratch.
            self._start_cold_load(server)

    # --- Warm load (has cache) ---

    def _start_warm_load(self, server) -> None:
        """Show cache instantly, refresh in background."""
        self._switch_to_section(
            self._section_choice.GetSelection(),
        )
        # Translators: Showing cached library.
        self._update_status(
            _("Library loaded from cache, updating...")
        )

        sid = server.id

        def on_loaded(
            libraries, tracks, playlists, pl_items,
        ):
            def run():
                if self._load_server_id == sid:
                    self._on_library_loaded(
                        libraries, tracks,
                        playlists, pl_items,
                    )
            wx.CallAfter(run)

        def on_error(e):
            # Translators: Background refresh error.
            msg = _("Error refreshing: {error}").format(
                error=e,
            )
            def run():
                if self._load_server_id == sid:
                    self._update_status(msg)
                    self._finish_loading()
            wx.CallAfter(run)

        self._client.get_library_async(
            on_loaded, on_error,
        )

    # --- Cold load (first launch / empty cache) ---

    def _start_cold_load(self, server) -> None:
        """Progressive loading with per-page UI updates."""
        self._initial_loading = True
        self._loaded_tracks = 0
        self._total_tracks = 0

        # Hide search (not usable until fully loaded)
        self._search_sizer.ShowItems(False)
        self._panel.Layout()

        # Show empty state
        self._switch_to_section(
            self._section_choice.GetSelection(),
        )
        # Translators: First time loading.
        self._update_status(
            _("Loading library from server...")
        )

        sid = server.id

        def on_libs(libraries, lib_counts):
            def run():
                if self._load_server_id == sid:
                    self._on_libraries_ready(
                        libraries, lib_counts,
                    )
            wx.CallAfter(run)

        def on_page(batch, lib_id, count):
            def run():
                if self._load_server_id == sid:
                    self._on_page_loaded(
                        batch, lib_id, count,
                    )
            wx.CallAfter(run)

        def on_done(playlists, pl_items):
            def run():
                if self._load_server_id == sid:
                    self._on_initial_load_done(
                        playlists, pl_items,
                    )
            wx.CallAfter(run)

        def on_error(e):
            # Translators: Cold load error.
            msg = _("Error loading: {error}").format(
                error=e,
            )
            def run():
                if self._load_server_id == sid:
                    self._update_status(msg)
                    self._finish_cold_load()
                    self._finish_loading()
            wx.CallAfter(run)

        self._client.fetch_library_paginated(
            on_libs, on_page, on_done, on_error,
        )

    def _on_libraries_ready(
        self,
        libraries: list[dict],
        lib_counts: dict[str, int],
    ) -> None:
        """Handle music views + per-library track counts."""
        server = self._current_server
        if not server or not server.id:
            return

        self._lib_track_counts = dict(lib_counts)
        self._lib_loaded_counts = {
            lid: 0 for lid in lib_counts
        }

        if libraries:
            self._db.cache_libraries(
                server.id, libraries,
            )
            # Store the expected count per library so we can
            # detect an interrupted load on the next startup.
            self._db.set_libraries_expected_counts(
                server.id, lib_counts,
            )
            db_libs = self._db.get_libraries(server.id)
            self._selected_library_ids = {
                lib["Id"] for lib in db_libs
                if lib.get("Enabled", True)
            }
            self._libraries = db_libs
            self._rebuild_libraries_menu()

        # Clear old track/artist/album data
        self._db.clear_library_cache(server.id)

        # Reload (now empty) in-memory lists
        self._load_library_from_db(server.id)
        self._update_loading_label()

    def _on_page_loaded(
        self,
        batch: list[dict],
        library_id: str,
        count: int,
    ) -> None:
        """Handle a page of tracks from the server."""
        server = self._current_server
        if not server or not server.id:
            return

        # Update per-library loaded count
        self._lib_loaded_counts[library_id] = (
            self._lib_loaded_counts.get(library_id, 0)
            + count
        )

        # Write batch to DB
        self._db.cache_library_batch(server.id, batch)

        # Refresh in-memory lists from DB
        self._load_library_from_db(server.id)

        # Refresh current view
        self._refresh_current_view(server.id)
        self._update_loading_label()

        # Check if visible libraries are fully loaded
        if self._visible_tracks_complete():
            self._finish_cold_load()

        loaded = sum(self._lib_loaded_counts.values())
        total = sum(self._lib_track_counts.values())
        # Translators: Cold load progress in status bar.
        self._update_status(
            _("Loading: {loaded} of {total} tracks"
              ).format(loaded=loaded, total=total),
        )

    def _on_initial_load_done(
        self,
        playlists: list[dict],
        playlist_items: dict[str, list[dict]],
    ) -> None:
        """Handle completion of progressive loading."""
        server = self._current_server
        if not server or not server.id:
            self._finish_cold_load()
            return

        self._db.cache_playlists(
            server.id, playlists, playlist_items,
        )
        self._load_library_from_db(server.id)

        # Cold load may have already finished early
        # (all visible libraries loaded), but we still
        # need to ensure it's finished now.
        if self._initial_loading:
            self._finish_cold_load()

        self._loading_in_progress = False
        self._refresh_current_view(server.id)
        # Translators: Library updated status.
        self._update_status(_("Library updated"))

    def _finish_cold_load(self) -> None:
        """End progressive loading: show search, etc.

        Note: *_loading_in_progress* is NOT cleared here
        because hidden libraries may still be fetching.
        It is cleared in *_on_initial_load_done* or on
        error.
        """
        if not self._initial_loading:
            return
        self._initial_loading = False

        # Show search field
        self._search_sizer.ShowItems(True)
        self._panel.Layout()

        # Reset label to normal format
        self._update_list_label()

    def _finish_loading(self) -> None:
        """Clear the loading-in-progress guard."""
        self._loading_in_progress = False

    def _visible_loading_counts(
        self,
    ) -> tuple[int, int]:
        """Return (loaded, total) for enabled libraries."""
        ids = self._selected_library_ids
        if ids is None:
            ids = set(self._lib_track_counts)
        loaded = sum(
            self._lib_loaded_counts.get(lid, 0)
            for lid in ids
        )
        total = sum(
            self._lib_track_counts.get(lid, 0)
            for lid in ids
        )
        return loaded, total

    def _visible_tracks_complete(self) -> bool:
        """True when all enabled libraries are loaded."""
        if not self._initial_loading:
            return True
        loaded, total = self._visible_loading_counts()
        return loaded >= total

    def _update_loading_label(self) -> None:
        """Update label during cold load to show progress."""
        if not self._initial_loading:
            self._update_list_label()
            return

        idx = self._section_choice.GetSelection()
        section = SECTIONS[idx]

        if section == "tracks" and not self._nav_stack:
            loaded, total = (
                self._visible_loading_counts()
            )
            # Translators: Loading progress label.
            # {loaded} = tracks loaded so far,
            # {total} = total tracks on server.
            label = _(
                "{loaded} of {total} tracks"
            ).format(loaded=loaded, total=total)
            self._list_label.SetLabel(label)
            self._list.SetName(label)
        else:
            self._update_list_label()

    def _load_library_from_db(self, server_id: int) -> None:
        """Populate in-memory lists from the DB cache."""
        # Load libraries if not yet loaded
        if not self._libraries:
            self._libraries = (
                self._db.get_libraries(server_id)
            )
            if self._libraries:
                # Restore persisted enabled/disabled state
                self._selected_library_ids = {
                    lib["Id"] for lib in self._libraries
                    if lib.get("Enabled", True)
                }
                self._rebuild_libraries_menu()

        lib_ids = self._selected_library_ids
        self._lib_tracks = self._db.get_all_tracks(
            server_id, lib_ids,
            sort=self._settings.track_sort,
        )
        self._lib_artists = (
            self._db.get_all_artists(server_id, lib_ids)
        )
        self._lib_album_artists = (
            self._db.get_all_album_artists(
                server_id, lib_ids,
            )
        )
        self._lib_albums = (
            self._db.get_all_albums(server_id, lib_ids)
        )
        self._lib_playlists = (
            self._db.get_all_playlists(server_id)
        )

    def _on_library_loaded(
        self,
        libraries: list[dict],
        tracks: list[dict],
        playlists: list[dict],
        playlist_items: dict[str, list[dict]],
    ) -> None:
        """Handle fresh library data from the server."""
        server = self._current_server
        if not server or not server.id:
            return

        # Cache libraries and rebuild menu
        if libraries:
            self._db.cache_libraries(
                server.id, libraries,
            )
            # Read back from DB: cache_libraries preserves
            # existing enabled states; new libs default to 1.
            db_libs = self._db.get_libraries(server.id)
            self._selected_library_ids = {
                lib["Id"] for lib in db_libs
                if lib.get("Enabled", True)
            }
            self._libraries = db_libs
            self._rebuild_libraries_menu()

        self._db.cache_library(server.id, tracks)
        self._db.cache_playlists(
            server.id, playlists, playlist_items,
        )

        # Update per-library expected counts from the actual
        # track data so future startups choose warm load.
        lib_counts: dict[str, int] = {}
        for track in tracks:
            lid = track.get("LibraryId", "") or ""
            if lid:
                lib_counts[lid] = (
                    lib_counts.get(lid, 0) + 1
                )
        if lib_counts:
            self._db.set_libraries_expected_counts(
                server.id, lib_counts,
            )

        self._load_library_from_db(server.id)
        self._refresh_current_view(server.id)
        self._update_queue_after_refresh()
        self._finish_loading()

        # Translators: Library updated status.
        self._update_status(_("Library updated"))

    def _refresh_current_view(
        self, server_id: int,
    ) -> None:
        """Re-query and refresh all navigation levels.

        Preserves search text, focus position, and nav stack.
        Updates stale nav stack entries so that going back
        also shows fresh data.
        """
        lib_ids = self._selected_library_ids

        if not self._nav_stack:
            # Top level: refresh without clearing search
            idx = (
                self._section_choice.GetSelection()
            )
            section = SECTIONS[idx]
            items = self._items_for_section(idx)
            self._display_level(
                items, section, None,
            )
            return

        # Refresh every nav stack entry bottom-up,
        # checking that each drilled-into item still exists.
        for i, state in enumerate(self._nav_stack):
            if i == 0:
                # Bottom of stack: top-level section
                idx = (
                    self._section_choice.GetSelection()
                )
                state.all_items = (
                    self._items_for_section(idx)
                )
            else:
                prev = self._nav_stack[i - 1]
                state.all_items = self._query_sub_items(
                    server_id,
                    prev.level_type,
                    prev.selected_id,
                    lib_ids,
                )

            # If the parent item we drilled into is gone,
            # the navigation path is broken — reset.
            if state.selected_id and not any(
                it.get("Id") == state.selected_id
                for it in state.all_items
            ):
                self._nav_stack.clear()
                self._search_text.ChangeValue("")
                idx = (
                    self._section_choice.GetSelection()
                )
                section = SECTIONS[idx]
                items = self._items_for_section(idx)
                self._display_level(
                    items, section, None,
                )
                return

        # All ancestors valid — refresh current level
        parent = self._nav_stack[-1]
        items = self._query_sub_items(
            server_id,
            parent.level_type,
            parent.selected_id,
            lib_ids,
        )
        self._display_level(
            items,
            self._current_level_type,
            self._context_name,
        )

    def _query_sub_items(
        self,
        server_id: int,
        parent_type: str,
        parent_id: str | None,
        library_ids: set[str] | None,
    ) -> list[dict]:
        """Query sub-items for a given parent level."""
        if not parent_id:
            return []
        if parent_type == "artists":
            return self._db.get_albums_by_artist(
                server_id, parent_id, library_ids,
            )
        if parent_type == "album_artists":
            return self._db.get_albums_by_album_artist(
                server_id, parent_id, library_ids,
            )
        if parent_type == "albums":
            return self._db.get_tracks_by_album(
                server_id, parent_id, library_ids,
            )
        if parent_type == "playlists":
            return self._db.get_playlist_tracks(
                server_id, parent_id,
            )
        return []

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
        self._deactivate_list_shuffle()
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
        """Show *items* in the list with the right formatter.

        If list shuffle is active (e.g. after a library
        refresh), a new shuffle is applied to the fresh
        items.  Navigation events deactivate shuffle via
        ``_deactivate_list_shuffle()`` before calling here.
        """
        self._pre_shuffle_items = items
        if self._list_shuffle_active:
            shuffled = list(items)
            random.shuffle(shuffled)
            self._all_items = shuffled
        else:
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
            q = normalize_search(query)
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
        """Check if *item* matches the search query.

        *q* must already be normalized via :func:`normalize_search`.
        """
        n = normalize_search
        if level_type in ("artists", "album_artists"):
            return q in n(item.get("Name", ""))
        if level_type == "playlists":
            return q in n(item.get("Name", ""))
        if level_type == "albums":
            return (
                q in n(item.get("Name", ""))
                or q in n(item.get("ArtistDisplay", ""))
            )
        # tracks
        return (
            q in n(item.get("Name", ""))
            or q in n(item.get("ArtistDisplay", ""))
            or q in n(item.get("AlbumArtist", ""))
        )

    # --- Drill down / go back ---

    def _drill_down(self, item: dict) -> None:
        """Enter a sub-level for the selected item."""
        lt = self._current_level_type
        server = self._current_server
        if not server or not server.id:
            return

        item_id = item.get("Id", "")
        item_name = item.get("Name", "")

        new_items: list[dict] | None = None
        new_type: str = ""
        new_ctx: str | None = None

        lib_ids = self._selected_library_ids

        if lt == "artists":
            new_items = self._db.get_albums_by_artist(
                server.id, item_id, lib_ids,
            )
            new_type = "albums"
            new_ctx = item_name
        elif lt == "album_artists":
            new_items = (
                self._db.get_albums_by_album_artist(
                    server.id, item_id, lib_ids,
                )
            )
            new_type = "albums"
            new_ctx = item_name
        elif lt == "albums":
            new_items = self._db.get_tracks_by_album(
                server.id, item_id, lib_ids,
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

        # Deactivate shuffle before navigating
        self._deactivate_list_shuffle()

        # Push current state (unshuffled original so
        # going back always restores canonical order)
        self._nav_stack.append(_NavState(
            all_items=self._pre_shuffle_items,
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

        self._deactivate_list_shuffle()
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
    # Sorting
    # ------------------------------------------------------------------

    def _on_sort_change(
        self, event: wx.CommandEvent,
    ) -> None:
        """Handle a sort radio-item selection."""
        sort_key = self._sort_menu_ids.get(
            event.GetId(),
        )
        if not sort_key:
            return

        self._settings.track_sort = sort_key
        self._settings.save()

        server = self._current_server
        if not server or not server.id:
            return

        lib_ids = self._selected_library_ids
        self._lib_tracks = self._db.get_all_tracks(
            server.id, lib_ids,
            sort=self._settings.track_sort,
        )

        # Refresh display if viewing top-level Tracks
        idx = self._section_choice.GetSelection()
        if (
            SECTIONS[idx] == "tracks"
            and not self._nav_stack
        ):
            self._display_level(
                self._lib_tracks, "tracks", None,
            )

    def _deactivate_list_shuffle(self) -> None:
        """Uncheck and deactivate list shuffle silently.

        Does NOT restore ``_all_items`` — the caller is
        expected to follow up with a ``_display_level``
        call that will provide fresh items.
        """
        if not self._list_shuffle_active:
            return
        self._list_shuffle_active = False
        self._menu_list_shuffle.Check(False)

    def _on_list_shuffle_toggle(
        self, event: wx.CommandEvent,
    ) -> None:
        """Toggle random shuffle of the visible list."""
        if event.IsChecked():
            self._list_shuffle_active = True
            shuffled = list(self._pre_shuffle_items)
            random.shuffle(shuffled)
            self._all_items = shuffled
        else:
            self._list_shuffle_active = False
            self._all_items = self._pre_shuffle_items
        self._apply_filter(
            self._search_text.GetValue(),
        )

    # ------------------------------------------------------------------
    # Library selection
    # ------------------------------------------------------------------

    def _rebuild_libraries_menu(self) -> None:
        """Rebuild the Libraries submenu from current data."""
        # Remove old items and unbind events
        for item in list(
            self._libraries_menu.GetMenuItems()
        ):
            self.Unbind(
                wx.EVT_MENU, id=item.GetId(),
            )
            self._libraries_menu.Delete(item)
        self._library_menu_ids.clear()

        for lib in self._libraries:
            lib_id = lib["Id"]
            item = self._libraries_menu.AppendCheckItem(
                wx.ID_ANY, lib.get("Name", lib_id),
            )
            if (
                self._selected_library_ids is not None
                and lib_id in self._selected_library_ids
            ):
                item.Check(True)
            self._library_menu_ids[item.GetId()] = lib_id
            self.Bind(
                wx.EVT_MENU,
                self._on_library_toggle,
                item,
            )

    def _on_library_toggle(
        self, event: wx.CommandEvent,
    ) -> None:
        """Handle a library check/uncheck toggle."""
        lib_id = self._library_menu_ids.get(
            event.GetId(),
        )
        if not lib_id or self._selected_library_ids is None:
            return

        item = self._libraries_menu.FindItemById(
            event.GetId(),
        )
        if item and item.IsChecked():
            self._selected_library_ids.add(lib_id)
        else:
            self._selected_library_ids.discard(lib_id)

        # Persist the new state and reload
        server = self._current_server
        if not server or not server.id:
            return

        self._db.set_library_enabled(
            server.id,
            lib_id,
            lib_id in self._selected_library_ids,
        )
        self._load_library_from_db(server.id)

        if self._initial_loading:
            self._refresh_current_view(server.id)
            self._update_loading_label()
            if self._visible_tracks_complete():
                self._finish_cold_load()
        else:
            self._refresh_current_view(server.id)
            self._update_queue_after_refresh()

    # ------------------------------------------------------------------
    # Audio device selection
    # ------------------------------------------------------------------

    def _populate_audio_devices(self) -> None:
        """Fill the device selector with available devices."""
        devices = self._player.get_audio_devices()

        choices: list[str] = []
        self._device_names = []

        # First item: Default (with name of first device)
        if devices:
            default_desc = devices[0].get(
                "description", "",
            )
            # Translators: Default audio device with name.
            choices.append(
                _("Default ({name})").format(
                    name=default_desc,
                )
            )
        else:
            # Translators: Default audio device.
            choices.append(_("Default"))
        self._device_names.append("auto")

        # All available devices
        for dev in devices:
            desc = dev.get("description", "")
            name = dev.get("name", "")
            choices.append(desc or name)
            self._device_names.append(name)

        # Last item: no device (mute)
        # Translators: No audio device (mute output).
        choices.append(_("No device"))
        self._device_names.append("null")

        self._device_choice.Set(choices)
        self._device_choice.SetSelection(0)

    def _on_device_change(
        self, event: wx.CommandEvent,
    ) -> None:
        """Handle audio device selection change."""
        idx = self._device_choice.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        if idx < len(self._device_names):
            device_name = self._device_names[idx]
            self._player.set_audio_device(device_name)

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

    def _play_track_from_list(
        self, track: dict,
    ) -> None:
        """User pressed Enter/dbl-click: build queue and play."""
        if self._initial_loading:
            # During cold load: play without queue
            self._play_track(track)
            return

        self._queue = list(self._filtered_items)
        self._original_queue = list(
            self._filtered_items,
        )

        track_id = track.get("Id")
        self._queue_index = next(
            (
                i for i, t in enumerate(self._queue)
                if t.get("Id") == track_id
            ),
            0,
        )

        self._queue_origin = _QueueOrigin(
            section_idx=(
                self._section_choice.GetSelection()
            ),
            nav_depth=len(self._nav_stack),
            level_type=self._current_level_type,
            context_name=self._context_name,
        )

        if self._shuffle_enabled:
            self._shuffle_queue_around_current()

        self._play_track(track)

    def _play_track(self, track: dict) -> None:
        """Play a track (internal, no queue creation)."""
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
        self._update_album_art(track)

    # ------------------------------------------------------------------
    # Album art
    # ------------------------------------------------------------------

    def _update_album_art(self, track: dict) -> None:
        """Fetch and display album art for the given track."""
        # Try the track's own image first, then its album
        track_id = track.get("Id", "")
        album_id = track.get("AlbumId", "")
        request_id = track_id
        self._art_request_id = request_id

        def _on_image(data: bytes | None) -> None:
            # Try album image if the track itself had none
            if data is None and album_id:
                self._client.fetch_image_async(
                    album_id,
                    lambda d: wx.CallAfter(
                        self._apply_album_art, d, request_id,
                    ),
                    max_size=self._ART_SIZE * 2,
                )
            else:
                wx.CallAfter(
                    self._apply_album_art, data, request_id,
                )

        self._client.fetch_image_async(
            track_id, _on_image,
            max_size=self._ART_SIZE * 2,
        )

    def _apply_album_art(
        self, data: bytes | None, request_id: str,
    ) -> None:
        """Apply fetched image data to the art bitmap."""
        if self._art_request_id != request_id:
            return  # stale callback
        if data is None:
            self._clear_album_art()
            return
        try:
            import io
            stream = io.BytesIO(data)
            img = wx.Image(stream, wx.BITMAP_TYPE_ANY)
            if not img.IsOk():
                self._clear_album_art()
                return
            img = img.Scale(
                self._ART_SIZE, self._ART_SIZE,
                wx.IMAGE_QUALITY_BICUBIC,
            )
            self._art_bitmap.SetBitmap(
                wx.Bitmap(img)
            )
            if not self._art_bitmap.IsShown():
                self._art_bitmap.Show()
                self._np_sizer.Layout()
        except Exception:
            self._clear_album_art()

    def _clear_album_art(self) -> None:
        """Hide the album art bitmap."""
        self._art_request_id = ""
        if self._art_bitmap.IsShown():
            self._art_bitmap.Hide()
            self._np_sizer.Layout()

    def _on_track_end(self) -> None:
        """Handle track end: repeat, advance queue, or stop."""
        if self._player.is_loaded:
            return

        # Synced lyrics open: reload same track paused
        if (
            self._synced_lyrics_active
            and self._current_track
        ):
            tid = self._current_track.get("Id")
            if tid:
                url = self._client.get_stream_url(tid)
                if url:
                    self._player.play(url)
                    self._player.pause()
                    return

        if self._repeat_enabled and self._current_track:
            tid = self._current_track.get("Id")
            if tid:
                url = self._client.get_stream_url(tid)
                if url:
                    self._player.play(url)
                    return

        if (
            self._queue
            and self._queue_index < len(self._queue) - 1
        ):
            self._queue_index += 1
            next_track = self._queue[self._queue_index]
            self._play_track(next_track)
            self._auto_focus_queue_track(next_track)
            return

        self._clear_queue()
        self._current_track = None
        self._clear_album_art()
        # Translators: Not playing label.
        self._now_playing_label.SetLabel(
            _("Not playing")
        )
        # Translators: Playback finished status.
        self._update_status(_("Playback finished"))
        self._update_title()

    # ------------------------------------------------------------------
    # Queue helpers
    # ------------------------------------------------------------------

    def _clear_queue(self) -> None:
        """Reset playback queue state."""
        self._queue.clear()
        self._original_queue.clear()
        self._queue_index = -1
        self._queue_origin = None

    def _auto_focus_queue_track(
        self, track: dict,
    ) -> None:
        """Focus playing track if in the queue origin."""
        origin = self._queue_origin
        if not origin:
            return

        cur_section = (
            self._section_choice.GetSelection()
        )
        cur_depth = len(self._nav_stack)

        if (
            cur_section == origin.section_idx
            and cur_depth == origin.nav_depth
            and self._current_level_type
            == origin.level_type
            and self._context_name
            == origin.context_name
        ):
            track_id = track.get("Id")
            if track_id:
                self._list.set_selection_by_id(track_id)

    def _update_queue_after_refresh(self) -> None:
        """Prune queue after library refresh."""
        if not self._queue:
            return

        valid_ids = {
            t.get("Id") for t in self._lib_tracks
        }

        current_id = None
        if 0 <= self._queue_index < len(self._queue):
            current_id = self._queue[
                self._queue_index
            ].get("Id")

        self._queue = [
            t for t in self._queue
            if t.get("Id") in valid_ids
        ]
        self._original_queue = [
            t for t in self._original_queue
            if t.get("Id") in valid_ids
        ]

        if not self._queue:
            self._clear_queue()
            return

        if current_id:
            new_idx = next(
                (
                    i for i, t in enumerate(self._queue)
                    if t.get("Id") == current_id
                ),
                None,
            )
            if new_idx is not None:
                self._queue_index = new_idx
            else:
                self._queue_index = min(
                    self._queue_index,
                    len(self._queue) - 1,
                )

    def _shuffle_queue_around_current(self) -> None:
        """Shuffle queue keeping current track in place."""
        if not self._queue or self._queue_index < 0:
            return
        after = self._queue[self._queue_index + 1:]
        random.shuffle(after)
        self._queue = (
            self._queue[: self._queue_index + 1] + after
        )

    def _unshuffle_queue(self) -> None:
        """Restore original queue order."""
        if not self._original_queue:
            return
        current_id = None
        if 0 <= self._queue_index < len(self._queue):
            current_id = self._queue[
                self._queue_index
            ].get("Id")
        self._queue = list(self._original_queue)
        if current_id:
            self._queue_index = next(
                (
                    i for i, t in enumerate(self._queue)
                    if t.get("Id") == current_id
                ),
                0,
            )

    # ------------------------------------------------------------------
    # Toggle notifications
    # ------------------------------------------------------------------

    def _notify_toggle(self, message: str) -> None:
        """Show accessible notification for toggles."""
        self._update_status(message)
        try:
            notif = wx.adv.NotificationMessage(
                __app_name__, message,
            )
            notif.Show(
                timeout=(
                    wx.adv.NotificationMessage.Timeout_Auto
                ),
            )
        except Exception:
            pass

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

        # Shift+Escape: minimize to system tray
        if (
            code == wx.WXK_ESCAPE
            and event.ShiftDown()
            and not event.ControlDown()
            and not event.AltDown()
        ):
            self._minimize_to_tray()
            return

        if focused is self._list:
            if code in (
                wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER,
            ) and not event.AltDown():
                item = self._list.get_selected_item()
                if item:
                    if (
                        self._current_level_type
                        == "tracks"
                    ):
                        self._play_track_from_list(item)
                    else:
                        self._drill_down(item)
                return
            if code == wx.WXK_BACK:
                if self._nav_stack:
                    self._go_back()
                    return
            # Delete: remove from playlist / delete playlist
            if code == wx.WXK_DELETE:
                if self._current_playlist_id():
                    item = (
                        self._list.get_selected_item()
                    )
                    if item:
                        self._remove_from_playlist(item)
                    return
                if (
                    self._current_level_type
                    == "playlists"
                ):
                    item = (
                        self._list.get_selected_item()
                    )
                    if item:
                        self._delete_playlist(item)
                    return
            # F2: rename playlist
            if code == wx.WXK_F2:
                if (
                    self._current_level_type
                    == "playlists"
                ):
                    item = (
                        self._list.get_selected_item()
                    )
                    if item:
                        self._rename_playlist(item)
                    return
            # Alt+Up/Down: reorder in playlist
            # (blocked while list shuffle is active)
            if (
                event.AltDown()
                and not event.ControlDown()
                and not event.ShiftDown()
            ):
                if code == wx.WXK_UP:
                    if (
                        self._current_playlist_id()
                        and not self._list_shuffle_active
                    ):
                        item = (
                            self._list
                            .get_selected_item()
                        )
                        if item:
                            self._move_playlist_item(
                                item, -1,
                            )
                        return
                elif code == wx.WXK_DOWN:
                    if (
                        self._current_playlist_id()
                        and not self._list_shuffle_active
                    ):
                        item = (
                            self._list
                            .get_selected_item()
                        )
                        if item:
                            self._move_playlist_item(
                                item, 1,
                            )
                        return

        # Shift+Arrow: next/prev track (unless in search)
        if (
            event.ShiftDown()
            and not event.ControlDown()
            and not event.AltDown()
        ):
            if code == wx.WXK_RIGHT:
                if focused is not self._search_text:
                    self._on_next_track(None)
                    return
            elif code == wx.WXK_LEFT:
                if focused is not self._search_text:
                    self._on_prev_track(None)
                    return

        # Ctrl+C: copy link (unless in search box)
        if (
            event.ControlDown()
            and not event.ShiftDown()
            and not event.AltDown()
            and code == ord("C")
            and focused is not self._search_text
        ):
            self._on_copy_link_accel(None)
            return

        event.Skip()

    def _on_list_activate(self, event: wx.CommandEvent):
        item = self._list.get_selected_item()
        if not item:
            return
        if self._current_level_type == "tracks":
            self._play_track_from_list(item)
        else:
            self._drill_down(item)

    def _on_play(self, event: wx.CommandEvent):
        item = self._list.get_selected_item()
        if item and self._current_level_type == "tracks":
            self._play_track_from_list(item)
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
        self._clear_queue()
        self._clear_album_art()
        # Translators: Not playing label.
        self._now_playing_label.SetLabel(
            _("Not playing")
        )
        # Translators: Stopped status.
        self._update_status(_("Stopped"))
        self._update_title()

    def _on_volume_up(self, event: wx.CommandEvent):
        self._player.volume_up(self._settings.volume_step)
        self._update_volume_display()

    def _on_volume_down(self, event: wx.CommandEvent):
        self._player.volume_down(self._settings.volume_step)
        self._update_volume_display()

    def _on_seek_forward(self, event: wx.CommandEvent):
        self._player.seek(self._settings.seek_step)

    def _on_seek_backward(self, event: wx.CommandEvent):
        self._player.seek(-self._settings.seek_step)

    def _on_next_track(self, event: wx.CommandEvent):
        if (
            not self._queue
            or self._queue_index >= len(self._queue) - 1
        ):
            return
        self._queue_index += 1
        track = self._queue[self._queue_index]
        self._play_track(track)
        self._auto_focus_queue_track(track)

    def _on_prev_track(self, event: wx.CommandEvent):
        if not self._queue or self._queue_index <= 0:
            return
        self._queue_index -= 1
        track = self._queue[self._queue_index]
        self._play_track(track)
        self._auto_focus_queue_track(track)

    def _on_restart_track(self, event: wx.CommandEvent):
        if self._current_track:
            self._play_track(self._current_track)

    def _on_toggle_repeat(self, event: wx.CommandEvent):
        self._repeat_enabled = (
            self._menu_repeat.IsChecked()
        )
        if self._repeat_enabled:
            # Translators: Repeat mode on notification.
            self._notify_toggle(_("Repeat on"))
        else:
            # Translators: Repeat mode off notification.
            self._notify_toggle(_("Repeat off"))

    def _on_toggle_shuffle(self, event: wx.CommandEvent):
        self._shuffle_enabled = (
            self._menu_shuffle.IsChecked()
        )
        if self._shuffle_enabled:
            if self._queue:
                self._shuffle_queue_around_current()
            # Translators: Shuffle mode on notification.
            self._notify_toggle(_("Shuffle on"))
        else:
            if self._queue and self._original_queue:
                self._unshuffle_queue()
            # Translators: Shuffle mode off notification.
            self._notify_toggle(_("Shuffle off"))

    def _tray_toggle_repeat(self) -> None:
        """Toggle repeat mode, called from the tray icon menu."""
        self._repeat_enabled = not self._repeat_enabled
        self._menu_repeat.Check(self._repeat_enabled)
        if self._repeat_enabled:
            # Translators: Repeat mode on notification.
            self._notify_toggle(_("Repeat on"))
        else:
            # Translators: Repeat mode off notification.
            self._notify_toggle(_("Repeat off"))

    def _tray_toggle_shuffle(self) -> None:
        """Toggle shuffle mode, called from the tray icon menu."""
        self._shuffle_enabled = not self._shuffle_enabled
        self._menu_shuffle.Check(self._shuffle_enabled)
        if self._shuffle_enabled:
            if self._queue:
                self._shuffle_queue_around_current()
            # Translators: Shuffle mode on notification.
            self._notify_toggle(_("Shuffle on"))
        else:
            if self._queue and self._original_queue:
                self._unshuffle_queue()
            # Translators: Shuffle mode off notification.
            self._notify_toggle(_("Shuffle off"))

    def _on_refresh(self, event: wx.CommandEvent):
        self.load_library()

    def _rebuild_servers_menu(self) -> None:
        """Rebuild the 'Change Server' submenu from the DB."""
        # Remove old items and unbind
        for item in list(
            self._servers_submenu.GetMenuItems()
        ):
            self.Unbind(
                wx.EVT_MENU, id=item.GetId(),
            )
            self._servers_submenu.Delete(item)
        self._server_menu_items.clear()

        active_id = self._settings.active_server_id
        for server in self._db.get_all_servers():
            label = "{user} @ {url}".format(
                user=server.username, url=server.url,
            )
            item = self._servers_submenu.AppendRadioItem(
                wx.ID_ANY, label,
            )
            if server.id == active_id:
                item.Check(True)
            self._server_menu_items[item.GetId()] = (
                server.id or 0
            )
            self.Bind(
                wx.EVT_MENU,
                self._on_server_menu_item,
                item,
            )

        if self._server_menu_items:
            self._servers_submenu.AppendSeparator()

        # Translators: Menu item to open server manager.
        manage_item = self._servers_submenu.Append(
            wx.ID_ANY,
            _("Manage Servers..."),
        )
        self.Bind(
            wx.EVT_MENU,
            self._on_manage_servers,
            manage_item,
        )

    def _on_server_menu_item(
        self, event: wx.CommandEvent,
    ) -> None:
        """Switch to a saved server from the submenu."""
        server_id = self._server_menu_items.get(
            event.GetId(),
        )
        if server_id is None:
            return
        # Clicking the already-active server does nothing
        if server_id == self._settings.active_server_id:
            return
        server = self._db.get_server(server_id)
        if not server:
            return
        self._switch_to_server(server)

    def _on_manage_servers(
        self, event: wx.CommandEvent,
    ) -> None:
        """Open the server management dialog."""
        from chordcut.ui.dialogs.servers_dialog import (
            ServersDialog,
        )
        dlg = ServersDialog(
            self, self._db, self._client,
            self._settings,
        )
        dlg.ShowModal()
        switch_needed = dlg.server_switch_needed
        dlg.Destroy()

        self._rebuild_servers_menu()

        if switch_needed:
            self._reset_for_server_switch()
            self.load_library()

    def _switch_to_server(
        self, server: ServerCredentials,
    ) -> None:
        """Reconnect to a saved server and reload library."""
        # Translators: Busy dialog while switching servers.
        progress = wx.BusyInfo(
            _("Connecting to server...")
        )
        ok = self._client.login_with_token(
            server.url,
            server.user_id,
            server.access_token,
            server.device_id,
        )
        del progress

        if not ok:
            wx.MessageBox(
                # Translators: Error when switching servers.
                _(
                    "Failed to connect to the server.\n\n"
                    "The previous server remains active."
                ),
                # Translators: Server switch error title.
                _("Connection Failed"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            # Restore checkmark to current active server
            self._rebuild_servers_menu()
            return

        self._settings.active_server_id = server.id
        self._settings.save()
        self._reset_for_server_switch()
        self.load_library()

    def _reset_for_server_switch(self) -> None:
        """Clear all library state to prepare for a new server."""
        # Stop playback
        self._player.stop()
        self._current_track = None
        self._clear_album_art()

        # Clear queue
        self._queue = []
        self._queue_index = -1
        self._queue_origin = None
        self._original_queue = []

        # Invalidate pending background load callbacks
        self._load_server_id = None
        self._current_server = None

        # Clear loading state
        self._loading_in_progress = False
        self._initial_loading = False
        self._lib_track_counts = {}
        self._lib_loaded_counts = {}

        # Clear navigation
        self._nav_stack = []
        self._current_level_type = "tracks"
        self._context_name = None
        self._all_items = []
        self._filtered_items = []

        # Clear in-memory library
        self._lib_tracks = []
        self._lib_playlists = []
        self._lib_artists = []
        self._lib_album_artists = []
        self._lib_albums = []

        # Clear library filter state
        self._libraries = []
        self._selected_library_ids = None

        # Clear lyrics cache
        self._lyrics_cache = {}

        # Reset UI
        self._search_text.ChangeValue("")
        self._search_sizer.ShowItems(True)
        self._section_choice.SetSelection(0)
        self._list.set_items([])
        # Translators: Label when no library is loaded.
        self._list_label.SetLabel(
            ngettext(
                "{n} track", "{n} tracks", 0,
            ).format(n=0)
        )
        # Translators: Now playing when nothing plays.
        self._now_playing_label.SetLabel(
            _("Not playing")
        )
        self._update_title()
        self._panel.Layout()

    def _on_shortcuts(self, event: wx.CommandEvent):
        # Translators: Keyboard shortcuts help text.
        shortcuts = _(
            "Keyboard Shortcuts:\n\n"
            "Navigation:\n"
            "  Tab            - Move between controls\n"
            "  Up/Down        - Navigate items\n"
            "  Enter          - Play track / open item\n"
            "  Backspace      - Go back one level\n\n"
            "Playback:\n"
            "  Escape         - Pause/Resume\n"
            "  Ctrl+Alt+Q     - Stop\n"
            "  Shift+Right    - Next track\n"
            "  Shift+Left     - Previous track\n"
            "  Ctrl+Alt+X     - Restart track\n"
            "  Ctrl+Alt+R     - Toggle repeat\n"
            "  Ctrl+Alt+S     - Toggle shuffle\n"
            "  Ctrl+Up        - Volume up\n"
            "  Ctrl+Down      - Volume down\n"
            "  Ctrl+Right     - Seek forward\n"
            "  Ctrl+Left      - Seek backward\n\n"
            "Context:\n"
            "  Alt+Enter        - Properties\n"
            "  Ctrl+C           - Copy link\n"
            "  Ctrl+Shift+C     - Copy stream link\n"
            "  Ctrl+Shift+Enter - Download track\n\n"
            "Playlists:\n"
            "  Ctrl+N         - New playlist\n"
            "  F2             - Rename playlist\n"
            "  Delete         - Delete playlist / "
            "remove track\n"
            "  Alt+Up/Down    - Reorder tracks\n\n"
            "Other:\n"
            "  F5             - Refresh library\n"
            "  F8             - Settings\n"
            "  F1             - Show this help\n"
            "  Alt+F4         - Exit"
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

    # ------------------------------------------------------------------
    # Context menu & actions
    # ------------------------------------------------------------------

    def _on_context_menu(
        self, event: wx.ContextMenuEvent,
    ) -> None:
        """Show context menu for the selected item."""
        item = self._list.get_selected_item()
        if not item:
            return

        from chordcut.ui.context_menu import (
            build_context_menu,
            ID_PLAY, ID_OPEN, ID_GO_BACK,
            ID_GO_TO_ARTIST, ID_GO_TO_ALBUM,
            ID_GO_TO_ALBUM_ARTIST,
            ID_VIEW_LYRICS, ID_SYNCED_LYRICS,
            ID_DOWNLOAD, ID_COPY_LINK, ID_COPY_STREAM,
            ID_PROPERTIES,
            ID_REMOVE_FROM_PLAYLIST,
            ID_MOVE_UP, ID_MOVE_DOWN,
            ID_RENAME_PLAYLIST, ID_DELETE_PLAYLIST,
        )

        in_playlist = bool(self._current_playlist_id())
        item_index = self._list.GetSelection()

        # Build "Add to Playlist" data for tracks
        playlists = None
        track_in_pls: set[str] = set()
        if self._current_level_type == "tracks":
            playlists = self._lib_playlists
            server = self._current_server
            if server and server.id:
                track_id = item.get("Id", "")
                for pl in self._lib_playlists:
                    pl_id = pl.get("Id", "")
                    ids = self._db.get_playlist_track_ids(
                        server.id, pl_id,
                    )
                    if track_id in ids:
                        track_in_pls.add(pl_id)

        menu, playlist_id_map = build_context_menu(
            self._current_level_type,
            item,
            len(self._nav_stack),
            in_playlist=in_playlist,
            playlists=playlists,
            track_in_playlists=track_in_pls,
            item_index=item_index,
            total_items=len(self._filtered_items),
            moves_locked=self._list_shuffle_active,
        )

        handler_map = {
            ID_PLAY: lambda e: (
                self._play_track_from_list(item)
            ),
            ID_OPEN: lambda e: self._drill_down(item),
            ID_GO_BACK: lambda e: self._go_back(),
            ID_GO_TO_ARTIST: lambda e: (
                self._go_to_artist(item)
            ),
            ID_GO_TO_ALBUM_ARTIST: lambda e: (
                self._go_to_album_artist(item)
            ),
            ID_GO_TO_ALBUM: lambda e: (
                self._go_to_album(item)
            ),
            ID_VIEW_LYRICS: lambda e: (
                self._show_lyrics(item, synced=False)
            ),
            ID_SYNCED_LYRICS: lambda e: (
                self._show_lyrics(item, synced=True)
            ),
            ID_DOWNLOAD: lambda e: (
                self._download_track(item)
            ),
            ID_COPY_LINK: lambda e: (
                self._copy_link(item)
            ),
            ID_COPY_STREAM: lambda e: (
                self._copy_stream_link(item)
            ),
            ID_PROPERTIES: lambda e: (
                self._show_properties(item)
            ),
            ID_REMOVE_FROM_PLAYLIST: lambda e: (
                self._remove_from_playlist(item)
            ),
            ID_MOVE_UP: lambda e: (
                self._move_playlist_item(item, -1)
            ),
            ID_MOVE_DOWN: lambda e: (
                self._move_playlist_item(item, 1)
            ),
            ID_RENAME_PLAYLIST: lambda e: (
                self._rename_playlist(item)
            ),
            ID_DELETE_PLAYLIST: lambda e: (
                self._delete_playlist(item)
            ),
        }

        for mid, handler in handler_map.items():
            self.Bind(wx.EVT_MENU, handler, id=mid)

        # Bind dynamic "Add to Playlist" submenu IDs
        for mid, pl in playlist_id_map.items():
            self.Bind(
                wx.EVT_MENU,
                lambda e, p=pl: (
                    self._add_to_playlist(item, p)
                ),
                id=mid,
            )

        self._list.PopupMenu(menu)
        menu.Destroy()

    def _on_properties_accel(
        self, event: wx.CommandEvent,
    ) -> None:
        item = self._list.get_selected_item()
        if item:
            self._show_properties(item)

    def _on_copy_link_accel(
        self, event: wx.CommandEvent,
    ) -> None:
        item = self._list.get_selected_item()
        if item:
            self._copy_link(item)

    def _on_copy_stream_accel(
        self, event: wx.CommandEvent,
    ) -> None:
        item = self._list.get_selected_item()
        if item and self._current_level_type == "tracks":
            self._copy_stream_link(item)

    def _on_download_accel(
        self, event: wx.CommandEvent,
    ) -> None:
        item = self._list.get_selected_item()
        if item and self._current_level_type == "tracks":
            self._download_track(item)

    def _copy_link(self, item: dict) -> None:
        """Copy the Jellyfin web URL to clipboard."""
        item_id = item.get("Id")
        if not item_id or not self._client.server_url:
            return

        url = (
            "{server}/web/index.html"
            "#!/details?id={id}"
        ).format(
            server=self._client.server_url,
            id=item_id,
        )

        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(
                wx.TextDataObject(url),
            )
            wx.TheClipboard.Close()
            # Translators: After copying link.
            self._notify_toggle(
                _("Link copied to clipboard")
            )

    def _copy_stream_link(self, item: dict) -> None:
        """Copy the direct stream URL to clipboard."""
        if self._current_level_type != "tracks":
            return
        track_id = item.get("Id")
        if not track_id:
            return
        url = self._client.get_stream_url(track_id)
        if not url:
            return
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(
                wx.TextDataObject(url),
            )
            wx.TheClipboard.Close()
            # Translators: After copying stream link.
            self._notify_toggle(
                _("Stream link copied to clipboard")
            )

    def _show_properties(self, item: dict) -> None:
        """Show properties dialog for an item."""
        lt = self._current_level_type

        if lt == "tracks":
            self._show_track_properties(item)
            return

        from chordcut.ui.dialogs.properties_dialog import (
            PropertiesDialog,
            build_artist_properties,
            build_album_properties,
            build_playlist_properties,
        )

        server = self._current_server
        if not server or not server.id:
            return
        lib_ids = self._selected_library_ids

        if lt in ("artists", "album_artists"):
            stats = self._db.get_artist_stats(
                server.id, item.get("Id", ""),
                lt, lib_ids,
            )
            props = build_artist_properties(item, stats)
            # Translators: Artist properties dialog title.
            title = _("Artist Properties")
        elif lt == "albums":
            stats = self._db.get_album_stats(
                server.id, item.get("Id", ""), lib_ids,
            )
            props = build_album_properties(item, stats)
            # Translators: Album properties dialog title.
            title = _("Album Properties")
        elif lt == "playlists":
            stats = self._db.get_playlist_stats(
                server.id, item.get("Id", ""),
            )
            props = build_playlist_properties(
                item, stats,
            )
            # Translators: Playlist properties title.
            title = _("Playlist Properties")
        else:
            return

        dlg = PropertiesDialog(self, title, props)
        dlg.ShowModal()
        dlg.Destroy()

    def _show_track_properties(
        self, item: dict,
    ) -> None:
        """Fetch details then show track properties."""
        track_id = item.get("Id")
        if not track_id:
            return
        # Translators: Fetching details status.
        self._update_status(_("Fetching details..."))

        def on_details(details):
            wx.CallAfter(
                self._on_track_details_received,
                item, details,
            )

        self._client.get_item_details_async(
            track_id, on_details,
        )

    def _on_track_details_received(
        self, track: dict, details: dict | None,
    ) -> None:
        from chordcut.ui.dialogs.properties_dialog import (
            PropertiesDialog,
            build_track_properties,
        )

        props = build_track_properties(
            track, details,
        )
        # Translators: Track properties dialog title.
        title = _("Track Properties")
        dlg = PropertiesDialog(self, title, props)
        dlg.ShowModal()
        dlg.Destroy()
        # Translators: Ready status.
        self._update_status(_("Ready"))

    def _show_lyrics(
        self, item: dict, synced: bool = False,
    ) -> None:
        """Fetch and show lyrics for a track."""
        track_id = item.get("Id")
        if not track_id:
            return

        # Check cache first
        cached = self._lyrics_cache.get(track_id)
        if cached == "none":
            wx.MessageBox(
                # Translators: No lyrics available message.
                _("No lyrics available for this track."),
                # Translators: Lyrics dialog title.
                _("Lyrics"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return
        if isinstance(cached, dict):
            self._on_lyrics_received(
                cached, item, synced,
            )
            return

        # Translators: Fetching lyrics status.
        self._update_status(_("Fetching lyrics..."))

        def on_lyrics(result):
            wx.CallAfter(
                self._on_lyrics_received,
                result, item, synced,
            )

        self._client.get_lyrics_async(
            track_id, on_lyrics,
        )

    def _on_lyrics_received(
        self,
        result: dict | None,
        track: dict,
        synced: bool,
    ) -> None:
        track_id = track.get("Id", "")

        if not result or not result.get("Lyrics"):
            self._lyrics_cache[track_id] = "none"
            wx.MessageBox(
                # Translators: No lyrics available message.
                _("No lyrics available for this track."),
                # Translators: Lyrics dialog title.
                _("Lyrics"),
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        # Cache the result
        self._lyrics_cache[track_id] = result

        lyrics = result["Lyrics"]
        name = track.get("Name") or _("Untitled")

        has_timing = any(
            cue.get("Start") is not None
            and cue["Start"] > 0
            for cue in lyrics
        )

        from chordcut.ui.dialogs.lyrics_dialog import (
            PlainLyricsDialog,
            SyncedLyricsDialog,
        )

        if synced:
            if not has_timing:
                wx.MessageBox(
                    # Translators: No synced lyrics message.
                    _(
                        "Synced lyrics are not available "
                        "for this track."
                    ),
                    # Translators: Synced lyrics title.
                    _("Synced Lyrics"),
                    wx.OK | wx.ICON_INFORMATION,
                    self,
                )
                return

            # Load the track (paused) so seek works
            self._load_track_for_lyrics(track)

            def play_from_cb(ticks: int) -> None:
                """Seek to timestamp and resume."""
                pos = ticks / 10_000_000
                self._player.seek(
                    pos, relative=False,
                )
                if not self._player.is_playing:
                    self._player.resume()

            def pause_cb() -> None:
                self._player.toggle_pause()

            def seek_cb(seconds: float) -> None:
                self._player.seek(seconds)

            def vol_up_cb() -> None:
                self._player.volume_up()

            def vol_down_cb() -> None:
                self._player.volume_down()

            # Translators: Synced lyrics dialog title.
            dlg = SyncedLyricsDialog(
                self,
                _("Lyrics - {title}").format(
                    title=name,
                ),
                lyrics,
                play_from_cb,
                pause_cb,
                seek_cb,
                vol_up_cb,
                vol_down_cb,
            )
        else:
            text = "\n".join(
                cue.get("Text", "") for cue in lyrics
            )
            # Translators: Plain lyrics dialog title.
            dlg = PlainLyricsDialog(
                self,
                _("Lyrics - {title}").format(
                    title=name,
                ),
                text,
            )

        if synced:
            self._synced_lyrics_active = True
        dlg.ShowModal()
        if synced:
            self._synced_lyrics_active = False
        dlg.Destroy()
        # Translators: Ready status.
        self._update_status(_("Ready"))

    def _load_track_for_lyrics(
        self, track: dict,
    ) -> None:
        """Load a track paused at beginning for lyrics.

        Builds the queue from the current list (same as
        pressing Enter) so next/prev work after dialog
        closes. If the track is already loaded, only the
        queue is rebuilt.
        """
        tid = track.get("Id")
        if not tid:
            return

        # Build queue like _play_track_from_list
        self._queue = list(self._filtered_items)
        self._original_queue = list(
            self._filtered_items,
        )
        self._queue_index = next(
            (
                i for i, t in enumerate(self._queue)
                if t.get("Id") == tid
            ),
            0,
        )
        self._queue_origin = _QueueOrigin(
            section_idx=(
                self._section_choice.GetSelection()
            ),
            nav_depth=len(self._nav_stack),
            level_type=self._current_level_type,
            context_name=self._context_name,
        )
        if self._shuffle_enabled:
            self._shuffle_queue_around_current()

        current_id = None
        if self._current_track:
            current_id = self._current_track.get("Id")

        if current_id == tid and self._player.is_loaded:
            return

        url = self._client.get_stream_url(tid)
        if not url:
            return

        self._current_track = track
        self._player.play(url)
        self._player.pause()
        title = track.get("Name") or _("Untitled")
        # Translators: Status bar when playing.
        self._update_status(
            _("Playing: {title}").format(title=title)
        )
        self._update_title()

    def _download_track(self, item: dict) -> None:
        """Download a track to the music folder."""
        if self._current_level_type != "tracks":
            return
        track_id = item.get("Id")
        if not track_id:
            return
        url = self._client.get_stream_url(track_id)
        if not url:
            return

        name = item.get("Name", "track")
        artist = item.get("ArtistDisplay", "")
        if artist:
            filename = "{artist} - {name}".format(
                artist=artist, name=name,
            )
        else:
            filename = name
        # Sanitize
        bad = r'\/:*?"<>|'
        filename = "".join(
            c for c in filename if c not in bad
        )
        filename = filename.strip() or "track"

        from chordcut.ui.dialogs.download_dialog import (
            DownloadDialog,
        )

        dlg = DownloadDialog(
            self,
            # Translators: Download dialog title.
            _("Download: {title}").format(title=name),
            url,
            filename,
            download_dir=self._settings.download_dir,
        )
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_OK:
            # Translators: Download complete notification.
            self._notify_toggle(_("Download complete"))

    # ------------------------------------------------------------------
    # Playlist management
    # ------------------------------------------------------------------

    def _on_new_playlist(
        self, event: wx.CommandEvent,
    ) -> None:
        """Show dialog to create a new playlist."""
        # Translators: New playlist dialog prompt.
        dlg = wx.TextEntryDialog(
            self,
            _("Enter playlist name:"),
            # Translators: New playlist dialog title.
            _("New Playlist"),
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        name = dlg.GetValue().strip()
        dlg.Destroy()
        if not name:
            return

        server = self._current_server
        if not server or not server.id:
            return
        srv_id = server.id

        # Translators: Creating playlist status.
        self._update_status(
            _("Creating playlist...")
        )

        def on_done(pl_id: str | None) -> None:
            wx.CallAfter(
                self._on_create_playlist_done,
                pl_id, srv_id, name,
            )

        self._client.create_playlist_async(
            name, on_done,
        )

    def _on_create_playlist_done(
        self,
        playlist_id: str | None,
        server_id: int,
        name: str,
    ) -> None:
        """Handle create-playlist completion."""
        if not playlist_id:
            # Translators: Create playlist failed.
            self._update_status(
                _("Failed to create playlist")
            )
            return

        self._db.create_playlist(
            server_id, playlist_id, name,
        )
        # Reload playlists into memory
        self._lib_playlists = (
            self._db.get_all_playlists(server_id)
        )

        # Refresh view if on playlists section
        idx = self._section_choice.GetSelection()
        if (
            SECTIONS[idx] == "playlists"
            and not self._nav_stack
        ):
            self._display_level(
                self._lib_playlists,
                "playlists", None,
            )

        # Translators: Playlist created notification.
        self._notify_toggle(
            _("Playlist \"{name}\" created").format(
                name=name,
            )
        )

    def _rename_playlist(self, item: dict) -> None:
        """Rename a playlist via dialog."""
        if self._current_level_type != "playlists":
            return
        pl_id = item.get("Id", "")
        old_name = item.get("Name", "")
        if not pl_id:
            return

        # Translators: Rename playlist dialog prompt.
        dlg = wx.TextEntryDialog(
            self,
            _("Enter new name:"),
            # Translators: Rename playlist dialog title.
            _("Rename Playlist"),
            value=old_name,
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        new_name = dlg.GetValue().strip()
        dlg.Destroy()
        if not new_name or new_name == old_name:
            return

        server = self._current_server
        if not server or not server.id:
            return
        srv_id = server.id

        # Update DB and in-memory immediately
        self._db.rename_playlist(
            srv_id, pl_id, new_name,
        )
        item["Name"] = new_name
        self._lib_playlists = (
            self._db.get_all_playlists(srv_id)
        )

        # Refresh list
        self._list.set_items(self._filtered_items)
        self._update_list_label()

        # Fire async server request
        self._client.rename_playlist_async(
            pl_id, new_name,
            lambda ok: None,
        )

        # Translators: Playlist renamed notification.
        self._notify_toggle(
            _("Playlist renamed to \"{name}\"").format(
                name=new_name,
            )
        )

    def _delete_playlist(self, item: dict) -> None:
        """Delete a playlist with confirmation."""
        if self._current_level_type != "playlists":
            return
        pl_id = item.get("Id", "")
        pl_name = item.get("Name", "")
        if not pl_id:
            return

        # Translators: Confirm delete playlist.
        result = wx.MessageBox(
            _("Delete playlist \"{name}\"?").format(
                name=pl_name,
            ),
            # Translators: Confirm delete dialog title.
            _("Delete Playlist"),
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        )
        if result != wx.YES:
            return

        server = self._current_server
        if not server or not server.id:
            return
        srv_id = server.id

        # Update UI immediately
        sel = self._list.GetSelection()
        if item in self._all_items:
            self._all_items.remove(item)
        if item in self._filtered_items:
            self._filtered_items.remove(item)
        self._list.set_items(self._filtered_items)
        new_sel = min(
            sel, len(self._filtered_items) - 1,
        )
        if new_sel >= 0:
            self._list.SetSelection(new_sel)
        self._update_list_label()

        # Update DB and in-memory
        self._db.delete_playlist(srv_id, pl_id)
        self._lib_playlists = (
            self._db.get_all_playlists(srv_id)
        )

        # Fire async server request
        self._client.delete_playlist_async(pl_id)

        # Translators: Playlist deleted notification.
        self._notify_toggle(
            _("Playlist \"{name}\" deleted").format(
                name=pl_name,
            )
        )

    def _current_playlist_id(self) -> str | None:
        """Return the playlist ID if viewing playlist tracks."""
        if (
            self._current_level_type == "tracks"
            and self._nav_stack
            and self._nav_stack[-1].level_type
            == "playlists"
        ):
            return self._nav_stack[-1].selected_id
        return None

    def _add_to_playlist(
        self, track: dict, playlist: dict,
    ) -> None:
        """Add a track to the top of a playlist."""
        track_id = track.get("Id", "")
        pl_id = playlist.get("Id", "")
        pl_name = playlist.get("Name", "")
        if not track_id or not pl_id:
            return

        server = self._current_server
        if not server or not server.id:
            return
        srv_id = server.id

        def on_done(success: bool) -> None:
            wx.CallAfter(
                self._on_add_to_playlist_done,
                success, srv_id,
                track, pl_id, pl_name,
            )

        # Translators: Status when adding to playlist.
        self._update_status(
            _("Adding to {name}...").format(
                name=pl_name,
            )
        )

        self._client.add_to_playlist_async(
            pl_id, track_id, on_done,
        )

    def _on_add_to_playlist_done(
        self,
        success: bool,
        server_id: int,
        track: dict,
        playlist_id: str,
        playlist_name: str,
    ) -> None:
        """Handle add-to-playlist completion."""
        if not success:
            # Translators: Add to playlist failed.
            self._update_status(
                _("Failed to add to playlist")
            )
            return

        # Update DB: use track Id as PlaylistItemId
        # (matches server behavior observed in testing)
        track_id = track.get("Id", "")
        self._db.add_playlist_track(
            server_id, playlist_id,
            track_id, track_id,
        )

        # Translators: Track added to playlist.
        self._notify_toggle(
            _("Added to {name}").format(
                name=playlist_name,
            )
        )

    def _remove_from_playlist(
        self, item: dict,
    ) -> None:
        """Remove a track from the current playlist."""
        pl_id = self._current_playlist_id()
        if not pl_id:
            return

        server = self._current_server
        if not server or not server.id:
            return
        srv_id = server.id

        track_name = item.get("Name", "")
        pid = item.get(
            "PlaylistItemId", item.get("Id", ""),
        )

        # Translators: Confirm remove from playlist.
        result = wx.MessageBox(
            _("Remove \"{name}\" from the playlist?")
            .format(name=track_name),
            # Translators: Confirm remove dialog title.
            _("Remove from Playlist"),
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        )
        if result != wx.YES:
            return

        # Update UI immediately
        sel = self._list.GetSelection()
        if item in self._all_items:
            self._all_items.remove(item)
        if item in self._filtered_items:
            self._filtered_items.remove(item)
        self._list.set_items(self._filtered_items)
        new_sel = min(
            sel, len(self._filtered_items) - 1,
        )
        if new_sel >= 0:
            self._list.SetSelection(new_sel)
        self._update_list_label()

        # Update DB
        self._db.remove_playlist_track(
            srv_id, pl_id, pid,
        )

        # Fire async server request
        self._client.remove_from_playlist_async(
            pl_id, pid,
        )

    def _move_playlist_item(
        self, item: dict, direction: int,
    ) -> None:
        """Move a track up (-1) or down (+1) in playlist."""
        pl_id = self._current_playlist_id()
        if not pl_id:
            return

        server = self._current_server
        if not server or not server.id:
            return

        # Find index in _all_items (unfiltered order)
        try:
            old_idx = self._all_items.index(item)
        except ValueError:
            return
        new_idx = old_idx + direction
        if new_idx < 0 or new_idx >= len(self._all_items):
            return

        # Swap in _all_items
        self._all_items[old_idx], self._all_items[new_idx] = (
            self._all_items[new_idx], self._all_items[old_idx]
        )

        # If no search filter, _filtered_items is the same
        # reference; otherwise swap there too
        if self._filtered_items is not self._all_items:
            try:
                fi_old = self._filtered_items.index(item)
            except ValueError:
                fi_old = -1
            if fi_old >= 0:
                fi_new = fi_old + direction
                if (
                    0 <= fi_new
                    < len(self._filtered_items)
                ):
                    (
                        self._filtered_items[fi_old],
                        self._filtered_items[fi_new],
                    ) = (
                        self._filtered_items[fi_new],
                        self._filtered_items[fi_old],
                    )

        # Refresh list and restore selection
        self._list.set_items(self._filtered_items)
        sel = self._list.GetSelection()
        # Move selection to follow the item
        new_sel = sel + direction
        if 0 <= new_sel < len(self._filtered_items):
            self._list.SetSelection(new_sel)

        # Update DB
        pid = item.get(
            "PlaylistItemId", item.get("Id", ""),
        )
        self._db.move_playlist_track(
            server.id, pl_id, pid,
            old_idx, new_idx,
        )

        # Fire async server request
        self._client.move_playlist_item_async(
            pl_id, pid, new_idx,
        )

    def _go_to_artist(self, item: dict) -> None:
        """Navigate to the (regular) artist."""
        artist_display = item.get("ArtistDisplay", "")

        target = None
        for a in self._lib_artists:
            if a.get("Name") == artist_display:
                target = a
                break

        if not target:
            # Translators: Artist not found status.
            self._update_status(
                _("Artist not found")
            )
            return

        section_idx = SECTIONS.index("artists")
        self._section_choice.SetSelection(section_idx)
        self._switch_to_section(section_idx)
        self._drill_down(target)

    def _go_to_album_artist(self, item: dict) -> None:
        """Navigate to the album artist."""
        album_artist = (
            item.get("AlbumArtist", "")
            or item.get("ArtistDisplay", "")
        )

        target = None
        for a in self._lib_album_artists:
            if a.get("Name") == album_artist:
                target = a
                break

        if not target:
            # Translators: Album artist not found status.
            self._update_status(
                _("Album artist not found")
            )
            return

        section_idx = SECTIONS.index("album_artists")
        self._section_choice.SetSelection(section_idx)
        self._switch_to_section(section_idx)
        self._drill_down(target)

    def _go_to_album(self, item: dict) -> None:
        """Navigate to the album of a track."""
        album_id = item.get("AlbumId")
        if not album_id:
            # Translators: Album not found status.
            self._update_status(
                _("Album not found")
            )
            return

        target = None
        for a in self._lib_albums:
            if a.get("Id") == album_id:
                target = a
                break

        if not target:
            # Translators: Album not found status.
            self._update_status(
                _("Album not found")
            )
            return

        section_idx = SECTIONS.index("albums")
        self._section_choice.SetSelection(section_idx)
        self._switch_to_section(section_idx)
        self._drill_down(target)

    # ------------------------------------------------------------------
    # Sleep timer
    # ------------------------------------------------------------------

    def _on_timer_menu(self, event: wx.CommandEvent) -> None:
        """Open the timer setup dialog, or cancel the active timer."""
        if self._countdown_timer.IsRunning():
            # User clicked the checked item — cancel the timer.
            self._cancel_timer()
            return

        # Menu was just checked; show the setup dialog.
        from chordcut.ui.dialogs.timer_dialog import TimerDialog
        dlg = TimerDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self._countdown_seconds = dlg.get_total_seconds()
            self._timer_action = dlg.get_action()
            self._countdown_timer.Start(1000)
            self._menu_timer.Check(True)
            self._update_timer_display()
        else:
            # User cancelled the dialog; un-check the menu item.
            self._menu_timer.Check(False)
        dlg.Destroy()

    def _cancel_timer(self) -> None:
        """Stop and reset the sleep timer."""
        self._countdown_timer.Stop()
        self._countdown_seconds = 0
        self._timer_action = ""
        self._menu_timer.Check(False)
        self.SetStatusText("", 3)

    def _update_timer_display(self) -> None:
        """Render the remaining time in status bar pane 3."""
        h = self._countdown_seconds // 3600
        m = (self._countdown_seconds % 3600) // 60
        s = self._countdown_seconds % 60
        # Translators: Sleep timer countdown shown in the status bar.
        self.SetStatusText(
            _("Timer: {h:02d}:{m:02d}:{s:02d}").format(h=h, m=m, s=s),
            3,
        )

    def _on_countdown_tick(self, event: wx.TimerEvent) -> None:
        """Called every second while the sleep timer is running."""
        self._countdown_seconds -= 1
        if self._countdown_seconds <= 0:
            self._countdown_timer.Stop()
            self._menu_timer.Check(False)
            self.SetStatusText("", 3)
            self._execute_timer_action()
        else:
            self._update_timer_display()

    def _execute_timer_action(self) -> None:
        """Execute the action selected in the timer dialog."""
        action = self._timer_action
        self._timer_action = ""
        self._countdown_seconds = 0
        if action == "close":
            self.Close()
        elif action == "shutdown":
            subprocess.run(
                ["shutdown", "/s", "/t", "0"],
                check=False,
            )
        elif action == "sleep":
            subprocess.run(
                [
                    "rundll32.exe",
                    "powrprof.dll,SetSuspendState",
                    "0,1,0",
                ],
                check=False,
            )

    def _on_activate(self, event: wx.ActivateEvent):
        """Handle window activation/deactivation to preserve focus.

        When the window is deactivated (Alt+Tab, minimize, etc.), we save
        which control had focus. When reactivated, we restore focus to that
        control instead of letting wx/Windows pick an arbitrary one.
        """
        if event.GetActive():
            # Window is being activated - restore focus via CallAfter
            # to let Windows finish its own focus management first
            wx.CallAfter(self._restore_focus)
        else:
            # Window is being deactivated - save current focus
            focused = self.FindFocus()
            if focused:
                self._last_focused_window = focused
        event.Skip()

    def _restore_focus(self) -> None:
        """Restore focus to the last focused control, or section selector."""
        if self._last_focused_window:
            try:
                # Check if the window is still valid and focusable
                if (
                    self._last_focused_window.IsShown()
                    and self._last_focused_window.IsEnabled()
                ):
                    self._last_focused_window.SetFocus()
                    return
            except (RuntimeError, Exception):
                pass
        # No saved focus or control invalid - default to section selector
        if self._section_choice.IsShown():
            self._section_choice.SetFocus()

    def _on_exit(self, event: wx.CommandEvent):
        self._force_closing = True
        self.Close()

    def _on_close(self, event: wx.CloseEvent):
        if (
            not self._force_closing
            and self._settings.close_to_tray
            and event.CanVeto()
        ):
            event.Veto()
            self._minimize_to_tray()
            return

        self._search_timer.Stop()
        self._countdown_timer.Stop()

        # Remove the tray icon before the window is destroyed.
        if self._tray_icon:
            self._tray_icon.RemoveIcon()
            self._tray_icon.Destroy()
            self._tray_icon = None

        # Persist volume and device if configured to do so.
        if self._settings.remember_volume:
            self._settings.volume = self._player.volume
        if self._settings.remember_device:
            idx = self._device_choice.GetSelection()
            if 0 <= idx < len(self._device_names):
                self._settings.device = (
                    self._device_names[idx]
                )
        self._settings.save()

        self._player.shutdown()
        self._client.shutdown()
        # Flush clipboard so data survives after exit.
        # OleFlushClipboard() copies owned data into the
        # OS clipboard manager, freeing it from this process.
        wx.TheClipboard.Flush()
        event.Skip()

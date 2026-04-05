"""System tray icon for ChordCut."""

import wx
import wx.adv

from chordcut.i18n import _
from chordcut.utils.paths import get_icon_path


def _load_icon() -> wx.Icon:
    """Load the application icon.

    Tries the bundled .ico file first.  Falls back to a simple
    generated bitmap when no file is found.
    """
    icon_path = get_icon_path()
    if icon_path:
        icon = wx.Icon(str(icon_path), wx.BITMAP_TYPE_ICO)
        if icon.IsOk():
            return icon

    # Fallback: programmatic purple note placeholder
    bmp = wx.Bitmap(16, 16)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(90, 40, 170)))
    dc.Clear()
    dc.SetTextForeground(wx.WHITE)
    dc.SetFont(
        wx.Font(
            9,
            wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_BOLD,
        )
    )
    dc.DrawText("C", 3, 1)
    dc.SelectObject(wx.NullBitmap)
    icon = wx.Icon()
    icon.CopyFromBitmap(bmp)
    return icon


class TrayIcon(wx.adv.TaskBarIcon):
    """System tray icon with minimal playback controls."""

    def __init__(self, main_window) -> None:
        super().__init__()
        self._main_window = main_window
        self._icon = _load_icon()

        # Translators: Tooltip shown when hovering over the tray icon.
        self.SetIcon(self._icon, _("ChordCut"))

        self.Bind(
            wx.adv.EVT_TASKBAR_LEFT_DOWN,
            self._on_left_click,
        )

    def _on_left_click(
        self,
        event: wx.adv.TaskBarIconEvent,
    ) -> None:
        if self._main_window.IsShown():
            self._main_window._minimize_to_tray()
        else:
            self._main_window._restore_from_tray()

    def update_tooltip(self, track: dict | None) -> None:
        """Update the tooltip to show the currently playing track."""
        if track:
            name = track.get("Name") or _("Untitled")
            artist = track.get("ArtistDisplay") or track.get("AlbumArtist") or ""
            tooltip = f"{name}\n{artist}" if artist else name
            if len(tooltip) > 128:
                tooltip = tooltip[:125] + "..."
        else:
            # Translators: Tray tooltip when nothing is playing.
            tooltip = _("ChordCut")
        self.SetIcon(self._icon, tooltip)

    def CreatePopupMenu(self) -> wx.Menu:
        """Build the tray right-click context menu."""
        win = self._main_window
        player = win._player
        menu = wx.Menu()

        # Toggle window visibility
        if win.IsShown():
            # Translators: Tray context menu: hide window to tray.
            toggle_label = _("&Minimize to Tray")
        else:
            # Translators: Tray context menu: restore window from tray.
            toggle_label = _("&Restore")
        item_toggle = menu.Append(wx.ID_ANY, toggle_label)
        menu.AppendSeparator()

        # Pause / Resume (label reflects current state)
        if player.is_playing:
            # Translators: Tray context menu: pause playback.
            pause_label = _("&Pause")
        else:
            # Translators: Tray context menu: resume playback.
            pause_label = _("&Resume")
        item_pause = menu.Append(wx.ID_ANY, pause_label)
        menu.AppendSeparator()

        # Previous / Next track
        item_prev = menu.Append(
            wx.ID_ANY,
            # Translators: Tray context menu: previous track.
            _("Pre&vious Track"),
        )
        item_next = menu.Append(
            wx.ID_ANY,
            # Translators: Tray context menu: next track.
            _("&Next Track"),
        )
        menu.AppendSeparator()

        # Volume
        item_vol_up = menu.Append(
            wx.ID_ANY,
            # Translators: Tray context menu: raise volume.
            _("Volume &Up"),
        )
        item_vol_down = menu.Append(
            wx.ID_ANY,
            # Translators: Tray context menu: lower volume.
            _("Volume &Down"),
        )
        menu.AppendSeparator()

        # Seek
        item_seek_fwd = menu.Append(
            wx.ID_ANY,
            # Translators: Tray context menu: seek forward.
            _("Seek &Forward"),
        )
        item_seek_bwd = menu.Append(
            wx.ID_ANY,
            # Translators: Tray context menu: seek backward.
            _("Seek &Backward"),
        )
        menu.AppendSeparator()

        # Repeat / Shuffle (checkable, reflect current state)
        item_repeat = menu.AppendCheckItem(
            wx.ID_ANY,
            # Translators: Tray context menu: toggle repeat mode.
            _("&Repeat"),
        )
        item_repeat.Check(win._repeat_enabled)

        item_shuffle = menu.AppendCheckItem(
            wx.ID_ANY,
            # Translators: Tray context menu: toggle shuffle mode.
            _("S&huffle"),
        )
        item_shuffle.Check(win._shuffle_enabled)
        menu.AppendSeparator()

        # Close
        item_close = menu.Append(
            wx.ID_ANY,
            # Translators: Tray context menu: close the application.
            _("&Close"),
        )

        # --- Bind handlers ---
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: (
                win._minimize_to_tray() if win.IsShown() else win._restore_from_tray()
            ),
            item_toggle,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._on_pause(None),
            item_pause,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._on_prev_track(None),
            item_prev,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._on_next_track(None),
            item_next,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._on_volume_up(None),
            item_vol_up,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._on_volume_down(None),
            item_vol_down,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._on_seek_forward(None),
            item_seek_fwd,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._on_seek_backward(None),
            item_seek_bwd,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._tray_toggle_repeat(),
            item_repeat,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._tray_toggle_shuffle(),
            item_shuffle,
        )
        menu.Bind(
            wx.EVT_MENU,
            lambda _e: win._force_close(),
            item_close,
        )

        return menu

"""System-wide hotkeys via RegisterHotKey (wx.Window.RegisterHotKey).

All combos live on the Ctrl+Shift+Alt layer with navigation keys where
possible: that layer is unused by NVDA and JAWS (unlike Ctrl+Alt, whose
arrow/Home combos are screen reader table navigation), cannot collide
with AltGr typing on character keys we avoid, and is rarely claimed by
other software.  Registration is polite: a combo another application
already owns is skipped and reported, never fought over.
"""

import logging
from collections.abc import Callable

import wx

_log = logging.getLogger(__name__)

_MOD = wx.MOD_CONTROL | wx.MOD_ALT | wx.MOD_SHIFT

# action id -> (display key name, wx key code)
# Home/End/PgUp/PgDn are deliberately absent: many laptop keyboards
# produce them via Fn+arrows, which makes the chords four-modifier
# presses that often misfire.
_HOTKEYS: dict[str, tuple[str, int]] = {
    "play_pause": ("Ctrl+Shift+Alt+Space", wx.WXK_SPACE),
    "previous": ("Ctrl+Shift+Alt+P", ord("P")),
    "next": ("Ctrl+Shift+Alt+N", ord("N")),
    "seek_backward": ("Ctrl+Shift+Alt+Left", wx.WXK_LEFT),
    "seek_forward": ("Ctrl+Shift+Alt+Right", wx.WXK_RIGHT),
    "volume_up": ("Ctrl+Shift+Alt+Up", wx.WXK_UP),
    "volume_down": ("Ctrl+Shift+Alt+Down", wx.WXK_DOWN),
    "repeat": ("Ctrl+Shift+Alt+R", ord("R")),
    "shuffle": ("Ctrl+Shift+Alt+S", ord("S")),
    "toggle_window": ("Ctrl+Shift+Alt+C", ord("C")),
}

_ID_BASE = 0xB000


class GlobalHotkeys:
    """Registers and dispatches the application's global hotkeys."""

    def __init__(
        self,
        window: wx.Window,
        actions: dict[str, Callable[[], None]],
    ) -> None:
        self._window = window
        self._actions = actions
        self._registered_ids: list[int] = []
        # Display names of combos the OS refused (owned elsewhere).
        self.failed: list[str] = []
        self._ids: dict[int, str] = {}
        for i, action in enumerate(_HOTKEYS):
            self._ids[_ID_BASE + i] = action
        window.Bind(wx.EVT_HOTKEY, self._on_hotkey)

    @property
    def active(self) -> bool:
        """Whether any hotkey is currently registered."""
        return bool(self._registered_ids)

    def register(self) -> None:
        """Register all hotkeys, remembering combos the OS refused."""
        if self._registered_ids:
            return
        self.failed = []
        for hotkey_id, action in self._ids.items():
            name, keycode = _HOTKEYS[action]
            if self._window.RegisterHotKey(hotkey_id, _MOD, keycode):
                self._registered_ids.append(hotkey_id)
            else:
                self.failed.append(name)
                _log.warning("Global hotkey unavailable: %s", name)

    def unregister(self) -> None:
        """Release all registered hotkeys."""
        for hotkey_id in self._registered_ids:
            try:
                self._window.UnregisterHotKey(hotkey_id)
            except Exception:
                pass
        self._registered_ids.clear()
        self.failed = []

    def _on_hotkey(self, event: wx.KeyEvent) -> None:
        action = self._ids.get(event.GetId())
        handler = self._actions.get(action) if action else None
        if handler:
            handler()
        else:
            event.Skip()

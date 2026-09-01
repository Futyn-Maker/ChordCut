"""Visual lyrics panel shown beside the library list.

Karaoke-style display for the playing track: with synced lyrics the
current line is emphasized and kept centered while neighbors are
dimmed; plain lyrics render as scrollable text. Clicking a synced line
seeks to it; the mouse wheel scrolls (pausing auto-follow briefly).

Like the transport canvas, the panel is mouse-only and invisible to
screen readers by design: it never takes focus, contributes no tab
stops, and exposes no named accessible elements — screen reader users
have the fully accessible lyrics dialogs instead.
"""

import bisect
import time
from collections.abc import Callable

import wx

from chordcut.i18n import _
from chordcut.ui.theme import Theme

_FOLLOW_RESUME_SECONDS = 4.0


class LyricsPanel(wx.Window):
    """Custom-drawn, mouse-only lyrics display."""

    def __init__(
        self,
        parent: wx.Window,
        on_seek_to: Callable[[int], None],
    ):
        super().__init__(parent, style=wx.BORDER_THEME, name="")
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self._on_seek_to = on_seek_to

        self._cues: list[dict] = []  # {"Start": ticks, "Text": str}
        self._starts: list[float] = []  # start times in seconds
        self._synced = False
        self._current = -1
        self._scroll = 0.0  # manual scroll offset in lines
        self._last_user_scroll = 0.0
        self._hover_line = -1
        # Translators: Lyrics panel placeholder when nothing plays.
        self._message = _("Nothing is playing")

        self._theme = Theme(self)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_SIZE, lambda e: self.Refresh())
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_click)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self._on_theme_change)
        self.Bind(wx.EVT_DPI_CHANGED, self._on_theme_change)

    # Mouse-only by design (see module docstring).
    def AcceptsFocus(self) -> bool:
        return False

    def AcceptsFocusFromKeyboard(self) -> bool:
        return False

    def DoGetBestSize(self) -> wx.Size:
        return self.FromDIP(wx.Size(260, 200))

    # ------------------------------------------------------------------
    # State pushed by MainWindow

    def show_message(self, text: str) -> None:
        """Replace content with a status message (no lyrics, etc.)."""
        self._cues = []
        self._starts = []
        self._synced = False
        self._current = -1
        self._scroll = 0.0
        self._message = text
        self.Refresh()

    def set_lyrics(self, cues: list[dict], synced: bool) -> None:
        """Show lyrics; cues are dicts with Start (ticks) and Text."""
        self._cues = [c for c in cues if c.get("Text")]
        self._starts = [(c.get("Start", 0) or 0) / 10_000_000 for c in self._cues]
        self._synced = synced and bool(self._starts)
        self._current = -1
        self._scroll = 0.0
        self._last_user_scroll = 0.0
        self.Refresh()

    def set_position(self, position: float) -> None:
        """Advance the highlighted line to the playback position."""
        if not self._synced or not self._cues:
            return
        idx = bisect.bisect_right(self._starts, position) - 1
        if idx != self._current:
            self._current = idx
            if self._follow_active():
                self._scroll = 0.0
            self.Refresh()

    def _follow_active(self) -> bool:
        return time.monotonic() - self._last_user_scroll > _FOLLOW_RESUME_SECONDS

    # ------------------------------------------------------------------
    # Mouse

    def _on_wheel(self, event: wx.MouseEvent) -> None:
        if not self._cues:
            return
        self._last_user_scroll = time.monotonic()
        self._scroll += -event.GetWheelRotation() / event.GetWheelDelta() * 3
        max_off = float(len(self._cues))
        self._scroll = min(max(self._scroll, -max_off), max_off)
        self.Refresh()

    def _on_click(self, event: wx.MouseEvent) -> None:
        if not self._synced:
            return
        line = self._line_at(event.GetPosition().y)
        if 0 <= line < len(self._cues):
            self._last_user_scroll = 0.0  # resume following at once
            self._on_seek_to(self._cues[line].get("Start", 0) or 0)

    def _on_motion(self, event: wx.MouseEvent) -> None:
        line = self._line_at(event.GetPosition().y) if self._synced else -1
        if line != self._hover_line:
            self._hover_line = line
            self.SetCursor(wx.Cursor(wx.CURSOR_HAND if line >= 0 else wx.CURSOR_ARROW))
            self.Refresh()

    def _on_leave(self, event: wx.MouseEvent) -> None:
        if self._hover_line != -1:
            self._hover_line = -1
            self.Refresh()

    def _on_theme_change(self, event: wx.Event) -> None:
        self._theme = Theme(self)
        self.Refresh()
        event.Skip()

    # ------------------------------------------------------------------
    # Painting

    def _line_height(self) -> int:
        dc = wx.ClientDC(self)
        dc.SetFont(self._theme.font)
        return dc.GetCharHeight() + self.FromDIP(10)

    def _anchor_line(self) -> float:
        """Index (fractional) of the line drawn at the panel's anchor.

        Synced lyrics anchor the current line to the panel's center
        (karaoke style); plain lyrics anchor line 0 to the top and
        read like a document.
        """
        if self._synced:
            base = self._current if self._current >= 0 else 0
            return base + self._scroll
        return max(0.0, self._scroll)

    def _anchor_y(self) -> int:
        if self._synced:
            return self.GetClientSize().height // 2
        return self._theme.cell_padding + self._line_height() // 2

    def _line_at(self, y: int) -> int:
        lh = self._line_height()
        return round(self._anchor_line() + (y - self._anchor_y()) / lh)

    def _on_paint(self, event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        theme = self._theme
        size = self.GetClientSize()
        dc.SetBackground(wx.Brush(theme.window_bg))
        dc.Clear()
        dc.SetFont(theme.font)

        if not self._cues:
            dc.SetTextForeground(theme.secondary_text)
            tw, th = dc.GetTextExtent(self._message)
            dc.DrawText(
                self._message,
                max(0, (size.width - tw) // 2),
                max(0, (size.height - th) // 2),
            )
            return

        lh = self._line_height()
        center_y = size.height // 2
        anchor = self._anchor_line()
        pad = theme.cell_padding

        first = int(anchor - center_y / lh) - 1
        last = int(anchor + center_y / lh) + 2
        for i in range(max(0, first), min(len(self._cues), last)):
            y = round(center_y + (i - anchor) * lh)
            if y < -lh or y > size.height:
                continue
            text = self._cues[i].get("Text", "")
            if i == self._current and self._synced:
                dc.SetFont(theme.header_font)
                dc.SetTextForeground(
                    theme.accent if not theme.high_contrast else theme.text
                )
            elif i == self._hover_line:
                dc.SetFont(theme.font)
                dc.SetTextForeground(theme.text)
            else:
                dc.SetFont(theme.font)
                dc.SetTextForeground(theme.secondary_text)
            label = wx.Control.Ellipsize(
                text, dc, wx.ELLIPSIZE_END, size.width - 2 * pad
            )
            dc.DrawText(label, pad, y)

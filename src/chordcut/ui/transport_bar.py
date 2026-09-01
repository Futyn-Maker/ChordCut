"""Playback transport bar: art, now-playing, seek, buttons, volume.

The interactive controls are drawn on a single custom canvas that is
deliberately mouse-only: it never takes keyboard focus, is not in the
tab order, and exposes no named accessible elements, so screen reader
users are not disturbed by it (they use hotkeys and menus instead) —
including when a sighted user hovers the mouse over it. All colors
come from system settings so high contrast themes apply automatically.

MainWindow supplies the action callbacks and pushes state through
update_play_state / set_progress / set_volume.
"""

import math
from collections.abc import Callable

import wx

from chordcut.i18n import _
from chordcut.player.mpv_player import format_duration
from chordcut.ui.theme import is_high_contrast


class TransportBar(wx.Panel):
    """Bottom playback bar: album art, now-playing text, controls."""

    def __init__(
        self,
        parent: wx.Window,
        art_size: int,
        *,
        on_prev: Callable[[], None],
        on_play_pause: Callable[[], None],
        on_next: Callable[[], None],
        on_shuffle: Callable[[], None],
        on_repeat: Callable[[], None],
        on_seek: Callable[[float], None],
        on_set_volume: Callable[[int], None],
        on_wheel_seek: Callable[[int], None],
        on_wheel_volume: Callable[[int], None],
        on_lyrics_panel: Callable[[], None],
        on_settings: Callable[[], None],
    ):
        super().__init__(parent)

        # Album art (hidden until a track with art plays)
        self.art_bitmap = wx.StaticBitmap(
            self,
            size=(art_size, art_size),
        )
        self.art_bitmap.Hide()

        self.now_playing_label = wx.StaticText(
            self,
            # Translators: Label when nothing is playing.
            label=_("Not playing"),
            # Translators: Accessible name for now-playing.
            name=_("Now playing"),
        )

        self._canvas = _TransportCanvas(
            self,
            on_prev=on_prev,
            on_play_pause=on_play_pause,
            on_next=on_next,
            on_shuffle=on_shuffle,
            on_repeat=on_repeat,
            on_seek=on_seek,
            on_set_volume=on_set_volume,
            on_wheel_seek=on_wheel_seek,
            on_wheel_volume=on_wheel_volume,
            on_lyrics_panel=on_lyrics_panel,
            on_settings=on_settings,
        )

        right = wx.BoxSizer(wx.VERTICAL)
        right.Add(self.now_playing_label, 0, wx.EXPAND | wx.BOTTOM, 4)
        right.Add(self._canvas, 1, wx.EXPAND)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.art_bitmap, 0, wx.RIGHT, 8)
        sizer.Add(right, 1, wx.EXPAND)
        self.SetSizer(sizer)

    # A panel whose children are all non-focusable becomes a tab stop
    # itself; refuse focus at every level so the whole bar stays out
    # of the tab order (it is mouse-only by design).
    def AcceptsFocus(self) -> bool:
        return False

    def AcceptsFocusFromKeyboard(self) -> bool:
        return False

    def AcceptsFocusRecursively(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # State pushed by MainWindow

    def update_play_state(self, is_playing: bool) -> None:
        self._canvas.set_playing(is_playing)

    def set_progress(self, position: float, duration: float) -> None:
        self._canvas.set_progress(position, duration)

    def set_volume(self, volume: int) -> None:
        self._canvas.set_volume(volume)

    def set_shuffle(self, enabled: bool) -> None:
        self._canvas.set_toggle("shuffle", enabled)

    def set_repeat(self, enabled: bool) -> None:
        self._canvas.set_toggle("repeat", enabled)

    def set_lyrics_panel(self, enabled: bool) -> None:
        self._canvas.set_toggle("lyrics", enabled)


class _TransportCanvas(wx.Window):
    """Custom-drawn, mouse-only strip with all playback controls.

    Not focusable, not in the tab order, no named accessible children:
    invisible to screen readers by design.
    """

    def __init__(self, parent: wx.Window, **handlers: Callable):
        super().__init__(parent, name="")
        self._handlers = handlers
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self._playing = False
        self._position = 0.0
        self._duration = 0.0
        self._volume = 0
        self._toggles = {"shuffle": False, "repeat": False, "lyrics": False}
        self._hover: str | None = None
        self._pressed: str | None = None
        self._seek_dragging = False
        self._drag_fraction = 0.0
        self._volume_dragging = False

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_SIZE, lambda e: self.Refresh())
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, lambda e: self.Refresh())
        self.Bind(wx.EVT_DPI_CHANGED, lambda e: self.Refresh())

    # Mouse-only by design: never reachable with Tab, never focused by
    # a click, so the screen reader focus can never land here.
    def AcceptsFocus(self) -> bool:
        return False

    def AcceptsFocusFromKeyboard(self) -> bool:
        return False

    def DoGetBestSize(self) -> wx.Size:
        return wx.Size(self.FromDIP(300), self.FromDIP(60))

    # ------------------------------------------------------------------
    # State

    def set_playing(self, is_playing: bool) -> None:
        if is_playing != self._playing:
            self._playing = is_playing
            self.Refresh()

    def set_progress(self, position: float, duration: float) -> None:
        if self._seek_dragging:
            return
        redraw = int(position) != int(self._position) or duration != self._duration
        self._position = position
        self._duration = duration
        if redraw:
            self.Refresh()

    def set_volume(self, volume: int) -> None:
        volume = min(max(0, volume), 100)
        if volume != self._volume:
            self._volume = volume
            self.Refresh()

    def set_toggle(self, name: str, enabled: bool) -> None:
        if self._toggles.get(name) != enabled:
            self._toggles[name] = enabled
            self.Refresh()

    # ------------------------------------------------------------------
    # Geometry

    def _regions(self) -> dict[str, wx.Rect]:
        """Compute hit/draw rectangles for the current size."""
        d = self.FromDIP
        w = self.GetClientSize().width
        seek_h = d(20)
        btn = d(32)
        btn_y = seek_h + d(2)
        time_w = d(44)

        regions = {
            "time_pos": wx.Rect(0, 0, time_w, seek_h),
            "seek": wx.Rect(
                time_w + d(6),
                0,
                max(0, w - 2 * (time_w + d(6))),
                seek_h,
            ),
            "time_dur": wx.Rect(w - time_w, 0, time_w, seek_h),
        }

        # Left cluster: shuffle | prev play next | repeat (the layout
        # sighted users know from streaming players).
        x = 0
        for name in ("shuffle", "prev", "play", "next", "repeat"):
            regions[name] = wx.Rect(x, btn_y, btn, btn)
            x += btn + d(6)

        vol_w = d(110)
        x = w - vol_w
        regions["volume"] = wx.Rect(x, btn_y, vol_w, btn)
        x -= d(24) + btn
        regions["settings"] = wx.Rect(x, btn_y, btn, btn)
        x -= btn + d(2)
        regions["lyrics"] = wx.Rect(x, btn_y, btn, btn)
        return regions

    _BUTTONS = (
        "shuffle",
        "prev",
        "play",
        "next",
        "repeat",
        "lyrics",
        "settings",
    )
    _TOGGLES = ("shuffle", "repeat", "lyrics")

    def _tooltip_for(self, region: str | None) -> str:
        # Tooltips carry the matching keyboard shortcut, the way
        # browsers and players like MusicBee do.
        tips = {
            # Translators: Tooltip for the shuffle toggle. {hotkey} is
            # the keyboard shortcut.
            "shuffle": _("Shuffle — {hotkey}").format(hotkey="Ctrl+Alt+S"),
            # Translators: Tooltip for the previous track button.
            "prev": _("Previous track — {hotkey}").format(hotkey="Shift+Left"),
            "play": (
                # Translators: Tooltip for the play/pause button.
                _("Pause — {hotkey}")
                if self._playing
                # Translators: Tooltip for the play/pause button.
                else _("Play — {hotkey}")
            ).format(hotkey="Escape"),
            # Translators: Tooltip for the next track button.
            "next": _("Next track — {hotkey}").format(hotkey="Shift+Right"),
            # Translators: Tooltip for the repeat toggle.
            "repeat": _("Repeat — {hotkey}").format(hotkey="Ctrl+Alt+R"),
            # Translators: Tooltip for the seek bar.
            "seek": _("Seek — {hotkey}").format(hotkey="Ctrl+Left/Right"),
            # Translators: Tooltip for the volume bar.
            "volume": _("Volume — {hotkey}").format(hotkey="Ctrl+Up/Down"),
            # Translators: Tooltip for the lyrics panel toggle.
            "lyrics": _("Lyrics panel — {hotkey}").format(hotkey="F9"),
            # Translators: Tooltip for the settings button.
            "settings": _("Settings — {hotkey}").format(hotkey="F8"),
        }
        return tips.get(region or "", "")

    def _hit_region(self, pos: wx.Point) -> str | None:
        for name, rect in self._regions().items():
            if name.startswith("time_"):
                continue
            if rect.Contains(pos):
                return name
        return None

    # ------------------------------------------------------------------
    # Mouse

    def _on_left_down(self, event: wx.MouseEvent) -> None:
        region = self._hit_region(event.GetPosition())
        if region == "seek":
            self._seek_dragging = True
            self._drag_fraction = self._fraction_from_x(event.GetPosition().x, "seek")
            self.CaptureMouse()
            self.Refresh()
        elif region == "volume":
            self._volume_dragging = True
            self.CaptureMouse()
            self._apply_volume_from_x(event.GetPosition().x)
        elif region in self._BUTTONS:
            self._pressed = region
            self.CaptureMouse()
            self.Refresh()

    def _on_left_up(self, event: wx.MouseEvent) -> None:
        if self.HasCapture():
            self.ReleaseMouse()
        if self._seek_dragging:
            self._seek_dragging = False
            self._handlers["on_seek"](self._drag_fraction)
            self.Refresh()
        elif self._volume_dragging:
            self._volume_dragging = False
        elif self._pressed:
            region = self._hit_region(event.GetPosition())
            pressed = self._pressed
            self._pressed = None
            self.Refresh()
            if region == pressed:
                handler_names = {
                    "shuffle": "on_shuffle",
                    "prev": "on_prev",
                    "play": "on_play_pause",
                    "next": "on_next",
                    "repeat": "on_repeat",
                    "lyrics": "on_lyrics_panel",
                    "settings": "on_settings",
                }
                self._handlers[handler_names[pressed]]()

    def _on_motion(self, event: wx.MouseEvent) -> None:
        pos = event.GetPosition()
        if self._seek_dragging:
            self._drag_fraction = self._fraction_from_x(pos.x, "seek")
            self.Refresh()
            return
        if self._volume_dragging:
            self._apply_volume_from_x(pos.x)
            return
        region = self._hit_region(pos)
        if region != self._hover:
            self._hover = region
            self.SetToolTip(self._tooltip_for(region))
            self.Refresh()

    def _on_leave(self, event: wx.MouseEvent) -> None:
        if self._hover is not None:
            self._hover = None
            self.Refresh()

    def _on_wheel(self, event: wx.MouseEvent) -> None:
        direction = 1 if event.GetWheelRotation() > 0 else -1
        if self._hit_region(event.GetPosition()) == "seek":
            self._handlers["on_wheel_seek"](direction)
        else:
            self._handlers["on_wheel_volume"](direction)

    def _on_capture_lost(self, event: wx.MouseCaptureLostEvent) -> None:
        self._seek_dragging = False
        self._volume_dragging = False
        self._pressed = None
        self.Refresh()

    def _fraction_from_x(self, x: int, region: str) -> float:
        rect = self._regions()[region]
        if rect.width <= 0:
            return 0.0
        return min(max(0.0, (x - rect.x) / rect.width), 1.0)

    def _apply_volume_from_x(self, x: int) -> None:
        fraction = self._fraction_from_x(x, "volume")
        self._handlers["on_set_volume"](round(fraction * 100))

    # ------------------------------------------------------------------
    # Painting

    def _on_paint(self, event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        gc = wx.GraphicsContext.Create(dc)
        regions = self._regions()

        bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)
        text = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNTEXT)
        muted = wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
        accent = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        accent_text = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT)

        dc.SetBackground(wx.Brush(bg))
        dc.Clear()

        dc.SetFont(wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT))
        dc.SetTextForeground(muted)

        # Times + seek bar
        fraction = (
            self._drag_fraction
            if self._seek_dragging
            else (self._position / self._duration if self._duration > 0 else 0.0)
        )
        shown_pos = fraction * self._duration if self._seek_dragging else self._position
        self._draw_time(dc, regions["time_pos"], shown_pos, wx.ALIGN_LEFT)
        self._draw_time(dc, regions["time_dur"], self._duration, wx.ALIGN_RIGHT)
        self._draw_bar(
            gc,
            regions["seek"],
            fraction,
            accent,
            muted,
            thumb=self._hover == "seek" or self._seek_dragging,
        )

        # Buttons
        for name in self._BUTTONS:
            rect = regions[name]
            if rect.x < 0:
                continue  # window too narrow
            active = name in self._TOGGLES and self._toggles.get(name)
            if name == self._pressed:
                glyph_color = accent_text
                gc.SetBrush(wx.Brush(accent))
                gc.SetPen(wx.TRANSPARENT_PEN)
                gc.DrawEllipse(rect.x, rect.y, rect.width, rect.height)
            elif name == self._hover:
                glyph_color = accent if active else text
                gc.SetBrush(wx.Brush(self._blend(accent, bg, 0.18)))
                gc.SetPen(wx.TRANSPARENT_PEN)
                gc.DrawEllipse(rect.x, rect.y, rect.width, rect.height)
            else:
                glyph_color = accent if active else text
            self._draw_glyph(gc, name, rect, glyph_color)
            if active:
                # Small dot under the glyph marks an engaged toggle.
                r = self.FromDIP(2)
                gc.SetBrush(wx.Brush(accent))
                gc.SetPen(wx.TRANSPARENT_PEN)
                gc.DrawEllipse(
                    rect.x + rect.width / 2 - r,
                    rect.y + rect.height - 2 * r - 1,
                    2 * r,
                    2 * r,
                )

        # Volume
        self._draw_glyph(
            gc,
            "speaker",
            wx.Rect(
                regions["volume"].x - self.FromDIP(18),
                regions["volume"].y,
                self.FromDIP(16),
                regions["volume"].height,
            ),
            muted,
        )
        self._draw_bar(
            gc,
            regions["volume"],
            self._volume / 100,
            accent,
            muted,
            thumb=self._hover == "volume" or self._volume_dragging,
        )

    def _blend(self, fg: wx.Colour, bg: wx.Colour, alpha: float) -> wx.Colour:
        # No alpha blends in high contrast: use the pure system color.
        if is_high_contrast():
            return fg
        if wx.SystemSettings.GetAppearance().IsUsingDarkBackground():
            alpha = min(1.0, alpha * 1.5)
        return wx.Colour(
            round(fg.Red() * alpha + bg.Red() * (1 - alpha)),
            round(fg.Green() * alpha + bg.Green() * (1 - alpha)),
            round(fg.Blue() * alpha + bg.Blue() * (1 - alpha)),
        )

    def _draw_time(self, dc: wx.DC, rect: wx.Rect, seconds: float, align: int) -> None:
        label = format_duration(seconds)
        tw, th = dc.GetTextExtent(label)
        x = rect.x if align == wx.ALIGN_LEFT else rect.x + rect.width - tw
        dc.DrawText(label, x, rect.y + (rect.height - th) // 2)

    def _draw_bar(
        self,
        gc: wx.GraphicsContext,
        rect: wx.Rect,
        fraction: float,
        accent: wx.Colour,
        muted: wx.Colour,
        thumb: bool,
    ) -> None:
        d = self.FromDIP
        bar_h = d(4)
        y = rect.y + (rect.height - bar_h) // 2
        radius = bar_h / 2
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(
            wx.Brush(
                self._blend(
                    muted, wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE), 0.5
                )
            )
        )
        gc.DrawRoundedRectangle(rect.x, y, rect.width, bar_h, radius)
        fill = round(rect.width * min(max(fraction, 0.0), 1.0))
        if fill > 0:
            gc.SetBrush(wx.Brush(accent))
            gc.DrawRoundedRectangle(rect.x, y, fill, bar_h, radius)
        if thumb:
            r = d(6)
            gc.SetBrush(wx.Brush(accent))
            gc.DrawEllipse(
                rect.x + fill - r,
                rect.y + rect.height // 2 - r,
                2 * r,
                2 * r,
            )

    def _draw_glyph(
        self,
        gc: wx.GraphicsContext,
        kind: str,
        rect: wx.Rect,
        color: wx.Colour,
    ) -> None:
        gc.SetBrush(wx.Brush(color))
        gc.SetPen(wx.Pen(color, max(1, self.FromDIP(1))))
        s = self.FromDIP(14)
        ox = rect.x + (rect.width - s) / 2
        oy = rect.y + (rect.height - s) / 2
        bar_w = max(2, s // 5)

        if kind == "play" and not self._playing:
            path = gc.CreatePath()
            path.MoveToPoint(ox + s * 0.2, oy)
            path.AddLineToPoint(ox + s * 0.95, oy + s / 2)
            path.AddLineToPoint(ox + s * 0.2, oy + s)
            path.CloseSubpath()
            gc.FillPath(path)
        elif kind == "play":
            gc.DrawRectangle(ox + s * 0.15, oy, bar_w, s)
            gc.DrawRectangle(ox + s * 0.85 - bar_w, oy, bar_w, s)
        elif kind == "prev":
            gc.DrawRectangle(ox, oy, bar_w, s)
            path = gc.CreatePath()
            path.MoveToPoint(ox + s, oy)
            path.AddLineToPoint(ox + s * 0.25, oy + s / 2)
            path.AddLineToPoint(ox + s, oy + s)
            path.CloseSubpath()
            gc.FillPath(path)
        elif kind == "next":
            path = gc.CreatePath()
            path.MoveToPoint(ox, oy)
            path.AddLineToPoint(ox + s * 0.75, oy + s / 2)
            path.AddLineToPoint(ox, oy + s)
            path.CloseSubpath()
            gc.FillPath(path)
            gc.DrawRectangle(ox + s - bar_w, oy, bar_w, s)
        elif kind == "shuffle":
            # Two crossing paths, each ending in a horizontal segment
            # with an arrowhead (the familiar streaming-player icon).
            pen = wx.Pen(color, max(2, self.FromDIP(2)))
            pen.SetCap(wx.CAP_ROUND)
            gc.SetPen(pen)
            for y_start, y_end in ((0.18, 0.82), (0.82, 0.18)):
                gc.StrokeLine(
                    ox,
                    oy + s * y_start,
                    ox + s * 0.2,
                    oy + s * y_start,
                )
                gc.StrokeLine(
                    ox + s * 0.2,
                    oy + s * y_start,
                    ox + s * 0.62,
                    oy + s * y_end,
                )
                gc.StrokeLine(
                    ox + s * 0.62,
                    oy + s * y_end,
                    ox + s * 0.74,
                    oy + s * y_end,
                )
                head = gc.CreatePath()
                head.MoveToPoint(ox + s, oy + s * y_end)
                head.AddLineToPoint(ox + s * 0.70, oy + s * y_end - s * 0.16)
                head.AddLineToPoint(ox + s * 0.70, oy + s * y_end + s * 0.16)
                head.CloseSubpath()
                gc.FillPath(head)
        elif kind == "repeat":
            # Circular arrow: open arc with a tangential arrowhead
            # closing the gap.
            pen = wx.Pen(color, max(2, self.FromDIP(2)))
            pen.SetCap(wx.CAP_ROUND)
            gc.SetPen(pen)
            cx, cy, r = ox + s / 2, oy + s / 2, s * 0.40
            # Small gap at the top, arrowhead sweeping into it.
            end = math.radians(250)
            path = gc.CreatePath()
            path.AddArc(cx, cy, r, math.radians(290), end, True)
            gc.StrokePath(path)
            ex = cx + r * math.cos(end)
            ey = cy + r * math.sin(end)
            # Unit tangent (clockwise) and outward normal at the end.
            tx, ty = -math.sin(end), math.cos(end)
            nx, ny = math.cos(end), math.sin(end)
            half, width = s * 0.18, s * 0.20
            head = gc.CreatePath()
            head.MoveToPoint(ex + tx * half, ey + ty * half)
            head.AddLineToPoint(
                ex - tx * half + nx * width, ey - ty * half + ny * width
            )
            head.AddLineToPoint(
                ex - tx * half - nx * width, ey - ty * half - ny * width
            )
            head.CloseSubpath()
            gc.FillPath(head)
        elif kind == "lyrics":
            # Text lines
            lh = max(2, s // 7)
            for i, width in enumerate((1.0, 1.0, 0.6)):
                gc.DrawRectangle(ox, oy + i * (s // 3) + lh // 2, s * width, lh)
        elif kind == "settings":
            # Gear: outer circle with teeth + hole
            cx, cy = ox + s / 2, oy + s / 2
            outer = s * 0.48
            path = gc.CreatePath()
            path.AddCircle(cx, cy, outer * 0.78)
            gc.FillPath(path)
            for i in range(8):
                angle = i * math.pi / 4
                tw = s * 0.16
                tx = cx + math.cos(angle) * outer - tw / 2
                ty = cy + math.sin(angle) * outer - tw / 2
                gc.DrawEllipse(tx, ty, tw, tw)
            bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)
            gc.SetBrush(wx.Brush(bg))
            gc.DrawEllipse(cx - s * 0.14, cy - s * 0.14, s * 0.28, s * 0.28)
        elif kind == "speaker":
            # Small speaker: box + cone
            gc.DrawRectangle(ox, oy + s * 0.3, s * 0.3, s * 0.4)
            path = gc.CreatePath()
            path.MoveToPoint(ox + s * 0.3, oy + s * 0.3)
            path.AddLineToPoint(ox + s * 0.65, oy)
            path.AddLineToPoint(ox + s * 0.65, oy + s)
            path.AddLineToPoint(ox + s * 0.3, oy + s * 0.7)
            path.CloseSubpath()
            gc.FillPath(path)

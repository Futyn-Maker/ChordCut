"""Custom-drawn multi-column table for library items.

Visually a full table (header, columns, hover, selection); to screen
readers it is a plain list: TrackTableAccessible exposes one LISTITEM
per row whose name comes from the formatters in library_list, so
announcements stay as terse as a native LISTBOX.
"""

import time
from collections.abc import Callable

import wx
import wx.lib.newevent

from chordcut.i18n import _
from chordcut.ui.library_list import format_track
from chordcut.ui.table_columns import COLUMN_MODELS, ColumnSpec
from chordcut.ui.theme import Theme
from chordcut.ui.track_table_accessible import TrackTableAccessible

# Emitted on Ctrl+click of a row; attribute: item (dict).
RowCtrlClickEvent, EVT_ROW_CTRL_CLICK = wx.lib.newevent.NewCommandEvent()
# Emitted on Shift+Ctrl+click; attribute: items (list[dict], in order).
RowRangeClickEvent, EVT_ROW_RANGE_CLICK = wx.lib.newevent.NewCommandEvent()
# Emitted after a completed drag-drop; attributes: from_idx, to_idx.
RowMovedEvent, EVT_ROW_MOVED = wx.lib.newevent.NewCommandEvent()

_TYPEAHEAD_TIMEOUT = 1.0  # seconds, matches native LISTBOX feel


class TrackTableView(wx.Window):
    """Custom-drawn table with list semantics for screen readers."""

    def __init__(self, parent: wx.Window, name: str | None = None):
        super().__init__(
            parent,
            style=wx.WANTS_CHARS | wx.VSCROLL | wx.BORDER_THEME,
            # Translators: Accessible name for the library list.
            name=name if name is not None else _("Library"),
        )
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self._items: list[dict] = []
        self._formatter: Callable[[dict], str] = format_track
        self._columns: list[ColumnSpec] = COLUMN_MODELS["tracks"]
        self._level_type = "tracks"
        self._sel = -1
        self._hover = -1
        self._top = 0  # first visible row index
        self._basket_ids: set[str] = set()
        self._empty_message = ""
        self._drag_enabled = False
        self._custom_columns: list[ColumnSpec] | None = None
        self._header_visible = True
        self._playing_row = -1
        self._last_user_activity = 0.0
        self._artwork = None  # ArtworkProvider, set by MainWindow

        self._typeahead = ""
        self._typeahead_time = 0.0

        # Drag-and-drop state: a press on a row arms a potential drag;
        # crossing the system drag threshold starts it.
        self._drag_origin: tuple[int, wx.Point] | None = None
        self._dragging = False
        self._drag_row = -1
        self._drop_gap = -1  # insertion point: 0..len(items)
        self._autoscroll_timer = wx.Timer(self)
        self._autoscroll_dir = 0

        self._theme = Theme(self)

        # The accessible must outlive any MSAA query; keep a hard
        # reference (GC of the accessible crashes the MSAA bridge).
        self._accessible = TrackTableAccessible(self)
        self.SetAccessible(self._accessible)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda e: None)
        self.Bind(wx.EVT_SET_FOCUS, self._on_focus)
        self.Bind(wx.EVT_KILL_FOCUS, self._on_kill_focus)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_CHAR, self._on_char)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_left_dclick)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)
        self.Bind(wx.EVT_TIMER, self._on_autoscroll, self._autoscroll_timer)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
        self.Bind(wx.EVT_SCROLLWIN, self._on_scrollwin)
        self.Bind(wx.EVT_SYS_COLOUR_CHANGED, self._on_theme_change)
        self.Bind(wx.EVT_DPI_CHANGED, self._on_theme_change)

    # ------------------------------------------------------------------
    # Data API

    def set_formatter(self, formatter: Callable[[dict], str]) -> None:
        """Change the screen reader / type-ahead formatter."""
        self._formatter = formatter

    def set_level_type(self, level_type: str) -> None:
        """Select the visual column model for the given level type."""
        self._level_type = level_type
        if self._custom_columns is None:
            self._columns = COLUMN_MODELS.get(level_type, COLUMN_MODELS["tracks"])
        self._clamp_top()
        self._update_scrollbar()
        self.Refresh()

    def set_columns(self, columns: "list[ColumnSpec] | None") -> None:
        """Override the column model (None restores the level type's)."""
        self._custom_columns = columns
        if columns is not None:
            self._columns = columns
        else:
            self._columns = COLUMN_MODELS.get(self._level_type, COLUMN_MODELS["tracks"])
        self.Refresh()

    def set_header_visible(self, visible: bool) -> None:
        """Hide the header band (e.g. for single-column dialog lists)."""
        self._header_visible = visible
        self._clamp_top()
        self._update_scrollbar()
        self.Refresh()

    def set_playing_row(self, row: int | None, follow: bool = True) -> None:
        """Visually mark the row as currently playing (no SR impact).

        With ``follow``, the view scrolls to keep the row centered —
        but only while the user has been idle, so it never fights
        manual scrolling or keyboard reading.
        """
        new = row if row is not None and 0 <= row < len(self._items) else -1
        if new == self._playing_row:
            return
        old = self._playing_row
        self._playing_row = new
        self._refresh_row(old)
        self._refresh_row(new)
        if follow and new >= 0 and time.monotonic() - self._last_user_activity > 4.0:
            self._top = new - self._visible_rows() // 2
            self._clamp_top()
            self._update_scrollbar()
            self.Refresh()

    def set_artwork_provider(self, provider) -> None:
        """Enable cover art thumbnails (tracks and albums views)."""
        self._artwork = provider
        self.Refresh()

    def _art_enabled(self) -> bool:
        return self._artwork is not None and self._level_type in (
            "tracks",
            "albums",
        )

    def _art_source(self, item: dict) -> tuple[str, str] | None:
        """Return (item_id, image_tag) to fetch art for, or None.

        Handles both DB-cache dicts (flat PrimaryImageTag) and raw API
        dicts (nested ImageTags), which appear during progressive
        loads.
        """
        tag = item.get("PrimaryImageTag") or (item.get("ImageTags") or {}).get(
            "Primary"
        )
        if tag:
            return item.get("Id", ""), tag
        album_tag = item.get("AlbumPrimaryImageTag")
        album_id = item.get("AlbumId")
        if album_tag and album_id:
            return album_id, album_tag
        return None

    def set_items(self, items: list[dict]) -> None:
        """Replace all items, preserving focus by Id."""
        old_id = self._get_focused_id()
        had_items = len(self._items) > 0

        self._items = items
        self._playing_row = -1

        if old_id and items:
            new_idx = self._find_by_id(old_id)
            if new_idx is not None:
                self._set_caret(new_idx, fire_events=False)
            else:
                self._set_caret(
                    min(max(self._sel, 0), len(items) - 1),
                    fire_events=False,
                )
        elif not had_items and items:
            self._set_caret(0, fire_events=False)
        elif not items:
            self._sel = -1

        self._hover = -1
        self._clamp_top()
        self._update_scrollbar()
        self.Refresh()

    def set_selection_by_id(self, item_id: str, fire_events: bool = True) -> None:
        """Set selection to the item with the given Id."""
        idx = self._find_by_id(item_id)
        if idx is not None:
            self._set_caret(idx, fire_events=fire_events)

    def get_selected_item(self) -> dict | None:
        """Get the currently selected item dict."""
        if 0 <= self._sel < len(self._items):
            return self._items[self._sel]
        return None

    def get_item(self, index: int) -> dict | None:
        """Get the item dict at the given index."""
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def GetSelection(self) -> int:
        return self._sel if self._sel >= 0 else wx.NOT_FOUND

    def SetSelection(self, index: int) -> None:
        if index == wx.NOT_FOUND:
            old = self._sel
            self._sel = -1
            if old >= 0:
                self._refresh_row(old)
            return
        if 0 <= index < len(self._items):
            self._set_caret(index)

    def GetCount(self) -> int:
        return len(self._items)

    # ------------------------------------------------------------------
    # New API

    def set_basket_ids(self, ids: set[str]) -> None:
        """Ids of tracks in the selection basket (drawn with a check)."""
        self._basket_ids = set(ids)
        self.Refresh()

    def set_empty_message(self, text: str) -> None:
        """Message painted (visually only) when the list is empty."""
        self._empty_message = text
        if not self._items:
            self.Refresh()

    def set_drag_enabled(self, enabled: bool) -> None:
        self._drag_enabled = enabled
        if not enabled:
            self.cancel_drag()

    def hit_test_row(self, pt: wx.Point) -> int:
        """Row index at the given client point, or -1."""
        y = pt.y - self._header_height()
        if y < 0:
            return -1
        row = self._top + y // self._row_height()
        if 0 <= row < len(self._items):
            return row
        return -1

    # ------------------------------------------------------------------
    # Data used by the accessible object

    def get_row_name(self, index: int) -> str:
        """Screen reader name for a row: the formatter string."""
        if 0 <= index < len(self._items):
            return self._formatter(self._items[index])
        return ""

    def get_row_count(self) -> int:
        return len(self._items)

    def get_row_screen_rect(self, index: int) -> wx.Rect:
        rect = self._row_rect(index)
        pos = self.ClientToScreen(rect.GetTopLeft())
        return wx.Rect(pos.x, pos.y, rect.width, rect.height)

    def is_row_offscreen(self, index: int) -> bool:
        last_visible = self._top + self._visible_rows() - 1
        return index < self._top or index > last_visible

    # ------------------------------------------------------------------
    # Geometry helpers

    def _row_height(self) -> int:
        # Rows grow to fit cover art thumbnails when art is shown.
        if self._art_enabled():
            return max(self._theme.row_height, self.FromDIP(40))
        return self._theme.row_height

    def _header_height(self) -> int:
        return self._theme.header_height if self._header_visible else 0

    def _art_size(self) -> int:
        return self._row_height() - self.FromDIP(6)

    def _visible_rows(self) -> int:
        h = self.GetClientSize().height - self._header_height()
        return max(1, h // self._row_height())

    def _row_rect(self, index: int) -> wx.Rect:
        y = self._header_height() + (index - self._top) * self._row_height()
        return wx.Rect(0, y, self.GetClientSize().width, self._row_height())

    def _basket_gutter(self) -> int:
        if self._level_type == "tracks":
            return self.FromDIP(24)
        return 0

    def _art_gutter(self) -> int:
        if self._art_enabled():
            return self._art_size() + self.FromDIP(6)
        return 0

    def _col_rects(self, width: int) -> list[tuple[ColumnSpec, int, int]]:
        """Compute (spec, x, width) for each column."""
        pad = self._theme.cell_padding
        x = self._basket_gutter() + self._art_gutter() + pad
        # Budget for the column widths themselves: everything except
        # the leading offset and one trailing pad per column.
        widths_avail = width - x - pad * len(self._columns)
        fixed_total = sum(
            self.FromDIP(c.fixed_dip) for c in self._columns if c.weight == 0
        )
        weight_total = sum(c.weight for c in self._columns) or 1
        flex_avail = max(0, widths_avail - fixed_total)
        result = []
        for col in self._columns:
            if col.weight == 0:
                w = self.FromDIP(col.fixed_dip)
            else:
                w = flex_avail * col.weight // weight_total
            result.append((col, x, max(0, w)))
            x += w + pad
        return result

    def _clamp_top(self) -> None:
        max_top = max(0, len(self._items) - self._visible_rows())
        self._top = min(max(0, self._top), max_top)

    def _update_scrollbar(self) -> None:
        visible = self._visible_rows()
        if len(self._items) > visible:
            self.SetScrollbar(wx.VERTICAL, self._top, visible, len(self._items), True)
        else:
            self.SetScrollbar(wx.VERTICAL, 0, 0, 0, True)

    def _refresh_row(self, index: int) -> None:
        if index < 0:
            return
        self.RefreshRect(self._row_rect(index))

    def ensure_visible(self, index: int) -> None:
        if not (0 <= index < len(self._items)):
            return
        visible = self._visible_rows()
        if index < self._top:
            self._top = index
        elif index >= self._top + visible:
            self._top = index - visible + 1
        self._clamp_top()
        self._update_scrollbar()
        self.Refresh()

    # ------------------------------------------------------------------
    # Caret / selection

    def _set_caret(self, index: int, fire_events: bool = True) -> None:
        index = min(max(0, index), len(self._items) - 1)
        if index < 0:
            return
        old = self._sel
        self._sel = index
        if old != index:
            self._refresh_row(old)
            self._refresh_row(index)
        self.ensure_visible(index)
        # Fire only on an actual caret move: a clamped move at the list
        # edges must stay silent, exactly like the native LISTBOX.
        if fire_events and old != index:
            self._fire_caret_events()

    def announce_view_change(self) -> None:
        """Announce the current view to the screen reader.

        Background refreshes (progressive loads, cache updates) are
        deliberately silent; MainWindow calls this after user-initiated
        navigation (drill in / go back) so the screen reader speaks the
        new list name and the focused item, matching a native LISTBOX
        rebuild.
        """
        if not self.HasFocus():
            return
        # Focus on the list itself first so its (freshly updated) name
        # is spoken, then on the caret row.
        wx.Accessible.NotifyEvent(wx.ACC_EVENT_OBJECT_FOCUS, self, wx.OBJID_CLIENT, 0)
        self._fire_caret_events()

    def _fire_caret_events(self) -> None:
        # Mirror native LISTBOX winevents; only meaningful (and only
        # announced by screen readers) while the control has focus.
        if self._sel < 0 or not self.HasFocus():
            return
        child = self._sel + 1
        wx.Accessible.NotifyEvent(
            wx.ACC_EVENT_OBJECT_FOCUS, self, wx.OBJID_CLIENT, child
        )
        wx.Accessible.NotifyEvent(
            wx.ACC_EVENT_OBJECT_SELECTION, self, wx.OBJID_CLIENT, child
        )

    def _get_focused_id(self) -> str | None:
        if 0 <= self._sel < len(self._items):
            return self._items[self._sel].get("Id")
        return None

    def _find_by_id(self, item_id: str) -> int | None:
        for i, item in enumerate(self._items):
            if item.get("Id") == item_id:
                return i
        return None

    # ------------------------------------------------------------------
    # Event handlers

    def _on_focus(self, event: wx.FocusEvent) -> None:
        if self._sel < 0 and self._items:
            self._sel = 0
        self._fire_caret_events()
        self.Refresh()
        event.Skip()

    def _on_kill_focus(self, event: wx.FocusEvent) -> None:
        self.Refresh()
        event.Skip()

    def _on_size(self, event: wx.SizeEvent) -> None:
        self._clamp_top()
        self._update_scrollbar()
        self.Refresh()
        event.Skip()

    def _on_theme_change(self, event: wx.Event) -> None:
        self._theme = Theme(self)
        self._update_scrollbar()
        self.Refresh()
        event.Skip()

    def _on_key_down(self, event: wx.KeyEvent) -> None:
        self._last_user_activity = time.monotonic()
        key = event.GetKeyCode()
        if key == wx.WXK_ESCAPE and self._dragging:
            self.cancel_drag()
            return
        if key == wx.WXK_TAB:
            self.HandleAsNavigationKey(event)
            return
        if not self._items:
            event.Skip()
            return
        sel = self._sel if self._sel >= 0 else 0
        page = self._visible_rows() - 1 or 1
        if key in (wx.WXK_DOWN, wx.WXK_NUMPAD_DOWN):
            self._set_caret(sel + 1)
        elif key in (wx.WXK_UP, wx.WXK_NUMPAD_UP):
            self._set_caret(sel - 1)
        elif key in (wx.WXK_HOME, wx.WXK_NUMPAD_HOME):
            self._set_caret(0)
        elif key in (wx.WXK_END, wx.WXK_NUMPAD_END):
            self._set_caret(len(self._items) - 1)
        elif key in (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN):
            self._set_caret(sel + page)
        elif key in (wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP):
            self._set_caret(sel - page)
        else:
            event.Skip()

    def _on_char(self, event: wx.KeyEvent) -> None:
        self._last_user_activity = time.monotonic()
        code = event.GetUnicodeKey()
        if code == wx.WXK_NONE or code < 32:
            event.Skip()
            return
        if event.ControlDown() or event.AltDown():
            event.Skip()
            return
        ch = chr(code).casefold()
        now = time.monotonic()
        if now - self._typeahead_time > _TYPEAHEAD_TIMEOUT:
            self._typeahead = ""
        self._typeahead_time = now

        # Native LISTBOX behavior: repeating the same single char
        # cycles through entries starting with it.
        if self._typeahead and self._typeahead == ch * len(self._typeahead):
            self._typeahead += ch
            self._typeahead_jump(ch, cycle=True)
        else:
            self._typeahead += ch
            self._typeahead_jump(self._typeahead, cycle=False)

    def _typeahead_jump(self, prefix: str, cycle: bool) -> None:
        n = len(self._items)
        if n == 0:
            return
        start = (self._sel + 1) % n if cycle else max(self._sel, 0)
        for offset in range(n):
            idx = (start + offset) % n
            name = self._formatter(self._items[idx]).casefold()
            if name.startswith(prefix):
                if idx != self._sel:
                    self._set_caret(idx)
                return

    def _on_left_down(self, event: wx.MouseEvent) -> None:
        self._last_user_activity = time.monotonic()
        self.SetFocus()
        row = self.hit_test_row(event.GetPosition())
        if row < 0:
            return
        if event.ControlDown() and event.ShiftDown():
            anchor = self._sel if self._sel >= 0 else row
            lo, hi = min(anchor, row), max(anchor, row)
            evt = RowRangeClickEvent(self.GetId())
            evt.SetEventObject(self)
            evt.items = self._items[lo : hi + 1]
            self._set_caret(row)
            self.GetEventHandler().ProcessEvent(evt)
        elif event.ControlDown():
            self._set_caret(row)
            evt = RowCtrlClickEvent(self.GetId())
            evt.SetEventObject(self)
            evt.item = self._items[row]
            self.GetEventHandler().ProcessEvent(evt)
        else:
            self._set_caret(row)
            if self._drag_enabled:
                self._drag_origin = (row, event.GetPosition())

    def _on_left_up(self, event: wx.MouseEvent) -> None:
        if self._dragging:
            self._finish_drag(drop=True)
        self._drag_origin = None

    def _on_left_dclick(self, event: wx.MouseEvent) -> None:
        row = self.hit_test_row(event.GetPosition())
        if row < 0:
            return
        self._set_caret(row)
        evt = wx.CommandEvent(wx.wxEVT_LISTBOX_DCLICK, self.GetId())
        evt.SetEventObject(self)
        evt.SetInt(row)
        self.GetEventHandler().ProcessEvent(evt)

    def _on_motion(self, event: wx.MouseEvent) -> None:
        pos = event.GetPosition()
        if self._dragging:
            self._update_drop_gap(pos)
            self._update_autoscroll(pos)
            return
        origin = self._drag_origin
        if (
            origin is not None
            and event.LeftIsDown()
            and self._past_drag_threshold(origin[1], pos)
        ):
            self._start_drag(origin[0])
            return
        row = self.hit_test_row(pos)
        if row != self._hover:
            old = self._hover
            self._hover = row
            self._refresh_row(old)
            self._refresh_row(row)

    def _on_leave(self, event: wx.MouseEvent) -> None:
        if self._hover >= 0:
            old = self._hover
            self._hover = -1
            self._refresh_row(old)

    # ------------------------------------------------------------------
    # Drag and drop (internal reorder)

    def _past_drag_threshold(self, origin: wx.Point, pos: wx.Point) -> bool:
        return abs(pos.x - origin.x) > wx.SystemSettings.GetMetric(
            wx.SYS_DRAG_X
        ) or abs(pos.y - origin.y) > wx.SystemSettings.GetMetric(wx.SYS_DRAG_Y)

    def _start_drag(self, row: int) -> None:
        self._dragging = True
        self._drag_row = row
        self._drop_gap = -1
        if self._hover >= 0:
            old = self._hover
            self._hover = -1
            self._refresh_row(old)
        self.CaptureMouse()
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))

    def _update_drop_gap(self, pos: wx.Point) -> None:
        gap = self._top + round((pos.y - self._header_height()) / self._row_height())
        gap = min(max(0, gap), len(self._items))
        if gap != self._drop_gap:
            self._drop_gap = gap
            self.Refresh()

    def _update_autoscroll(self, pos: wx.Point) -> None:
        height = self.GetClientSize().height
        if pos.y < self._header_height() + self._row_height() // 2:
            direction = -1
        elif pos.y > height - self._row_height() // 2:
            direction = 1
        else:
            direction = 0
        if direction != self._autoscroll_dir:
            self._autoscroll_dir = direction
            if direction:
                self._autoscroll_timer.Start(120)
            else:
                self._autoscroll_timer.Stop()

    def _on_autoscroll(self, event: wx.TimerEvent) -> None:
        if not self._dragging or not self._autoscroll_dir:
            self._autoscroll_timer.Stop()
            return
        self._top += self._autoscroll_dir
        self._clamp_top()
        self._update_scrollbar()
        self._update_drop_gap(self.ScreenToClient(wx.GetMousePosition()))
        self.Refresh()

    def _finish_drag(self, drop: bool) -> None:
        from_idx = self._drag_row
        gap = self._drop_gap
        self._dragging = False
        self._drag_origin = None
        self._drag_row = -1
        self._drop_gap = -1
        self._autoscroll_dir = 0
        self._autoscroll_timer.Stop()
        if self.HasCapture():
            self.ReleaseMouse()
        self.SetCursor(wx.NullCursor)
        self.Refresh()
        if not drop or gap < 0 or from_idx < 0:
            return
        # An insertion gap above the removed row keeps its index; one
        # below shifts up by the removed row.
        to_idx = gap if gap <= from_idx else gap - 1
        if to_idx == from_idx:
            return
        evt = RowMovedEvent(self.GetId())
        evt.SetEventObject(self)
        evt.from_idx = from_idx
        evt.to_idx = to_idx
        self.GetEventHandler().ProcessEvent(evt)

    def cancel_drag(self) -> None:
        """Cancel an in-progress drag without dropping."""
        if self._dragging:
            self._finish_drag(drop=False)
        self._drag_origin = None

    def _on_capture_lost(self, event: wx.MouseCaptureLostEvent) -> None:
        self.cancel_drag()

    def _on_wheel(self, event: wx.MouseEvent) -> None:
        self._last_user_activity = time.monotonic()
        lines = -event.GetWheelRotation() // event.GetWheelDelta() * 3
        if lines:
            self._top += lines
            self._clamp_top()
            self._update_scrollbar()
            self.Refresh()

    def _on_scrollwin(self, event: wx.ScrollWinEvent) -> None:
        self._last_user_activity = time.monotonic()
        evt_type = event.GetEventType()
        visible = self._visible_rows()
        if evt_type == wx.wxEVT_SCROLLWIN_LINEUP:
            self._top -= 1
        elif evt_type == wx.wxEVT_SCROLLWIN_LINEDOWN:
            self._top += 1
        elif evt_type == wx.wxEVT_SCROLLWIN_PAGEUP:
            self._top -= visible
        elif evt_type == wx.wxEVT_SCROLLWIN_PAGEDOWN:
            self._top += visible
        elif evt_type == wx.wxEVT_SCROLLWIN_TOP:
            self._top = 0
        elif evt_type == wx.wxEVT_SCROLLWIN_BOTTOM:
            self._top = len(self._items)
        else:  # thumb track / release
            self._top = event.GetPosition()
        self._clamp_top()
        self._update_scrollbar()
        self.Refresh()

    # ------------------------------------------------------------------
    # Painting

    def _on_paint(self, event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        theme = self._theme
        size = self.GetClientSize()

        dc.SetBackground(wx.Brush(theme.window_bg))
        dc.Clear()

        cols = self._col_rects(size.width)
        if self._header_visible:
            self._draw_header(dc, size, cols)

        if not self._items:
            self._draw_empty_message(dc, size)
            return

        first = self._top
        last = min(len(self._items), first + self._visible_rows() + 1)
        for row in range(first, last):
            self._draw_row(dc, row, cols)

        if self._dragging and self._drop_gap >= 0:
            self._draw_insertion_line(dc, size)

    def _draw_insertion_line(self, dc: wx.DC, size: wx.Size) -> None:
        theme = self._theme
        y = self._header_height() + (self._drop_gap - self._top) * self._row_height()
        y = min(max(self._header_height(), y), size.height - 1)
        dc.SetPen(wx.Pen(theme.accent, self.FromDIP(2)))
        dc.DrawLine(0, y, size.width, y)

    def _draw_header(
        self,
        dc: wx.DC,
        size: wx.Size,
        cols: list[tuple[ColumnSpec, int, int]],
    ) -> None:
        theme = self._theme
        header_rect = wx.Rect(0, 0, size.width, theme.header_height)
        dc.SetBrush(wx.Brush(theme.header_bg))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(header_rect)
        dc.SetPen(wx.Pen(theme.grid_line))
        dc.DrawLine(
            0,
            theme.header_height - 1,
            size.width,
            theme.header_height - 1,
        )
        dc.SetFont(theme.header_font)
        dc.SetTextForeground(theme.header_text)
        for spec, x, w in cols:
            if w <= 0:
                continue
            label = wx.Control.Ellipsize(spec.heading(), dc, wx.ELLIPSIZE_END, w)
            tw, th = dc.GetTextExtent(label)
            tx = x + (w - tw if spec.align == wx.ALIGN_RIGHT else 0)
            dc.DrawText(label, tx, (theme.header_height - th) // 2)

    def _draw_art(self, dc: wx.DC, rect: wx.Rect, item: dict) -> None:
        """Draw the row's cover art thumbnail or a placeholder."""
        theme = self._theme
        size = self._art_size()
        x = rect.x + self._basket_gutter()
        y = rect.y + (rect.height - size) // 2

        source = self._art_source(item)
        provider = self._artwork
        bmp = None
        if source is not None and provider is not None:
            item_id, tag = source
            bmp = provider.get_cached(item_id, tag, size)
            if bmp is None and not provider.is_negative(item_id, tag, size):
                provider.request(
                    item_id,
                    tag,
                    size,
                    lambda: self.Refresh() if self else None,
                )
        if bmp is not None:
            dc.DrawBitmap(
                bmp,
                x + (size - bmp.GetWidth()) // 2,
                y + (size - bmp.GetHeight()) // 2,
                True,
            )
            return

        # Placeholder: rounded rect with a note glyph.
        dc.SetBrush(wx.Brush(theme.header_bg))
        dc.SetPen(wx.Pen(theme.grid_line))
        dc.DrawRoundedRectangle(x, y, size, size, self.FromDIP(3))
        dc.SetFont(theme.font)
        dc.SetTextForeground(theme.secondary_text)
        note = "♪"
        tw, th = dc.GetTextExtent(note)
        dc.DrawText(note, x + (size - tw) // 2, y + (size - th) // 2)

    def _draw_row(
        self,
        dc: wx.DC,
        row: int,
        cols: list[tuple[ColumnSpec, int, int]],
    ) -> None:
        theme = self._theme
        rect = self._row_rect(row)
        item = self._items[row]
        focused = self.HasFocus()

        if row == self._sel:
            bg = theme.selection_bg if focused else theme.unfocused_selection_bg
            fg = theme.selection_text if focused else theme.unfocused_selection_text
            secondary = fg
        elif row == self._hover:
            bg = theme.hover_bg
            fg = theme.hover_text
            secondary = (
                theme.hover_text if theme.high_contrast else theme.secondary_text
            )
        else:
            bg = theme.window_bg
            fg = theme.text
            secondary = theme.secondary_text

        dc.SetBrush(wx.Brush(bg))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(rect)

        # Currently-playing marker: accent text + accent bar at the
        # left edge (visual only; never exposed to screen readers).
        if row == self._playing_row and row != self._sel:
            if not theme.high_contrast:
                fg = theme.accent
                secondary = theme.accent
            dc.SetPen(wx.Pen(theme.accent, self.FromDIP(3)))
            dc.DrawLine(
                rect.x + 1,
                rect.y + 2,
                rect.x + 1,
                rect.y + rect.height - 2,
            )

        gutter = self._basket_gutter()
        if gutter and item.get("Id") in self._basket_ids:
            dc.SetPen(wx.Pen(theme.accent, self.FromDIP(3)))
            dc.DrawLine(
                rect.x + 1,
                rect.y + 2,
                rect.x + 1,
                rect.y + rect.height - 2,
            )
            dc.SetFont(theme.font)
            dc.SetTextForeground(fg)
            check = "✓"
            tw, th = dc.GetTextExtent(check)
            dc.DrawText(
                check,
                rect.x + (gutter - tw) // 2,
                rect.y + (rect.height - th) // 2,
            )

        if self._art_enabled():
            self._draw_art(dc, rect, item)

        dc.SetFont(theme.font)
        for spec, x, w in cols:
            if w <= 0:
                continue
            text = spec.cell(item)
            if not text:
                continue
            dc.SetTextForeground(secondary if spec.secondary else fg)
            label = wx.Control.Ellipsize(text, dc, wx.ELLIPSIZE_END, w)
            tw, th = dc.GetTextExtent(label)
            tx = x + (w - tw if spec.align == wx.ALIGN_RIGHT else 0)
            dc.DrawText(label, tx, rect.y + (rect.height - th) // 2)

        if row == self._sel and focused:
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.SetPen(wx.Pen(theme.selection_text, 1, wx.PENSTYLE_USER_DASH))
            dc.DrawRectangle(rect.x, rect.y, rect.width - 1, rect.height - 1)

    def _draw_empty_message(self, dc: wx.DC, size: wx.Size) -> None:
        if not self._empty_message:
            return
        theme = self._theme
        dc.SetFont(theme.font)
        dc.SetTextForeground(theme.secondary_text)
        tw, th = dc.GetTextExtent(self._empty_message)
        y_area = size.height - self._header_height()
        dc.DrawText(
            self._empty_message,
            max(0, (size.width - tw) // 2),
            self._header_height() + max(0, (y_area - th) // 2),
        )

    # ------------------------------------------------------------------

    def DoGetBestSize(self) -> wx.Size:
        return self.FromDIP(wx.Size(400, 200))

    def AcceptsFocusFromKeyboard(self) -> bool:
        return True

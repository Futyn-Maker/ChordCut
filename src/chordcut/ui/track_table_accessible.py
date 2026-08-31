"""MSAA accessible object for TrackTableView.

Exposes the custom-drawn table to screen readers as a plain list
(ROLE_SYSTEM_LIST) of items (ROLE_SYSTEM_LISTITEM) whose names come
from the same formatters as the native LISTBOX, so NVDA/JAWS
announcements match the classic list exactly.

childId convention (MSAA): 0 = the list itself, 1..N = rows.

Note on override signatures: Phoenix generates the virtual-call bridge
from the C++ out-parameter signatures and the exact Python shapes are
not documented; every override logs its arguments when DEBUG_LOG is
enabled so mismatches surface immediately.
"""

import logging

import wx

logger = logging.getLogger(__name__)

# Set True to trace every MSAA call a screen reader makes.
DEBUG_LOG = False


def _log(method: str, args: tuple, result: object) -> None:
    if DEBUG_LOG:
        logger.info("MSAA %s%r -> %r", method, args, result)


class TrackTableAccessible(wx.Accessible):
    """Presents TrackTableView as a simple MSAA list."""

    def __init__(self, table: wx.Window):
        super().__init__(table)
        self._table = table

    # -- identity ------------------------------------------------------

    def GetName(self, childId):
        if childId == 0:
            result = (wx.ACC_OK, self._table.GetName())
        else:
            name = self._table.get_row_name(childId - 1)
            if name:
                result = (wx.ACC_OK, name)
            else:
                result = (wx.ACC_INVALID_ARG, "")
        _log("GetName", (childId,), result)
        return result

    def GetRole(self, childId):
        if childId == 0:
            result = (wx.ACC_OK, wx.ROLE_SYSTEM_LIST)
        else:
            result = (wx.ACC_OK, wx.ROLE_SYSTEM_LISTITEM)
        _log("GetRole", (childId,), result)
        return result

    def GetChildCount(self):
        result = (wx.ACC_OK, self._table.get_row_count())
        _log("GetChildCount", (), result)
        return result

    def GetChild(self, childId):
        # None => the child is an element of this object (no separate
        # IAccessible), which is exactly how native LISTBOX items work.
        if childId == 0:
            result = (wx.ACC_OK, None)
        elif 1 <= childId <= self._table.get_row_count():
            result = (wx.ACC_OK, None)
        else:
            result = (wx.ACC_FAIL, None)
        _log("GetChild", (childId,), result)
        return result

    # -- geometry ------------------------------------------------------

    def GetLocation(self, elementId):
        if elementId == 0:
            result = (wx.ACC_OK, self._table.GetScreenRect())
        elif 1 <= elementId <= self._table.get_row_count():
            result = (
                wx.ACC_OK,
                self._table.get_row_screen_rect(elementId - 1),
            )
        else:
            result = (wx.ACC_INVALID_ARG, wx.Rect())
        _log("GetLocation", (elementId,), result)
        return result

    def HitTest(self, pt, *args):
        client = self._table.ScreenToClient(wx.Point(pt.x, pt.y))
        size = self._table.GetClientSize()
        if not wx.Rect(0, 0, size.width, size.height).Contains(client):
            result = (wx.ACC_FALSE, 0, None)
        else:
            row = self._table.hit_test_row(client)
            result = (wx.ACC_OK, row + 1 if row >= 0 else 0, None)
        _log("HitTest", (pt, *args), result)
        return result

    # -- state / focus / selection ------------------------------------

    def GetState(self, childId):
        focused = self._table.HasFocus()
        if childId == 0:
            state = wx.ACC_STATE_SYSTEM_FOCUSABLE
            if focused:
                state |= wx.ACC_STATE_SYSTEM_FOCUSED
            result = (wx.ACC_OK, state)
        elif 1 <= childId <= self._table.get_row_count():
            state = wx.ACC_STATE_SYSTEM_SELECTABLE | wx.ACC_STATE_SYSTEM_FOCUSABLE
            if childId - 1 == self._table.GetSelection():
                state |= wx.ACC_STATE_SYSTEM_SELECTED
                if focused:
                    state |= wx.ACC_STATE_SYSTEM_FOCUSED
            if self._table.is_row_offscreen(childId - 1):
                # Native LISTBOX marks scrolled-out items with both.
                state |= wx.ACC_STATE_SYSTEM_OFFSCREEN | wx.ACC_STATE_SYSTEM_INVISIBLE
            result = (wx.ACC_OK, state)
        else:
            result = (wx.ACC_INVALID_ARG, 0)
        _log("GetState", (childId,), result)
        return result

    def GetFocus(self, *args):
        sel = self._table.GetSelection()
        if self._table.HasFocus() and sel != wx.NOT_FOUND:
            result = (wx.ACC_OK, sel + 1, None)
        elif self._table.HasFocus():
            result = (wx.ACC_OK, 0, None)
        else:
            result = (wx.ACC_FALSE, 0, None)
        _log("GetFocus", args, result)
        return result

    def GetSelections(self):
        sel = self._table.GetSelection()
        if sel != wx.NOT_FOUND:
            result = (wx.ACC_OK, sel + 1)
        else:
            result = (wx.ACC_FALSE, 0)
        _log("GetSelections", (), result)
        return result

    def Navigate(self, navDir, fromId, *args):
        count = self._table.get_row_count()
        to_id = None
        if navDir in (wx.NAVDIR_FIRSTCHILD,):
            to_id = 1 if count else None
        elif navDir in (wx.NAVDIR_LASTCHILD,):
            to_id = count if count else None
        elif navDir in (wx.NAVDIR_DOWN, wx.NAVDIR_NEXT):
            if 1 <= fromId < count:
                to_id = fromId + 1
        elif navDir in (wx.NAVDIR_UP, wx.NAVDIR_PREVIOUS):
            if 2 <= fromId <= count:
                to_id = fromId - 1
        if to_id is None:
            result = (wx.ACC_FALSE, 0, None)
        else:
            result = (wx.ACC_OK, to_id, None)
        _log("Navigate", (navDir, fromId, *args), result)
        return result

    # -- explicitly not implemented (parity with native LISTBOX) ------

    def GetValue(self, childId):
        return (wx.ACC_NOT_IMPLEMENTED, "")

    def GetDescription(self, childId):
        return (wx.ACC_NOT_IMPLEMENTED, "")

    def GetHelpText(self, childId):
        return (wx.ACC_NOT_IMPLEMENTED, "")

    def GetKeyboardShortcut(self, childId):
        return (wx.ACC_NOT_IMPLEMENTED, "")

    def GetDefaultAction(self, childId):
        return (wx.ACC_NOT_IMPLEMENTED, "")

    def DoDefaultAction(self, childId):
        return wx.ACC_NOT_IMPLEMENTED

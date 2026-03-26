"""Lyrics dialogs for ChordCut."""

from typing import Callable

import wx

from chordcut.i18n import _
from chordcut.player.mpv_player import format_duration


class PlainLyricsDialog(wx.Dialog):
    """Read-only text display for plain lyrics."""

    def __init__(
        self,
        parent: wx.Window,
        title: str,
        text: str,
    ):
        super().__init__(
            parent,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(500, 400),
        )

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self._text_ctrl = wx.TextCtrl(
            panel,
            value=text,
            style=(
                wx.TE_MULTILINE
                | wx.TE_READONLY
                | wx.TE_RICH2
            ),
            name=title,
        )
        sizer.Add(
            self._text_ctrl, 1,
            wx.EXPAND | wx.ALL, 10,
        )

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        copy_btn = wx.Button(
            panel,
            wx.ID_COPY,
            # Translators: Copy button in lyrics dialog.
            _("&Copy"),
        )
        close_btn = wx.Button(panel, wx.ID_CLOSE)
        btn_sizer.Add(copy_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(close_btn, 0)
        sizer.Add(
            btn_sizer, 0,
            wx.ALIGN_CENTER | wx.BOTTOM, 10,
        )

        panel.SetSizer(sizer)

        copy_btn.Bind(
            wx.EVT_BUTTON, self._on_copy,
        )
        close_btn.Bind(
            wx.EVT_BUTTON, lambda e: self.Close(),
        )
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_copy(self, event: wx.CommandEvent) -> None:
        text = self._text_ctrl.GetValue()
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(
                wx.TextDataObject(text),
            )
            wx.TheClipboard.Close()

    def _on_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()


class SyncedLyricsDialog(wx.Dialog):
    """Interactive synced lyrics with seek support.

    Player controls work inside this dialog:
    - Escape: pause/resume (does NOT close)
    - Ctrl+Up/Down: volume
    - Ctrl+Right/Left: seek ±10s
    - Enter: play from the selected lyric timestamp
    """

    def __init__(
        self,
        parent: wx.Window,
        title: str,
        lyrics: list[dict],
        play_from_callback: Callable[[int], None],
        pause_callback: Callable[[], None],
        seek_callback: Callable[[float], None],
        volume_up_callback: Callable[[], None],
        volume_down_callback: Callable[[], None],
    ):
        super().__init__(
            parent,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(500, 450),
        )

        self._lyrics = lyrics
        self._play_from = play_from_callback
        self._pause = pause_callback
        self._seek = seek_callback
        self._volume_up = volume_up_callback
        self._volume_down = volume_down_callback

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self._list = wx.ListBox(
            panel,
            style=wx.LB_SINGLE,
            name=title,
        )

        # Format: "Text [MM:SS]"
        lines = []
        for cue in lyrics:
            start = cue.get("Start", 0) or 0
            text = cue.get("Text", "")
            ts = format_duration(start / 10_000_000)
            lines.append("{text} [{ts}]".format(
                text=text, ts=ts,
            ))
        self._list.Set(lines)
        if lines:
            self._list.SetSelection(0)

        sizer.Add(
            self._list, 1,
            wx.EXPAND | wx.ALL, 10,
        )

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        copy_all_btn = wx.Button(
            panel,
            wx.ID_ANY,
            # Translators: Copy all button in synced lyrics.
            _("Copy &All"),
        )
        close_btn = wx.Button(panel, wx.ID_CLOSE)
        btn_sizer.Add(copy_all_btn, 0, wx.RIGHT, 5)
        btn_sizer.Add(close_btn, 0)
        sizer.Add(
            btn_sizer, 0,
            wx.ALIGN_CENTER | wx.BOTTOM, 10,
        )

        panel.SetSizer(sizer)

        copy_all_btn.Bind(
            wx.EVT_BUTTON, self._on_copy_all,
        )
        close_btn.Bind(
            wx.EVT_BUTTON, lambda e: self.Close(),
        )
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_key(self, event: wx.KeyEvent) -> None:
        code = event.GetKeyCode()
        ctrl = event.ControlDown()

        # Escape = pause/resume (NOT close)
        if code == wx.WXK_ESCAPE:
            self._pause()
            return

        # Backspace = close dialog
        if code == wx.WXK_BACK:
            self.Close()
            return

        # Enter = play from selected timestamp
        if code in (
            wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER,
        ):
            idx = self._list.GetSelection()
            if idx != wx.NOT_FOUND:
                cue = self._lyrics[idx]
                start = cue.get("Start", 0) or 0
                self._play_from(start)
            return

        # Ctrl+C = copy selected line text
        if ctrl and code == ord("C"):
            idx = self._list.GetSelection()
            if idx != wx.NOT_FOUND:
                cue = self._lyrics[idx]
                text = cue.get("Text", "")
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(
                        wx.TextDataObject(text),
                    )
                    wx.TheClipboard.Close()
            return

        # Ctrl+Up/Down = volume
        if ctrl and code == wx.WXK_UP:
            self._volume_up()
            return
        if ctrl and code == wx.WXK_DOWN:
            self._volume_down()
            return

        # Ctrl+Right/Left = seek ±10s
        if ctrl and code == wx.WXK_RIGHT:
            self._seek(10)
            return
        if ctrl and code == wx.WXK_LEFT:
            self._seek(-10)
            return

        event.Skip()

    def _on_copy_all(
        self, event: wx.CommandEvent,
    ) -> None:
        """Copy all lyrics with timestamps."""
        lines = []
        for cue in self._lyrics:
            start = cue.get("Start", 0) or 0
            text = cue.get("Text", "")
            ts = format_duration(start / 10_000_000)
            lines.append("{text} [{ts}]".format(
                text=text, ts=ts,
            ))
        full_text = "\n".join(lines)
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(
                wx.TextDataObject(full_text),
            )
            wx.TheClipboard.Close()

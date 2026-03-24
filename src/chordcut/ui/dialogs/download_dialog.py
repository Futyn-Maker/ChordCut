"""Download dialog with progress bar."""

import threading
import urllib.request
from pathlib import Path

import wx

from chordcut.i18n import _
from chordcut.utils.paths import get_app_dir


class DownloadDialog(wx.Dialog):
    """Dialog showing download progress."""

    def __init__(
        self,
        parent: wx.Window,
        title: str,
        url: str,
        filename: str,
        download_dir: Path | None = None,
    ):
        super().__init__(
            parent,
            title=title,
            style=wx.DEFAULT_DIALOG_STYLE,
            size=(400, 150),
        )

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self._label = wx.StaticText(
            panel,
            # Translators: Download progress label.
            label=_("Downloading..."),
        )
        sizer.Add(self._label, 0, wx.ALL, 10)

        self._gauge = wx.Gauge(
            panel,
            range=100,
            # Translators: Download progress bar name.
            name=_("Download progress"),
        )
        sizer.Add(
            self._gauge, 0,
            wx.EXPAND | wx.LEFT | wx.RIGHT, 10,
        )

        # Translators: Cancel download button.
        self._cancel_btn = wx.Button(
            panel, wx.ID_CANCEL, _("Cancel"),
        )
        sizer.Add(
            self._cancel_btn, 0,
            wx.ALIGN_CENTER | wx.ALL, 10,
        )

        panel.SetSizer(sizer)

        self._url = url
        self._filename = filename
        self._download_dir = download_dir
        self._cancelled = False
        self._thread: threading.Thread | None = None

        self._cancel_btn.Bind(
            wx.EVT_BUTTON, self._on_cancel,
        )
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        self._start_download()

    def _start_download(self) -> None:
        music_dir = (
            self._download_dir
            if self._download_dir is not None
            else get_app_dir() / "music"
        )
        music_dir.mkdir(parents=True, exist_ok=True)

        self._thread = threading.Thread(
            target=self._download_thread,
            args=(music_dir,),
            daemon=True,
        )
        self._thread.start()

    def _download_thread(self, music_dir: Path) -> None:
        try:
            req = urllib.request.urlopen(self._url)
            total = int(
                req.headers.get("Content-Length", 0),
            )

            # Determine extension from Content-Type
            ct = req.headers.get(
                "Content-Type", "",
            )
            ext = ""
            if "flac" in ct:
                ext = ".flac"
            elif "mpeg" in ct or "mp3" in ct:
                ext = ".mp3"
            elif "ogg" in ct:
                ext = ".ogg"
            elif "wav" in ct:
                ext = ".wav"
            elif "aac" in ct:
                ext = ".aac"
            elif "mp4" in ct or "m4a" in ct:
                ext = ".m4a"

            dest = music_dir / (self._filename + ext)
            downloaded = 0

            with open(dest, "wb") as f:
                while not self._cancelled:
                    chunk = req.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(
                            downloaded * 100 / total,
                        )
                        wx.CallAfter(
                            self._update_progress, pct,
                        )

            if self._cancelled:
                dest.unlink(missing_ok=True)
                wx.CallAfter(
                    self.EndModal, wx.ID_CANCEL,
                )
            else:
                wx.CallAfter(self._on_complete)

        except Exception as e:
            wx.CallAfter(self._on_error, str(e))

    def _update_progress(self, pct: int) -> None:
        if self.IsShown():
            self._gauge.SetValue(min(pct, 100))
            self._label.SetLabel(
                # Translators: Download progress with percent.
                _("Downloading... {pct}%").format(
                    pct=pct,
                )
            )

    def _on_complete(self) -> None:
        # Translators: Download complete label.
        self._label.SetLabel(_("Download complete"))
        self.EndModal(wx.ID_OK)

    def _on_error(self, msg: str) -> None:
        wx.MessageBox(
            msg,
            # Translators: Download error dialog title.
            _("Download Error"),
            wx.OK | wx.ICON_ERROR,
            self,
        )
        self.EndModal(wx.ID_CANCEL)

    def _on_cancel(
        self, event: wx.CommandEvent,
    ) -> None:
        self._cancelled = True

    def _on_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self._cancelled = True
            return
        event.Skip()

    def _on_close(self, event: wx.CloseEvent) -> None:
        self._cancelled = True
        event.Skip()

"""Settings dialog for ChordCut."""

import wx

from chordcut.i18n import _
from chordcut.settings import Settings


class SettingsDialog(wx.Dialog):
    """Dialog for configuring application settings."""

    def __init__(self, parent: wx.Window, settings: Settings):
        super().__init__(
            parent,
            # Translators: Title of the settings dialog.
            title=_("Settings"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(500, 460),
        )

        self._settings = settings

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---- Download folder ----------------------------------------
        folder_label = wx.StaticText(
            panel,
            # Translators: Label for download folder picker.
            label=_("Download &folder:"),
        )
        main_sizer.Add(
            folder_label,
            flag=wx.LEFT | wx.RIGHT | wx.TOP,
            border=10,
        )

        # Plain text field + labeled button instead of wx.DirPickerCtrl:
        # the picker is a composite whose inner text field and button
        # get no accessible labels, so screen readers announce them as
        # nameless controls.
        folder_row = wx.BoxSizer(wx.HORIZONTAL)
        self._folder_text = wx.TextCtrl(
            panel,
            value=str(settings.download_dir),
            # Translators: Accessible name for download folder field.
            name=_("Download folder"),
        )
        browse_btn = wx.Button(
            panel,
            # Translators: Button that opens the folder browser.
            label=_("&Browse..."),
        )
        browse_btn.Bind(wx.EVT_BUTTON, self._on_browse_folder)
        folder_row.Add(self._folder_text, proportion=1, flag=wx.RIGHT, border=5)
        folder_row.Add(browse_btn)
        main_sizer.Add(
            folder_row,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=10,
        )

        # ---- Player settings group ----------------------------------
        player_box = wx.StaticBox(
            panel,
            # Translators: Label for the player settings group box.
            label=_("Player settings"),
        )
        player_sizer = wx.StaticBoxSizer(
            player_box,
            wx.VERTICAL,
        )

        # Volume step
        vol_row = wx.BoxSizer(wx.HORIZONTAL)
        vol_label = wx.StaticText(
            panel,
            # Translators: Label for volume step spin control.
            label=_("&Volume step for hotkeys and wheel (%):"),
        )
        self._volume_step = wx.SpinCtrl(
            panel,
            min=1,
            max=20,
            initial=settings.volume_step,
            # Translators: Accessible name for volume step field.
            name=_("Volume step"),
        )
        vol_row.Add(
            vol_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        vol_row.Add(self._volume_step)
        player_sizer.Add(vol_row, flag=wx.ALL, border=5)

        # Seek step
        seek_row = wx.BoxSizer(wx.HORIZONTAL)
        seek_label = wx.StaticText(
            panel,
            # Translators: Label for seek step spin control.
            label=_("&Seek step for hotkeys and wheel (seconds):"),
        )
        self._seek_step = wx.SpinCtrl(
            panel,
            min=1,
            max=60,
            initial=settings.seek_step,
            # Translators: Accessible name for seek step field.
            name=_("Seek step"),
        )
        seek_row.Add(
            seek_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        seek_row.Add(self._seek_step)
        player_sizer.Add(seek_row, flag=wx.ALL, border=5)

        # Remember volume checkbox
        self._remember_volume = wx.CheckBox(
            panel,
            # Translators: Checkbox to save volume on exit.
            label=_("Remember &volume level on exit"),
        )
        self._remember_volume.SetValue(settings.remember_volume)
        player_sizer.Add(
            self._remember_volume,
            flag=wx.ALL,
            border=5,
        )

        # Remember device checkbox
        self._remember_device = wx.CheckBox(
            panel,
            # Translators: Checkbox to save audio device on exit.
            label=_("Remember output &device on exit"),
        )
        self._remember_device.SetValue(settings.remember_device)
        player_sizer.Add(
            self._remember_device,
            flag=wx.ALL,
            border=5,
        )

        main_sizer.Add(
            player_sizer,
            flag=wx.EXPAND | wx.ALL,
            border=10,
        )

        # ---- Behavior settings group --------------------------------
        behavior_box = wx.StaticBox(
            panel,
            # Translators: Label for the behavior settings group box.
            label=_("Behavior"),
        )
        behavior_sizer = wx.StaticBoxSizer(
            behavior_box,
            wx.VERTICAL,
        )

        self._close_to_tray = wx.CheckBox(
            panel,
            # Translators: Checkbox to minimize to tray on close.
            label=_("&Close button minimizes to tray instead of exiting"),
        )
        self._close_to_tray.SetValue(settings.close_to_tray)
        behavior_sizer.Add(
            self._close_to_tray,
            flag=wx.ALL,
            border=5,
        )

        self._check_updates = wx.CheckBox(
            panel,
            # Translators: Checkbox to enable automatic update checks.
            label=_("Check for &updates on startup"),
        )
        self._check_updates.SetValue(settings.check_updates)
        behavior_sizer.Add(
            self._check_updates,
            flag=wx.ALL,
            border=5,
        )

        self._global_hotkeys = wx.CheckBox(
            panel,
            # Translators: Checkbox to enable system-wide hotkeys that
            # work while another application is focused.
            label=_("&Global hotkeys (control playback from any application)"),
        )
        self._global_hotkeys.SetValue(settings.global_hotkeys)
        behavior_sizer.Add(
            self._global_hotkeys,
            flag=wx.ALL,
            border=5,
        )

        main_sizer.Add(
            behavior_sizer,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=10,
        )

        # ---- Buttons ------------------------------------------------
        btn_sizer = wx.StdDialogButtonSizer()
        self._save_btn = wx.Button(
            panel,
            wx.ID_OK,
            # Translators: Save button in settings dialog.
            _("Save"),
        )
        self._save_btn.SetDefault()
        cancel_btn = wx.Button(panel, wx.ID_CANCEL)
        btn_sizer.AddButton(self._save_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()

        main_sizer.Add(
            btn_sizer,
            flag=wx.EXPAND | wx.ALL,
            border=10,
        )

        panel.SetSizer(main_sizer)

        self._save_btn.Bind(wx.EVT_BUTTON, self._on_save)

    def _on_browse_folder(self, event: wx.CommandEvent) -> None:
        """Open a folder browser for the download folder."""
        dlg = wx.DirDialog(
            self,
            # Translators: Folder browser dialog prompt.
            message=_("Select download folder"),
            defaultPath=self._folder_text.GetValue(),
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST,
        )
        if dlg.ShowModal() == wx.ID_OK:
            self._folder_text.SetValue(dlg.GetPath())
        dlg.Destroy()

    def _on_save(self, event: wx.CommandEvent) -> None:
        """Apply values from the dialog to settings and save."""
        path = self._folder_text.GetValue().strip()
        if path:
            from pathlib import Path

            from chordcut.utils.paths import get_app_dir

            default_dir = get_app_dir() / "music"
            if Path(path).resolve() == default_dir.resolve():
                # Keep as relative so it follows the app
                # when the portable folder is moved.
                self._settings.download_dir = None
            else:
                self._settings.download_dir = path

        self._settings.volume_step = self._volume_step.GetValue()
        self._settings.seek_step = self._seek_step.GetValue()
        self._settings.remember_volume = self._remember_volume.GetValue()
        self._settings.remember_device = self._remember_device.GetValue()
        self._settings.close_to_tray = self._close_to_tray.GetValue()
        self._settings.check_updates = self._check_updates.GetValue()
        self._settings.global_hotkeys = self._global_hotkeys.GetValue()
        self._settings.save()
        self.EndModal(wx.ID_OK)

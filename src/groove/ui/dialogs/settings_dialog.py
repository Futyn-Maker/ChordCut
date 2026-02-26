"""Settings dialog for Groove."""

import wx

from groove.i18n import _
from groove.settings import Settings


class SettingsDialog(wx.Dialog):
    """Dialog for configuring application settings."""

    def __init__(self, parent: wx.Window, settings: Settings):
        # Translators: Title of the settings dialog.
        super().__init__(
            parent,
            title=_("Settings"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
            size=(500, 380),
        )

        self._settings = settings

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---- Download folder ----------------------------------------
        # Translators: Label for download folder picker.
        folder_label = wx.StaticText(
            panel, label=_("Download &folder:"),
        )
        main_sizer.Add(
            folder_label,
            flag=wx.LEFT | wx.RIGHT | wx.TOP,
            border=10,
        )

        # wx.DirPickerCtrl is the native way to pick a folder in wx:
        # it renders as a read-only text field + "Browse" button.
        self._folder_picker = wx.DirPickerCtrl(
            panel,
            path=str(settings.download_dir),
            # Translators: Folder browser dialog prompt.
            message=_("Select download folder"),
            # Translators: Accessible name for download folder picker.
            name=_("Download folder"),
            style=(
                wx.DIRP_USE_TEXTCTRL
                | wx.DIRP_DIR_MUST_EXIST
                | wx.DIRP_SMALL
            ),
        )
        main_sizer.Add(
            self._folder_picker,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
            border=10,
        )

        # ---- Player settings group ----------------------------------
        # Translators: Label for the player settings group box.
        player_box = wx.StaticBox(
            panel, label=_("Player settings"),
        )
        player_sizer = wx.StaticBoxSizer(
            player_box, wx.VERTICAL,
        )

        # Volume step
        vol_row = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: Label for volume step spin control.
        vol_label = wx.StaticText(
            panel, label=_("&Volume step (%):"),
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
        # Translators: Label for seek step spin control.
        seek_label = wx.StaticText(
            panel, label=_("&Seek step (seconds):"),
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
        # Translators: Checkbox to save volume on exit.
        self._remember_volume = wx.CheckBox(
            panel,
            label=_("Remember &volume level on exit"),
        )
        self._remember_volume.SetValue(settings.remember_volume)
        player_sizer.Add(
            self._remember_volume, flag=wx.ALL, border=5,
        )

        # Remember device checkbox
        # Translators: Checkbox to save audio device on exit.
        self._remember_device = wx.CheckBox(
            panel,
            label=_("Remember output &device on exit"),
        )
        self._remember_device.SetValue(settings.remember_device)
        player_sizer.Add(
            self._remember_device, flag=wx.ALL, border=5,
        )

        main_sizer.Add(
            player_sizer,
            flag=wx.EXPAND | wx.ALL,
            border=10,
        )

        # ---- Buttons ------------------------------------------------
        btn_sizer = wx.StdDialogButtonSizer()
        # Translators: Save button in settings dialog.
        self._save_btn = wx.Button(
            panel, wx.ID_OK, _("Save"),
        )
        self._save_btn.SetDefault()
        # Translators: Cancel button in settings dialog.
        cancel_btn = wx.Button(
            panel, wx.ID_CANCEL, _("Cancel"),
        )
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

    def _on_save(self, event: wx.CommandEvent) -> None:
        """Apply values from the dialog to settings and save."""
        path = self._folder_picker.GetPath()
        if path:
            self._settings.download_dir = path

        self._settings.volume_step = (
            self._volume_step.GetValue()
        )
        self._settings.seek_step = (
            self._seek_step.GetValue()
        )
        self._settings.remember_volume = (
            self._remember_volume.GetValue()
        )
        self._settings.remember_device = (
            self._remember_device.GetValue()
        )
        self._settings.save()
        self.EndModal(wx.ID_OK)

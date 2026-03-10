"""Sleep timer setup dialog for ChordCut."""

import wx

from chordcut.i18n import _

# Action identifiers returned by the dialog
TIMER_ACTION_CLOSE = "close"
TIMER_ACTION_SHUTDOWN = "shutdown"
TIMER_ACTION_SLEEP = "sleep"


class TimerDialog(wx.Dialog):
    """Dialog for configuring the sleep timer."""

    def __init__(self, parent: wx.Window):
        # Translators: Title of the sleep timer dialog.
        super().__init__(
            parent,
            title=_("Sleep Timer"),
            style=wx.DEFAULT_DIALOG_STYLE,
        )

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---- Time entry row -----------------------------------------
        time_box = wx.StaticBox(
            panel,
            # Translators: Group box label for timer duration fields.
            label=_("Timer duration"),
        )
        time_sizer = wx.StaticBoxSizer(time_box, wx.HORIZONTAL)

        # Hours
        # Translators: Label for hours field in timer dialog.
        hours_label = wx.StaticText(panel, label=_("&Hours:"))
        self._hours = wx.SpinCtrl(
            panel,
            min=0,
            max=23,
            initial=0,
            # Translators: Accessible name for hours spin control.
            name=_("Hours"),
        )
        time_sizer.Add(
            hours_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT,
            border=5,
        )
        time_sizer.Add(self._hours, flag=wx.RIGHT, border=10)

        # Minutes
        # Translators: Label for minutes field in timer dialog.
        minutes_label = wx.StaticText(panel, label=_("&Minutes:"))
        self._minutes = wx.SpinCtrl(
            panel,
            min=0,
            max=59,
            initial=0,
            # Translators: Accessible name for minutes spin control.
            name=_("Minutes"),
        )
        time_sizer.Add(
            minutes_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        time_sizer.Add(self._minutes, flag=wx.RIGHT, border=10)

        # Seconds
        # Translators: Label for seconds field in timer dialog.
        seconds_label = wx.StaticText(panel, label=_("&Seconds:"))
        self._seconds = wx.SpinCtrl(
            panel,
            min=0,
            max=59,
            initial=0,
            # Translators: Accessible name for seconds spin control.
            name=_("Seconds"),
        )
        time_sizer.Add(
            seconds_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        time_sizer.Add(self._seconds, flag=wx.RIGHT, border=5)

        main_sizer.Add(
            time_sizer,
            flag=wx.EXPAND | wx.ALL,
            border=10,
        )

        # ---- Action selector ----------------------------------------
        action_row = wx.BoxSizer(wx.HORIZONTAL)
        # Translators: Label for the action dropdown in the timer dialog.
        action_label = wx.StaticText(panel, label=_("&Select action:"))
        self._action_choice = wx.Choice(
            panel,
            choices=[
                # Translators: Timer action — exit the application.
                _("Close the program"),
                # Translators: Timer action — shut down Windows.
                _("Shut down the computer"),
                # Translators: Timer action — sleep/suspend Windows.
                _("Put the computer to sleep"),
            ],
            # Translators: Accessible name for action selector.
            name=_("Select action"),
        )
        self._action_choice.SetSelection(0)
        action_row.Add(
            action_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            border=5,
        )
        action_row.Add(self._action_choice, proportion=1)
        main_sizer.Add(
            action_row,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=10,
        )

        # ---- Buttons ------------------------------------------------
        btn_sizer = wx.StdDialogButtonSizer()
        # Translators: Button to enable the sleep timer.
        self._ok_btn = wx.Button(panel, wx.ID_OK, _("Enable Timer"))
        self._ok_btn.SetDefault()
        # Translators: Cancel button in timer dialog.
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, _("Cancel"))
        btn_sizer.AddButton(self._ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()

        main_sizer.Add(
            btn_sizer,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=10,
        )

        panel.SetSizer(main_sizer)
        main_sizer.Fit(self)

        self._ok_btn.Bind(wx.EVT_BUTTON, self._on_ok)

    def _on_ok(self, event: wx.CommandEvent) -> None:
        """Validate that at least one time unit is non-zero."""
        if self.get_total_seconds() == 0:
            wx.MessageBox(
                # Translators: Error when timer duration is zero.
                _("Please enter a duration greater than zero."),
                # Translators: Title of the validation error dialog.
                _("Invalid Duration"),
                wx.OK | wx.ICON_WARNING,
                self,
            )
            return
        self.EndModal(wx.ID_OK)

    def get_total_seconds(self) -> int:
        """Return total duration in seconds."""
        return (
            self._hours.GetValue() * 3600
            + self._minutes.GetValue() * 60
            + self._seconds.GetValue()
        )

    def get_action(self) -> str:
        """Return the selected action identifier."""
        idx = self._action_choice.GetSelection()
        return [
            TIMER_ACTION_CLOSE,
            TIMER_ACTION_SHUTDOWN,
            TIMER_ACTION_SLEEP,
        ][idx]

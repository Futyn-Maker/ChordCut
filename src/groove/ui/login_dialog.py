"""Login dialog for Jellyfin server connection."""

import wx

from groove.i18n import _


class LoginDialog(wx.Dialog):
    """Dialog for entering Jellyfin server credentials."""

    def __init__(self, parent: wx.Window | None = None):
        """Initialize the login dialog.

        Args:
            parent: Parent window, if any.
        """
        super().__init__(
            parent,
            # Translators: Title of the login dialog for connecting to a Jellyfin server.
            title=_("Connect to Jellyfin Server"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        self._server_url = ""
        self._username = ""
        self._password = ""

        self._create_controls()
        self._do_layout()
        self._bind_events()

        # Set initial focus and size
        self.SetMinSize((400, 200))
        self.SetSize((450, 220))
        self.CenterOnScreen()
        self._url_text.SetFocus()

    def _create_controls(self) -> None:
        """Create the dialog controls."""
        # Labels and text controls
        self._url_label = wx.StaticText(
            self,
            # Translators: Label for the server URL input field. The ampersand indicates the keyboard mnemonic.
            label=_("Server &URL:"),
        )
        self._url_text = wx.TextCtrl(
            self,
            value="",
            # Translators: Accessible name for the server URL input field.
            name=_("Server URL"),
        )
        # Translators: Placeholder hint shown in the server URL field when it is empty.
        self._url_text.SetHint(_("https://jellyfin.example.com"))

        self._username_label = wx.StaticText(
            self,
            # Translators: Label for the username input field. The ampersand indicates the keyboard mnemonic.
            label=_("&Username:"),
        )
        self._username_text = wx.TextCtrl(
            self,
            value="",
            # Translators: Accessible name for the username input field.
            name=_("Username"),
        )

        self._password_label = wx.StaticText(
            self,
            # Translators: Label for the password input field. The ampersand indicates the keyboard mnemonic.
            label=_("&Password:"),
        )
        self._password_text = wx.TextCtrl(
            self,
            value="",
            style=wx.TE_PASSWORD,
            # Translators: Accessible name for the password input field.
            name=_("Password"),
        )

        # Buttons
        self._connect_btn = wx.Button(
            self,
            wx.ID_OK,
            # Translators: Label for the connect button in the login dialog.
            _("&Connect"),
        )
        self._cancel_btn = wx.Button(
            self,
            wx.ID_CANCEL,
            # Translators: Label for the cancel button in the login dialog.
            _("Cancel"),
        )

        self._connect_btn.SetDefault()

    def _do_layout(self) -> None:
        """Layout the dialog controls."""
        # Main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Grid for form fields
        grid = wx.FlexGridSizer(rows=3, cols=2, vgap=10, hgap=10)
        grid.AddGrowableCol(1, 1)

        grid.Add(
            self._url_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT,
        )
        grid.Add(self._url_text, flag=wx.EXPAND)

        grid.Add(
            self._username_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT,
        )
        grid.Add(self._username_text, flag=wx.EXPAND)

        grid.Add(
            self._password_label,
            flag=wx.ALIGN_CENTER_VERTICAL | wx.ALIGN_RIGHT,
        )
        grid.Add(self._password_text, flag=wx.EXPAND)

        main_sizer.Add(grid, proportion=1, flag=wx.EXPAND | wx.ALL, border=15)

        # Button sizer
        btn_sizer = wx.StdDialogButtonSizer()
        btn_sizer.AddButton(self._connect_btn)
        btn_sizer.AddButton(self._cancel_btn)
        btn_sizer.Realize()

        main_sizer.Add(
            btn_sizer,
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=15,
        )

        self.SetSizer(main_sizer)

    def _bind_events(self) -> None:
        """Bind event handlers."""
        self._connect_btn.Bind(wx.EVT_BUTTON, self._on_connect)

    def _on_connect(self, event: wx.CommandEvent) -> None:
        """Handle connect button click."""
        # Validate inputs
        url = self._url_text.GetValue().strip()
        username = self._username_text.GetValue().strip()
        password = self._password_text.GetValue()

        if not url:
            # Translators: Validation error when the server URL field is empty.
            self._show_error(_("Please enter the server URL."))
            self._url_text.SetFocus()
            return

        if not username:
            # Translators: Validation error when the username field is empty.
            self._show_error(_("Please enter your username."))
            self._username_text.SetFocus()
            return

        # Store values
        self._server_url = url
        self._username = username
        self._password = password

        # Accept the dialog
        self.EndModal(wx.ID_OK)

    def _show_error(self, message: str) -> None:
        """Show an error message dialog.

        Args:
            message: Error message to display.
        """
        wx.MessageBox(
            message,
            # Translators: Title of the input validation error dialog.
            _("Input Error"),
            wx.OK | wx.ICON_ERROR,
            self,
        )

    @property
    def server_url(self) -> str:
        """Get the entered server URL."""
        return self._server_url

    @property
    def username(self) -> str:
        """Get the entered username."""
        return self._username

    @property
    def password(self) -> str:
        """Get the entered password."""
        return self._password

    def set_server_url(self, url: str) -> None:
        """Pre-fill the server URL field.

        Args:
            url: URL to set.
        """
        self._url_text.SetValue(url)

    def set_username(self, username: str) -> None:
        """Pre-fill the username field.

        Args:
            username: Username to set.
        """
        self._username_text.SetValue(username)

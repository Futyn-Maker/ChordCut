"""Main application class for Groove."""

import wx

from groove.api import JellyfinClient
from groove.db import Database
from groove.db.database import ServerCredentials
from groove.i18n import _
from groove.player import Player
from groove.settings import Settings
from groove.ui import LoginDialog, MainWindow


class GrooveApp(wx.App):
    """Main wxPython application class."""

    def __init__(self):
        """Initialize the application."""
        self._db: Database | None = None
        self._client: JellyfinClient | None = None
        self._player: Player | None = None
        self._settings: Settings | None = None
        self._main_window: MainWindow | None = None

        super().__init__(redirect=False)

    def OnInit(self) -> bool:
        """Initialize the application (called by wxPython).

        Returns:
            True if initialization succeeded.
        """
        # Initialize core components
        self._settings = Settings()
        self._db = Database()
        self._client = JellyfinClient()
        self._player = Player()

        # Check for saved credentials
        server = self._db.get_active_server()

        if server:
            # Try to reconnect with saved token
            if self._try_reconnect(server):
                self._show_main_window()
                return True

        # No saved credentials or reconnect failed - show login
        if self._show_login():
            self._show_main_window()
            return True

        # User cancelled login
        return False

    def _try_reconnect(self, server: ServerCredentials) -> bool:
        """Try to reconnect using saved credentials.

        Args:
            server: Saved server credentials.

        Returns:
            True if reconnection succeeded.
        """
        return self._client.login_with_token(
            server.url,
            server.user_id,
            server.access_token,
            server.device_id,
        )

    def _show_login(self) -> bool:
        """Show the login dialog and authenticate.

        Returns:
            True if login succeeded, False if cancelled.
        """
        # Check if we have previous server info to pre-fill
        server = self._db.get_active_server()

        while True:
            dialog = LoginDialog()

            if server:
                dialog.set_server_url(server.url)
                dialog.set_username(server.username)

            result = dialog.ShowModal()

            if result != wx.ID_OK:
                dialog.Destroy()
                return False

            # Try to authenticate
            server_url = dialog.server_url
            username = dialog.username
            password = dialog.password
            dialog.Destroy()

            # Show progress
            # Translators: Busy dialog message shown while connecting to the Jellyfin server.
            progress = wx.BusyInfo(_("Connecting to server..."))

            auth_result = self._client.login(server_url, username, password)

            del progress

            if auth_result:
                # Save credentials
                creds = ServerCredentials(
                    id=None,
                    url=server_url,
                    user_id=self._client.user_id or "",
                    username=username,
                    access_token=self._client.access_token or "",
                    device_id=self._client.device_id,
                )
                self._db.save_server(creds)
                return True
            else:
                wx.MessageBox(
                    # Translators: Error message shown when the server connection fails.
                    _("Failed to connect to the server.\n\n"
                      "Please check the server URL and your credentials."),
                    # Translators: Title of the connection error dialog.
                    _("Connection Failed"),
                    wx.OK | wx.ICON_ERROR,
                )

    def _show_main_window(self) -> None:
        """Show the main application window."""
        self._main_window = MainWindow(
            self._db,
            self._client,
            self._player,
            self._settings,
        )

        # Bind change server event
        self._main_window.Bind(
            wx.EVT_MENU,
            self._on_change_server,
            id=wx.ID_NEW,
        )

        self._main_window.Show()

        # Load library
        self._main_window.load_library()

    def _on_change_server(self, event: wx.CommandEvent) -> None:
        """Handle change server request."""
        if self._show_login():
            if self._main_window:
                self._main_window.load_library()


def run() -> None:
    """Run the Groove application."""
    app = GrooveApp()
    app.MainLoop()
